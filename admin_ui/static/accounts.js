'use strict';
const token = document.querySelector('meta[name="office-token"]').content;
const management = document.querySelector('meta[name="management"]').content === 'yes';
const byId = id => document.getElementById(id);
const escapeText = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const dateText = value => value ? new Date(typeof value === 'number' ? value * 1000 : value).toLocaleString('vi-VN') : 'Chưa có';
let profiles = [], providers = [], editing = null, busy = false, loading = false, policyLoaded = false, providerEditing = null;
async function api(path = '', options = {}) {
  return requestJson((management ? '/admin/api/accounts' : '/api/codex/accounts') + path,options);
}
async function requestJson(url, options = {}) {
  const response = await fetch(url, {...options, headers: {'Content-Type':'application/json', 'X-Office-Token': token}});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Không thực hiện được yêu cầu.');
  return data;
}
function showError(id, message) {
  const node = byId(id);
  node.textContent = message || '';
  node.classList.toggle('hidden', !message);
}
function quotaWindow(profile, key, title) {
  const w = profile.windows[key];
  if (!w) return '<div class="quota-window"><strong>' + title + '</strong><small>Chưa có số đo</small></div>';
  const remaining = Math.max(0, 100 - w.used_percent);
  return '<div class="quota-window"><strong>' + title + '<span>' + (['STALE','UNKNOWN','ERROR'].includes(profile.status) ? 'Số đo cũ: còn ' : 'Còn ') + escapeText(remaining) + '%</span></strong><meter min="0" max="100" value="' + remaining + '" aria-label="' + title + ' còn lại"></meter><small>Đã dùng ' + escapeText(w.used_percent) + '% · Reset: ' + escapeText(dateText(w.resets_at)) + '</small></div>';
}
function render() {
  const filter = byId('provider-filter').value;
  const rows = [...profiles,...providers].filter(p => !filter || p.provider===filter);
  byId('account-table').innerHTML = rows.map(p => '<tr><td>'+escapeText(p.name)+'<small>'+escapeText(p.id)+'</small></td><td>'+escapeText(p.provider)+'</td><td>'+escapeText(p.model || 'Theo bài')+'</td><td>'+escapeText(p.status)+'</td><td>'+escapeText(p.windows?.['5h'] ? (100-p.windows['5h'].used_percent)+'%' : 'N/A')+'</td><td>'+escapeText(p.windows?.week ? (100-p.windows.week.used_percent)+'%' : 'N/A')+'</td><td>'+escapeText(p.windows?.['5h'] ? dateText(p.windows['5h'].resets_at) : 'N/A')+'</td><td>'+escapeText(dateText(p.checked))+'</td><td>'+escapeText(p.jobs_completed ?? '—')+'</td></tr>').join('');
  byId('providers-list').innerHTML = rows.filter(p => p.provider==='API').map(p => '<article class="account-card"><h2>'+escapeText(p.name)+'</h2><p>API · '+escapeText(p.model)+' · '+escapeText(p.status)+'</p><p>'+escapeText(p.error)+'</p><small>Ưu tiên: '+p.priority+' · Ngân sách token: '+p.max_job_tokens+'</small><div class="account-card-actions"><button class="button secondary" data-history="'+escapeText(p.id)+'">Lịch sử</button>'+(management ? '<button class="button secondary" data-provider-check="'+p.id+'">Kiểm tra</button><button class="button secondary" data-provider-edit="'+p.id+'">Sửa</button><button class="button danger" data-provider-delete="'+p.id+'">Xóa</button>' : '')+'</div></article>').join('');
  const visible = rows.filter(p => p.provider==='Codex Plus');
  byId('accounts-list').innerHTML = visible.length ? visible.map(p => {
    const status = !p.enabled ? 'Đã tắt theo dõi' : (p.status || 'UNKNOWN') + (p.error ? ' · số đo cũ có thể đã thay đổi' : '');
    return '<article class="account-card"><h2>' + escapeText(p.name) + '</h2><div class="account-path">' + escapeText(p.home) + '</div>' +
      (p.notes ? '<p>' + escapeText(p.notes) + '</p>' : '') +
      '<div class="account-status ' + (p.error ? 'error' : p.low ? 'warning' : '') + '">' + status + '</div>' +
      (p.error ? '<p>' + escapeText(p.error) + '</p>' : '') +
      quotaWindow(p, '5h', '5 giờ') + quotaWindow(p, 'week', 'Hằng tuần') +
      '<small>Lần kiểm tra: ' + escapeText(dateText(p.checked)) + '<br>Số đo thành công: ' + escapeText(dateText(p.last_success)) +
      '<br>Nguồn: '+escapeText(p.source || 'official')+
      '<br>Ngưỡng cảnh báo: còn ≤ ' + escapeText(p.warning) + '%</small>' +
      '<div class="account-card-actions"><button class="button secondary" data-history="'+escapeText(p.id)+'">Lịch sử</button>' + (management ? '<button class="button secondary" data-edit="' + escapeText(p.id) + '">Sửa</button><button class="button danger" data-delete="' + escapeText(p.id) + '">Xóa</button>' : '') + '</div></article>';
  }).join('') : '<div class="empty"><h2>Chưa có hồ sơ theo dõi</h2><p>Thêm hồ sơ hiện tại để xem quota 5 giờ và tuần.</p></div>';
}
function tableActions() {
    byId('account-table').querySelectorAll('tr').forEach((row,index)=>{
      const filter=byId('provider-filter').value;
      const item=[...profiles,...providers].filter(p=>!filter || p.provider===filter)[index];
      const cell=row.insertCell();
      const button=document.createElement('button');button.className='button secondary';button.textContent='Xem';
      button.onclick=()=>openHistory(item.id);cell.append(button);
    });
}
async function load() {
  if (loading) return;
  loading = true;
  try {
    const data = await api();
    profiles = data.accounts;
    providers = data.providers;
    render();tableActions();
    byId('monitor-state').textContent = data.scanning ? 'Đang kiểm tra quota…' : 'Kiểm tra mỗi '+data.interval_seconds+' giây · Lượt gần nhất: ' + dateText(data.last_scan);
    byId('policy-state').textContent = data.policy.enabled ? 'Policy đang bật: thiếu quota sẽ chờ hoặc dùng API được phép.' : 'Policy đang tắt: workflow giữ cách chạy cũ. Admin cần chọn hồ sơ chính và bật policy.';
    if (management) {
      const f = byId('policy-form').elements;
      const selected = f.primary_account.value || data.policy.primary_account;
      f.primary_account.innerHTML = '<option value="">Chọn hồ sơ chính…</option>'+profiles.map(p=>'<option value="'+p.id+'">'+escapeText(p.name)+'</option>').join('');
      f.primary_account.value = selected;
      if (!policyLoaded) {
        for (const [key,value] of Object.entries(data.policy)) {
          if (!f[key]) continue;
          if (f[key].type==='checkbox') f[key].checked=value;
          else f[key].value=value;
        }
        policyLoaded = true;
      }
    }
    const jobs = await requestJson('/api/codex/jobs');
    byId('assignments-log').textContent = jobs.jobs.length ? jobs.jobs.map(j=>j.job_id+' · '+j.state+' · '+(j.kind || 'Chờ provider')+' · '+j.reason).join('\n') : 'Chưa có job được policy phân công.';
    if (management) {
      const audit = await requestJson('/admin/api/audit');
      byId('audit-log').textContent = audit.events.map(e=>dateText(e.timestamp)+' · '+e.action+' · '+e.target).join('\n') || 'Chưa có sự kiện.';
    }
    showError('accounts-message', '');
    if (data.monitor_error) showError('accounts-message',data.monitor_error);
  } catch (error) { showError('accounts-message', error.message); }
  finally { loading = false; }
}
function openForm(profile = null) {
  editing = profile?.id || null;
  const form = byId('account-form');
  form.reset();
  for (const key of ['name','home','notes','model']) form.elements[key].value = profile?.[key] || '';
  form.elements.warning.value = profile?.warning ?? 20;
  form.elements.enabled.checked = profile?.enabled ?? true;
  byId('account-title').textContent = profile ? 'Sửa hồ sơ' : 'Thêm hồ sơ';
  showError('account-error', '');
  byId('account-dialog').showModal();
  form.elements.name.focus();
}
if (management) byId('add-account').onclick = () => openForm();
byId('close-account').onclick = () => { if (!busy) byId('account-dialog').close(); };
byId('account-dialog').addEventListener('cancel', event => { if (busy) event.preventDefault(); });
byId('account-form').onsubmit = async event => {
  event.preventDefault();
  if (busy) return;
  busy = true; byId('save-account').disabled = true;
  const f = event.target.elements;
  try {
    await api(editing ? '/' + editing : '', {method: editing ? 'PUT' : 'POST',
      body: JSON.stringify({name:f.name.value, home:f.home.value, notes:f.notes.value, model:f.model.value, warning:Number(f.warning.value), enabled:f.enabled.checked})});
    byId('account-dialog').close();
    await api('/refresh', {method:'POST'});
    await load();
  } catch (error) { showError('account-error', error.message); }
  finally { busy = false; byId('save-account').disabled = false; }
};
byId('accounts-list').onclick = async event => {
  const button = event.target.closest('button');
  if (!button) return;
  if (button.dataset.history) return openHistory(button.dataset.history);
  const profile = profiles.find(p => p.id === (button.dataset.edit || button.dataset.delete));
  if (!profile) return;
  if (button.dataset.edit) return openForm(profile);
  if (!confirm('Xóa hồ sơ "' + profile.name + '" khỏi danh sách theo dõi? Thư mục đăng nhập Codex và các bài viết được giữ nguyên.')) return;
  button.disabled = true;
  try { await api('/' + profile.id, {method:'DELETE'}); await load(); }
  catch (error) { showError('accounts-message', error.message); button.disabled = false; }
};
if (management) byId('refresh-accounts').onclick = async () => {
  const button = byId('refresh-accounts');
  button.disabled = true;
  try {
    const result = await api('/refresh', {method:'POST'});
    await load();
    byId('monitor-state').textContent = result.queued ? 'Đã yêu cầu kiểm tra quota…' : 'Đang kiểm tra hoặc vừa kiểm tra. Vui lòng đợi ít nhất 30 giây.';
  } catch (error) { showError('accounts-message', error.message); }
  finally { button.disabled = false; }
};
async function openHistory(id) {
  try {
    const data = await requestJson('/api/codex/accounts/'+id+'/history');
    const quotaRows=data.quota.map(q=>{
      const remaining=k=>q.windows[k] ? (100-q.windows[k].used_percent)+'%' : '—';
      return '<tr><td>'+escapeText(dateText(q.checked))+'</td><td>'+remaining('5h')+'</td><td>'+remaining('week')+'</td><td>'+escapeText(q.error || 'Có số đo')+'</td></tr>';
    }).join('');
    const jobRows=data.jobs.map(j=>'<tr><td>'+escapeText(j.job_id)+'</td><td>'+escapeText(j.result)+'</td><td>'+escapeText(j.total_tokens ?? 'Chưa đo')+'</td><td><button class="button secondary" data-workflow-log="'+escapeText(j.job_id)+'">Xem log</button></td></tr>').join('');
    byId('history-data').innerHTML='<h3>Lịch sử quota</h3><p>Số đo tại thời điểm kiểm tra, không phải quota hiện tại.</p><div class="table-scroll"><table class="accounts-table"><thead><tr><th>Thời điểm</th><th>5 giờ còn</th><th>Tuần còn</th><th>Kết quả</th></tr></thead><tbody>'+quotaRows+'</tbody></table></div><h3>Workflow</h3><div class="table-scroll"><table class="accounts-table"><thead><tr><th>Job</th><th>Kết quả</th><th>Token đã đo</th><th>Log</th></tr></thead><tbody>'+jobRows+'</tbody></table></div><pre id="workflow-log"></pre>';
    byId('history-dialog').showModal();
  } catch (e) { showError('accounts-message',e.message); }
}
byId('close-history').onclick=()=>byId('history-dialog').close();
byId('history-data').onclick=async event=>{
  const button=event.target.closest('[data-workflow-log]');if(!button)return;
  try{const job=await requestJson('/api/jobs/'+button.dataset.workflowLog);byId('workflow-log').textContent=job.log || 'Chưa có log.';}
  catch(e){byId('workflow-log').textContent=e.message;}
};
byId('provider-filter').onchange=()=>{render();tableActions();};
byId('providers-list').onclick = async event => {
  const b=event.target.closest('button'); if(!b)return;
  if(b.dataset.history)return openHistory(b.dataset.history);
  const id=b.dataset.providerEdit || b.dataset.providerDelete || b.dataset.providerCheck;
  if(!management || !id)return;
  if(b.dataset.providerEdit)return openProvider(providers.find(p=>p.id===id));
  if(b.dataset.providerDelete && !confirm('Xóa cấu hình API dự phòng này?'))return;
  b.disabled=true;
  try {
    await requestJson('/admin/api/providers/'+id+(b.dataset.providerCheck ? '/check' : ''),{method:b.dataset.providerCheck ? 'POST' : 'DELETE'});
    await load();
  } catch(e){showError('accounts-message',e.message);b.disabled=false;}
};
function openProvider(p=null) {
  providerEditing=p?.id || null;
  const f=byId('provider-form');f.reset();
  for(const key of ['name','model','priority','max_job_tokens']) if(p)f.elements[key].value=p[key];
  f.elements.enabled.checked=!!p?.enabled;
  f.elements.api_key.required=!p;
  showError('provider-error','');
  byId('provider-dialog').showModal();
}
byId('close-provider').onclick=()=>byId('provider-dialog').close();
if(management) {
  byId('add-provider').onclick=()=>openProvider();
  byId('logout-admin').onclick=async()=>{await requestJson('/admin/auth/logout',{method:'POST'});location.assign('/admin');};
  byId('policy-form').onsubmit=async event=>{
    event.preventDefault();const f=event.target.elements,body={};
    for(const key of ['warning','minimum','safety_margin','interval','max_age','cold_start_cost','max_job_quota'])body[key]=Number(f[key].value);
    body.primary_account=f.primary_account.value;body.enabled=f.enabled.checked;body.allow_api=f.allow_api.checked;
    try{await requestJson('/admin/api/policy',{method:'PUT',body:JSON.stringify(body)});await load();}
    catch(e){showError('accounts-message',e.message);}
  };
  byId('provider-form').onsubmit=async event=>{
    event.preventDefault();const f=event.target.elements,b=event.target.querySelector('[type=submit]');
    b.disabled=true;
    try{
      await requestJson('/admin/api/providers'+(providerEditing ? '/'+providerEditing : ''),{
        method:providerEditing ? 'PATCH' : 'POST',body:JSON.stringify({name:f.name.value,model:f.model.value,
        api_key:f.api_key.value,enabled:f.enabled.checked,priority:Number(f.priority.value),max_job_tokens:Number(f.max_job_tokens.value)})});
      f.api_key.value='';byId('provider-dialog').close();await load();
    }catch(e){showError('provider-error',e.message);}finally{b.disabled=false;}
  };
}
load();
setInterval(() => { if (!document.hidden) load(); }, 5000);
