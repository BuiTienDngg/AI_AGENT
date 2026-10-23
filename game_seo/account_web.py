"""Viewer endpoints and server-authorized account administration."""
import json
from flask import Blueprint, abort, jsonify, render_template, request, session
from .account_monitor import AccountMonitor
from .admin_auth import AdminAuth
from .capacity_service import Capacity
from .capacity_db import audit


def install_accounts(app, store, token):
    monitor = AccountMonitor(store)
    auth = AdminAuth(app,store)
    capacity = Capacity(store,monitor,app.extensions['office_jobs'])
    app.extensions.update(office_accounts=monitor,office_auth=auth,office_capacity=capacity)
    app.extensions['office_jobs'].capacity = capacity
    monitor.interval = capacity.settings()['interval']
    monitor.after_scan = capacity.pump
    routes = Blueprint('accounts', __name__)

    @routes.get('/admin')
    @routes.get('/admin/')
    def page():
        return render_template('accounts.html' if auth.allowed() else 'admin_login.html',
                               office_token=token,management=True,configured=auth.configured())

    @routes.get('/accounts')
    def viewer():
        return render_template('accounts.html',office_token=token,management=False)

    @routes.post('/admin/auth/setup')
    def setup():
        auth.setup((request.get_json() or {}).get('password'))
        return jsonify(ok=True)

    @routes.post('/admin/auth/login')
    def login():
        auth.login((request.get_json() or {}).get('password'))
        return jsonify(ok=True)

    @routes.post('/admin/auth/logout')
    @auth.require
    def logout():
        audit(store,'admin.logout','local-admin')
        session.clear()
        return jsonify(ok=True)

    def listing_data(private=False):
        profiles = monitor.profiles()
        from .quota_policy import quota_state
        policy = capacity.settings()
        for profile in profiles:
            profile['status'] = quota_state(profile['windows'],profile['last_success'],error=profile['error'],
                                            max_age=policy['max_age'],warning=policy['warning'])
            profile['provider'] = 'Codex Plus'
            profile['jobs_completed'] = sum(h['result']=='completed' for h in capacity.history(profile['id']))
            if not private:
                for key in ('home','notes'):
                    profile.pop(key,None)
        return dict(accounts=profiles,providers=capacity.providers(),scanning=monitor.scanning,
                    last_scan=monitor.last_scan,interval_seconds=monitor.interval,
                    policy=policy,monitor_error=monitor.last_error or capacity.last_error)

    @routes.get('/admin/api/accounts')
    @auth.require
    def listing():
        return jsonify(**listing_data(True))

    @routes.get('/api/codex/accounts')
    def public_listing():
        return jsonify(**listing_data())

    @routes.get('/api/codex/accounts/<key>')
    @routes.get('/api/codex/accounts/<key>/quota')
    def public_detail(key):
        row = next((p for p in listing_data()['accounts'] if p['id']==key),None)
        if not row:
            abort(404)
        return jsonify(row)

    @routes.get('/api/codex/accounts/<key>/history')
    def history(key):
        with store.connection() as db:
            rows = db.execute('SELECT checked,windows,error FROM codex_profile_samples WHERE profile_id=? ORDER BY id DESC LIMIT 100',(key,)).fetchall()
        return jsonify(quota=[{**dict(r),'windows':json.loads(r['windows'])} for r in rows],jobs=capacity.history(key))

    @routes.get('/api/codex/monitor/status')
    def status():
        return jsonify(scanning=monitor.scanning,last_scan=monitor.last_scan,error=monitor.last_error,
                       interval_seconds=monitor.interval,policy=capacity.settings())

    @routes.get('/api/codex/jobs')
    def job_list():
        return jsonify(jobs=capacity.jobs_list(),usage=capacity.history())

    @routes.post('/admin/api/accounts')
    @auth.require
    def create():
        return jsonify(id=monitor.save(request.get_json())),201

    @routes.put('/admin/api/accounts/<key>')
    @routes.patch('/admin/api/accounts/<key>')
    @auth.require
    def edit(key):
        current = next((p for p in monitor.profiles() if p['id']==key),None)
        if not current:
            abort(404)
        return jsonify(id=monitor.save({**current,**request.get_json()},key))

    @routes.delete('/admin/api/accounts/<key>')
    @auth.require
    def delete(key):
        if capacity.settings()['enabled'] and capacity.settings()['primary_account']==key:
            raise ValueError('Tắt policy hoặc chọn hồ sơ chính khác trước khi xóa.')
        if any(a['provider_id']==key and a['state']=='RUNNING' for a in capacity.jobs_list()):
            raise ValueError('Hồ sơ đang chạy job.')
        monitor.delete(key)
        return jsonify(deleted=True)

    @routes.post('/admin/api/accounts/refresh')
    @auth.require
    def refresh():
        return jsonify(queued=monitor.trigger()),202

    @routes.put('/admin/api/policy')
    @auth.require
    def policy():
        return jsonify(policy=capacity.configure(request.get_json()))

    @routes.post('/admin/api/providers')
    @auth.require
    def provider_create():
        return jsonify(id=capacity.save_provider(request.get_json())),201

    @routes.patch('/admin/api/providers/<key>')
    @auth.require
    def provider_edit(key):
        current = next((p for p in capacity.providers() if p['id']==key),None)
        if not current:
            abort(404)
        return jsonify(id=capacity.save_provider({**current,**request.get_json()},key))

    @routes.delete('/admin/api/providers/<key>')
    @auth.require
    def provider_delete(key):
        capacity.delete_provider(key)
        return jsonify(deleted=True)

    @routes.post('/admin/api/providers/<key>/check')
    @auth.require
    def provider_check(key):
        return jsonify(status=capacity.check_provider(key))

    @routes.get('/admin/api/audit')
    @auth.require
    def audit_log():
        with store.connection() as db:
            rows = db.execute('SELECT * FROM account_audit_logs ORDER BY id DESC LIMIT 200').fetchall()
        return jsonify(events=[dict(r) for r in rows])

    app.register_blueprint(routes)
    return monitor
