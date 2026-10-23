"""Capacity admission, durable queue, provider assignments and usage history."""
import json
import re
import time
import uuid
from datetime import datetime, timezone

import requests

from .core import load_json, utc_now
from .capacity_db import audit
from .quota_policy import DEFAULTS, evaluate
from .secret_store import Secrets
from .web_review import atomic_json


class Capacity:
    def __init__(self, store, monitor, jobs):
        self.store, self.monitor, self.jobs = store, monitor, jobs
        self.vault = Secrets(store)
        self.last_error = ''
        self.recover()

    def settings(self):
        with self.store.connection() as db:
            row = db.execute('SELECT config FROM capacity_settings WHERE id=1').fetchone()
        return {**DEFAULTS, **(json.loads(row[0]) if row else {})}

    def configure(self, data):
        cfg = self.settings()
        for key in DEFAULTS:
            if key not in data:
                continue
            value = data[key]
            if key in ('enabled','allow_api'):
                if not isinstance(value,bool):
                    raise ValueError('Cấu hình bật/tắt không hợp lệ.')
            elif key == 'primary_account':
                if value and not any(p['id']==value for p in self.monitor.profiles()):
                    raise ValueError('Chọn hồ sơ Codex chính đã đăng ký.')
            elif not isinstance(value,(int,float)) or isinstance(value,bool) or not 0 <= value <= (3600 if key in ('interval','max_age') else 100):
                raise ValueError('Tham số policy không hợp lệ.')
            cfg[key] = value
        if cfg['interval']<30 or cfg['max_age']<cfg['interval'] or cfg['minimum']>cfg['warning']:
            raise ValueError('Chu kỳ ≥ 30 giây, độ mới ≥ chu kỳ; ngưỡng tối thiểu ≤ cảnh báo.')
        if cfg['enabled'] and not cfg['primary_account']:
            raise ValueError('Cần chọn hồ sơ Codex chính trước khi bật policy.')
        with self.store.connection() as db:
            db.execute('INSERT OR REPLACE INTO capacity_settings VALUES(1,?)',(json.dumps(cfg),))
            audit(self.store,'policy.update','capacity',db)
        self.monitor.interval = cfg['interval']
        self.monitor.trigger()
        return cfg

    def providers(self):
        with self.store.connection() as db:
            rows = db.execute('SELECT id,name,model,enabled,priority,status,checked,error,max_job_tokens,updated '
                              'FROM provider_configs ORDER BY priority,id').fetchall()
        return [dict(r,provider='API',configured=True,
                     jobs_completed=sum(h['result']=='completed' for h in self.history(r['id']))) for r in rows]

    def save_provider(self, data, key=None):
        name, model = data.get('name','').strip(), data.get('model','').strip()
        if not name or len(name)>100 or not re.fullmatch(r'[a-zA-Z0-9._-]{1,100}',model):
            raise ValueError('Cần tên provider và model ID hợp lệ.')
        priority, limit = data.get('priority',100), data.get('max_job_tokens',1000000)
        if isinstance(priority,bool) or not isinstance(priority,int) or not 0<=priority<=1000 or isinstance(limit,bool) or not isinstance(limit,int) or not 1000<=limit<=10000000:
            raise ValueError('Ưu tiên 0–1000; ngân sách token 1.000–10.000.000.')
        enabled = data.get('enabled',False)
        if not isinstance(enabled,bool):
            raise ValueError('Trạng thái provider không hợp lệ.')
        existing = next((p for p in self.providers() if p['id']==key),None)
        if key and not existing:
            raise KeyError(key)
        key = key or uuid.uuid4().hex
        ref = 'api-'+key
        secret = data.get('api_key','')
        if not isinstance(secret,str) or len(secret)>1000 or any(c.isspace() for c in secret):
            raise ValueError('API key không hợp lệ.')
        if not existing and not secret:
            raise ValueError('Cần API key khi tạo provider dự phòng.')
        if secret:
            self.vault.put(ref,secret)
        with self.store.connection() as db:
            db.execute('INSERT INTO provider_configs(id,name,model,enabled,priority,max_job_tokens,secret_ref,updated) '
                       'VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,model=excluded.model,'
                       'enabled=excluded.enabled,priority=excluded.priority,max_job_tokens=excluded.max_job_tokens,'
                       "updated=excluded.updated,status='UNKNOWN',error=''",
                       (key,name,model,int(enabled),priority,limit,ref,utc_now()))
            audit(self.store,'provider.update' if existing else 'provider.create',key,db)
        return key

    def delete_provider(self,key):
        with self.store.connection() as db:
            if db.execute("SELECT 1 FROM job_assignments WHERE provider_id=? AND state='RUNNING'",(key,)).fetchone():
                raise ValueError('Provider đang chạy job. Chờ hoàn tất trước khi xóa.')
            if not db.execute('DELETE FROM provider_configs WHERE id=?',(key,)).rowcount:
                raise KeyError(key)
            audit(self.store,'provider.delete',key,db)
        self.vault.delete('api-'+key)

    def check_provider(self,key):
        provider = next((p for p in self.providers() if p['id']==key),None)
        if not provider:
            raise KeyError(key)
        try:
            secret = self.vault.get('api-'+key)
            if not secret:
                raise ValueError()
            response = requests.get('https://api.openai.com/v1/models/'+provider['model'],
                                    headers={'Authorization':'Bearer '+secret},timeout=8,allow_redirects=False)
            status = 'AVAILABLE' if response.status_code==200 else 'ERROR'
            response.close()
        except Exception:
            status = 'ERROR'
        with self.store.connection() as db:
            db.execute('UPDATE provider_configs SET status=?,checked=?,error=? WHERE id=?',
                       (status,utc_now(),'' if status=='AVAILABLE' else 'Không xác nhận được quyền truy cập model API.',key))
        return status

    def history(self,provider=None):
        with self.store.connection() as db:
            rows = db.execute('SELECT * FROM workflow_usage WHERE provider_id=? ORDER BY updated DESC LIMIT 100',(provider,)).fetchall() if provider else db.execute('SELECT * FROM workflow_usage ORDER BY updated DESC LIMIT 100').fetchall()
        return [dict(r) for r in rows]

    def recover(self):
        # Never automatically replay an in-flight model call after a crash.
        with self.store.connection() as db:
            db.execute("UPDATE job_assignments SET state='INTERRUPTED',reason=?,updated=? WHERE state='RUNNING'",
                       ('Backend restart: cần bấm Chạy tiếp để dùng checkpoint hợp lệ.',utc_now()))

    def admit(self,job,task='article'):
        cfg = self.settings()
        if not cfg['enabled']:
            file = self.jobs.workdir(job)/'admin_config.json'
            previous_cfg = load_json(file,default={})
            if previous_cfg.pop('api_provider',None):
                previous_cfg.pop('max_job_tokens',None)
                previous_cfg['quota_tracking'] = True
                original = job['data'].get('execution',{}).get('model')
                if original:
                    previous_cfg['codex_model'] = original
                atomic_json(file,previous_cfg)
            return {}
        # The single explicitly selected Plus profile is the only subscription candidate.
        primary = next((p for p in self.monitor.profiles() if p['id']==cfg['primary_account']),None)
        run_cfg = load_json(self.jobs.workdir(job)/'admin_config.json')
        if primary and primary.get('model'):
            run_cfg['codex_model'] = primary['model']
        history = [h for h in self.history(cfg['primary_account']) if h['model']==run_cfg.get('codex_model')]
        decision = evaluate(primary or {},cfg,history)
        selected = {'id':primary['id'],'kind':'codex','home':primary['home']} if primary and decision['allowed'] else None
        if not selected and cfg['allow_api']:
            for provider in self.providers():
                if not provider['enabled']:
                    continue
                # Metadata probe is not a guarantee of billing balance; failures stay queued.
                if self.check_provider(provider['id'])=='AVAILABLE':
                    selected = {**provider,'kind':'api'}
                    break
        with self.store.connection() as db:
            previous = db.execute('SELECT * FROM job_assignments WHERE job_id=?',(job['id'],)).fetchone()
            if previous and previous['state']=='RUNNING':
                raise ValueError('Job đã có tiến trình đang chạy.')
            state = 'RUNNING' if selected else 'WAITING_FOR_CAPACITY'
            attempts = (previous['attempts'] if previous else 0) + int(bool(selected))
            used = json.loads(previous['providers_used']) if previous else []
            if selected:
                signature = selected['kind']+':'+selected['id']+':'+(selected.get('model') or run_cfg.get('codex_model') or '')
                if signature not in used:
                    used.append(signature)
            db.execute('INSERT INTO job_assignments(job_id,provider_id,kind,state,reason,attempts,started,updated) VALUES(?,?,?,?,?,?,?,?) '
                       'ON CONFLICT(job_id) DO UPDATE SET provider_id=excluded.provider_id,kind=excluded.kind,state=excluded.state,'
                       'reason=excluded.reason,attempts=excluded.attempts,started=excluded.started,updated=excluded.updated',
                       (job['id'],selected['id'] if selected else None,selected['kind'] if selected else None,
                        state,decision['reason'],attempts,utc_now() if selected else None,utc_now()))
            db.execute('UPDATE job_assignments SET providers_used=?,next_retry=? WHERE job_id=?',
                       (json.dumps(used),0 if selected else time.time()+cfg['interval'],job['id']))
        if not selected:
            self.store.update_job(job['id'],'waiting_for_capacity',decision['reason'])
            return None
        environment = {}
        if selected['kind']=='codex':
            environment['CODEX_HOME'] = selected['home']
            run_cfg.pop('api_provider',None)
            run_cfg.pop('max_job_tokens',None)
        else:
            try:
                secret = self.vault.get('api-'+selected['id'])
            except Exception:
                secret = None
            if not secret:
                with self.store.connection() as db:
                    db.execute("UPDATE job_assignments SET state='WAITING_FOR_CAPACITY',reason=?,updated=? WHERE job_id=?",
                               ('Không giải mã được credential API.',utc_now(),job['id']))
                self.store.update_job(job['id'],'waiting_for_capacity','Không giải mã được credential API.')
                return None
            environment['GAME_SEO_API_KEY'] = secret
            run_cfg['api_provider'] = True
            run_cfg['quota_tracking'] = False
            run_cfg['codex_model'] = selected['model']
            run_cfg['max_job_tokens'] = selected['max_job_tokens']
        atomic_json(self.jobs.workdir(job)/'admin_config.json',run_cfg)
        return environment

    def defer(self,job):
        with self.store.connection() as db:
            db.execute("INSERT INTO job_assignments(job_id,state,reason,updated) VALUES(?,'QUEUED',?,?) "
                       "ON CONFLICT(job_id) DO UPDATE SET state='QUEUED',updated=excluded.updated",
                       (job['id'],'Đang có một workflow khác chạy.',utc_now()))
        self.store.update_job(job['id'],'queued','Đang chờ workflow trước hoàn tất.')

    def finished(self,job):
        with self.store.connection() as db:
            assignment = db.execute('SELECT * FROM job_assignments WHERE job_id=?',(job['id'],)).fetchone()
        if not assignment:
            return
        work = self.jobs.workdir(job)
        tokens = load_json(work/'token_usage.json',default={})
        totals = tokens.get('measured_totals',{})
        quota = load_json(work/'quota_usage.json',default={}).get('summary',{})
        cfg = load_json(work/'admin_config.json',default={})
        # Only full original-run subscription measurements train the estimator.
        clean = (assignment['kind']=='codex' and job['status']=='completed' and
                 json.loads(assignment['providers_used'])==['codex:'+assignment['provider_id']+':'+(cfg.get('codex_model') or '')])
        deltas = [quota.get(k,{}).get('delta_percent_points') if clean else None for k in ('5h','week')]
        duration = sum(c.get('duration_seconds',0) for c in tokens.get('calls',[]))
        status = {'running':'RUNNING','stopped':'CANCELLED','waiting':'WAITING_FOR_INPUT',
                  'completed':'COMPLETED','interrupted':'INTERRUPTED','failed':'FAILED'}.get(job['status'],job['status'].upper())
        with self.store.connection() as db:
            db.execute('UPDATE job_assignments SET state=?,updated=? WHERE job_id=?',(status,utc_now(),job['id']))
            db.execute('INSERT OR REPLACE INTO workflow_usage VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                       (job['id'],assignment['provider_id'],cfg.get('codex_model'),job['status'],
                        totals.get('input_tokens'),totals.get('cached_input_tokens'),totals.get('output_tokens'),
                        totals.get('total_tokens'),duration,*deltas,utc_now()))
            if job['status']=='failed' and assignment['kind']=='api':
                db.execute("UPDATE provider_configs SET status='ERROR',error=?,checked=? WHERE id=?",
                           ('Job API lỗi. Kiểm tra log đã che bí mật trước khi thử lại.',utc_now(),assignment['provider_id']))

    def pump(self):
        with self.jobs.lock:
            if self.jobs.active or not self.settings()['enabled']:
                return
            with self.store.connection() as db:
                rows = db.execute("SELECT a.job_id FROM job_assignments a JOIN jobs j ON j.id=a.job_id "
                                  "WHERE a.state IN ('WAITING_FOR_CAPACITY','QUEUED') AND j.status IN ('waiting_for_capacity','queued') "
                                  "AND a.next_retry<=? ORDER BY j.created",(time.time(),)).fetchall()
            for row in rows:
                try:
                    job = self.store.job(row['job_id'])
                    self.jobs._launch(job)
                    if self.jobs.active:
                        break
                except Exception:
                    self.last_error = 'Không thể khởi chạy job chờ; sẽ đánh giá lại ở chu kỳ tiếp theo.'
                    job = self.store.job(row['job_id'])
                    if job['status']=='failed':
                        self.finished(job)

    def jobs_list(self):
        with self.store.connection() as db:
            return [dict(r) for r in db.execute('SELECT * FROM job_assignments ORDER BY updated DESC LIMIT 200')]
