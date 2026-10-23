'use strict';
const $ = (s, root = document) => root.querySelector(s);
const $$ = (s, root = document) => [...root.querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const icon = name => '<svg class="icon" aria-hidden="true"><use href="#i-' + name + '"/></svg>';
const token = $('meta[name="office-token"]').content;
const labels = {draft:'Chưa chạy',running:'Đang chạy',translating:'Đang dịch câu hỏi',stopping:'Đang dừng',waiting:'Chờ bạn trả lời',waiting_for_capacity:'Chờ quota / provider',cancelled:'Đã hủy',completed:'Đã hoàn tất',failed:'Cần kiểm tra',stopped:'Đã dừng',interrupted:'Bị gián đoạn',legacy:'Lượt cũ'};
const activeState = status => ['running','stopping','translating'].includes(status);
labels.queued='Trong hàng đợi';
const badge = state => '<span class="badge ' + esc(state) + '">' + (state === 'running' ? '<span class="live-dot"></span>' : '') + esc(labels[state] || state) + '</span>';
const date = value => value ? new Date(value).toLocaleString('vi-VN', {day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'}) : '—';
const duration = seconds => Math.floor(seconds / 60) + ':' + String(Math.round(seconds % 60)).padStart(2,'0');
const bytes = size => size >= 1024**3 ? (size / 1024**3).toFixed(1) + ' GB' : (size / 1024**2).toFixed(1) + ' MB';
let state = {games:[],jobs:[],history:[],settings:{}}, view = 'games', editing = null;
let selectedVideo = null, videoURL = null, formDirty = false, uploading = false;
let importedBrief = null;
let selectedJob = null, details = null, tab = 'progress', questionDirty = false, busy = false, refreshing = false;
let savedGameId = null, savedEntries = [];
const savedDirty = new Set();
let toastTimer;
let modelCatalogKey = '';
function remembered(key) { try{return localStorage.getItem(key) || '';}catch{return '';} }
function remember(key,value) { try{localStorage.setItem(key,value);}catch{} }
function setupModels() {
  const models=state.settings.models;
  if(!models?.length)return;
  $('#execution-panel').classList.remove('hidden');
  const key=JSON.stringify(models);
  if(key!==modelCatalogKey){
    const current=$('#run-model').value || remembered('office-model') || state.settings.model;
    $('#run-model').innerHTML=models.map(m=>'<option value="'+esc(m.id)+'">'+esc(m.label)+'</option>').join('')+'<option value="custom">Nhập model khác…</option>';
    $('#run-model').value=models.some(m=>m.id===current)?current:'custom';
    if($('#run-model').value==='custom')$('#custom-model').value=remembered('office-custom-model') || current;
    modelCatalogKey=key;updateEfforts();
  }
}
function selectedExecution() {
  if(!state.settings.models?.length)return {};
  const model=$('#run-model').value==='custom'?$('#custom-model').value.trim():$('#run-model').value;
  if(!/^gpt-[A-Za-z0-9._-]{1,90}$/.test(model))throw new Error('Nhập ID model GPT hợp lệ.');
  return {model,reasoning_effort:$('#run-effort').value};
}
function updateEfforts() {
  const model=$('#run-model').value, entry=state.settings.models?.find(m=>m.id===model);
  const allowed=entry?.efforts || ['low','medium','high','xhigh','max'];
  const current=$('#run-effort').value || remembered('office-effort') || state.settings.reasoning_effort;
  $('#run-effort').innerHTML=allowed.map(e=>'<option value="'+esc(e)+'">'+esc(e)+'</option>').join('');
  $('#run-effort').value=allowed.includes(current)?current:entry?.default_effort || allowed[0];
  $('#custom-model-label').classList.toggle('hidden',model!=='custom');
}

async function api(path, body, method) {
  const options = {method:method || (body === undefined ? 'GET' : 'POST'), headers:{'X-Office-Token':token}};
  if (body !== undefined) { options.headers['Content-Type']='application/json'; options.body=JSON.stringify(body); }
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Không thực hiện được thao tác.');
  return data;
}
function toast(message) {
  const holder=$('#job-dialog').open?$('#job-dialog'):$('#saved-answers-dialog').open?$('#saved-answers-dialog'):$('#game-dialog').open?$('#game-dialog'):document.body;
  holder.appendChild($('#toast'));
  $('#toast').textContent = message; $('#toast').classList.remove('hidden');
  clearTimeout(toastTimer); toastTimer=setTimeout(() => $('#toast').classList.add('hidden'), 4200);
}
function errorAt(id, message) { const el=$(id); el.textContent=message; el.classList.toggle('hidden',!message); if(message)el.scrollIntoView({block:'nearest'}); }
function latestJob(game) { return state.jobs.find(j => j.game_id === game.id); }
function executionLabel(execution) { return execution?.model ? execution.model+(execution.reasoning_effort?' / '+execution.reasoning_effort:'') : ''; }
function downloads(run, files) {
  const ready=state.history.find(h=>h.run_name===run)?.result_available || (details?.job?.run_name===run && details.result_available);
  return '<div class="download-group">' + ['docx_en','docx_vi'].filter(k => files.includes(k)).map(k =>
    '<a class="button secondary small" href="/api/runs/' + encodeURIComponent(run) + '/download/' + k + '">' + icon('file') + 'Word ' + (k==='docx_en'?'EN':'VI') + '</a>').join('') + (ready ? '<a class="button primary small" href="/api/runs/'+encodeURIComponent(run)+'/result.zip">'+icon('file')+'Bộ đăng site (.zip)</a>' : '') + '</div>';
}
function quotaSummary(quota) {
  const summary=quota?.summary || quota || {};
  return [['5h','5 giờ'],['week','Tuần']].filter(([key])=>summary[key]).map(([key,label])=>{
    const value=summary[key], before=value.before_percent, after=value.after_percent;
    const delta=value.delta_percent_points;
    const latest=value.latest_percent ?? after;
    const text=after===null||after===undefined?esc(latest)+'% đã dùng · chưa có mốc kết thúc':before===null||before===undefined?esc(after)+'% đã dùng (thiếu mốc trước khi chạy)':esc(before)+'% → '+esc(after)+'% đã dùng';
    return '<div class="quota-window"><strong>'+label+'</strong><span>'+text+(delta===null||delta===undefined?'':' · tăng '+esc(delta)+' điểm %')+'</span>'+(value.reset_detected?'<small>Hạn mức đã reset trong khoảng đo; không tính chênh lệch.</small>':'')+'</div>';
  }).join('');
}
function empty(title, text, action='') {
  return '<div class="empty"><div class="empty-symbol">' + icon(view==='history'?'history':view==='questions'?'question':'grid') + '</div><h3>' + esc(title) + '</h3><p>' + esc(text) + '</p>' + action + '</div>';
}
function render() {
  const waiting=state.jobs.filter(j=>j.status==='waiting').length;
  $('#nav-games').textContent=state.games.length; $('#nav-questions').textContent=waiting;
  $('#stats').innerHTML=[
    ['Game trong thư viện',state.games.length,'grid',''],
    ['Lượt đang chạy',state.jobs.filter(j=>activeState(j.status)).length,'play','blue'],
    ['Chờ bạn trả lời',waiting,'question','amber'],
    ['Bài đã hoàn tất',state.history.filter(h=>h.status==='completed' && h.files.length===2).length,'file','green']
  ].map(([label,value,symbol,tone])=>'<div class="stat"><div><div class="stat-label">'+label+'</div><div class="stat-value">'+value+'</div></div><span class="stat-icon '+tone+'">'+icon(symbol)+'</span></div>').join('');
  setupModels();
  const model=state.settings.model || 'Codex mặc định';
  $('#model-info').textContent=model+' · '+(state.settings.frames || 16)+' khung hình / video';
  const missing=Object.entries(state.settings.dependencies || {}).filter(([,ok])=>!ok).map(([key])=>key);
  const warning=$('#dependency-warning');
  warning.textContent=missing.length?'Chưa tìm thấy '+missing.join(', ')+'. Cần bổ sung trước khi chạy viết bài; bạn vẫn có thể lưu game.':'';
  warning.classList.toggle('hidden',!missing.length);
  renderCollection();
}
function renderCollection() {
  const query=$('#search').value.toLocaleLowerCase('vi'), filter=$('#status-filter').value;
  const matches=(name,status)=>name.toLocaleLowerCase('vi').includes(query) && (!filter || filter===status || (filter==='failed' && status==='interrupted'));
  if (view==='games') {
    const rows=state.games.filter(g=>matches(g.data.name,latestJob(g)?.status || 'draft'));
    $('#collection-count').textContent=rows.length;
    if (!rows.length) { $('#content').innerHTML=empty(state.games.length?'Không tìm thấy game':'Bắt đầu với game đầu tiên',state.games.length?'Thử tên hoặc trạng thái khác.':'Thêm video, xác nhận cách chơi và để AI phát triển bài giới thiệu từ ý tưởng của bạn.',!state.games.length?'<button class="button primary" data-action="new">'+icon('plus')+'Thêm game mới</button>':''); return; }
    $('#content').innerHTML='<div class="game-grid">'+rows.map((g,index)=>{
      const job=latestJob(g), status=job?.status || 'draft';
      const initials=g.data.name.split(/\s+/).slice(0,2).map(x=>x[0]).join('').toUpperCase();
      const canRun=state.settings.capacity_policy_enabled || !state.jobs.some(j=>activeState(j.status));
      const main=job && (['waiting','queued','waiting_for_capacity'].includes(status) || activeState(status))
        ? '<button class="button '+(status==='waiting'?'soft':'secondary')+' small" data-action="job" data-id="'+job.id+'">'+icon(status==='waiting'?'question':'arrow')+(status==='waiting'?'Trả lời AI':'Xem tiến độ')+'</button>'
        : '<button class="button soft small" data-action="run" data-id="'+g.id+'" '+(!canRun?'disabled':'')+'>'+icon('play')+'Chạy viết bài</button>';
      return '<article class="game-card"><div class="card-top"><span class="game-monogram tone'+(index%4)+'">'+esc(initials)+'</span>'+badge(status)+'</div><h3>'+esc(g.data.name)+'</h3><a class="card-site" href="'+esc(g.data.game_url)+'" target="_blank" rel="noopener noreferrer">'+esc(new URL(g.data.site_url).hostname)+'</a><div class="card-meta">'+icon('video')+'<span title="'+esc(g.data.video_name)+'">'+esc(g.data.video_name)+' · '+duration(g.data.video_seconds)+'</span></div><div class="card-bottom">'+main+(job && status!=='waiting' && !activeState(status)?'<button class="icon-button" data-action="job" data-id="'+job.id+'" title="Lượt chạy gần nhất" aria-label="Xem lượt chạy gần nhất">'+icon('history')+'</button>':'')+'<button class="icon-button" data-action="saved" data-id="'+g.id+'" title="Câu hỏi đã lưu" aria-label="Câu hỏi đã lưu của '+esc(g.data.name)+'">'+icon('question')+'</button><button class="icon-button" data-action="edit" data-id="'+g.id+'" title="Sửa game" aria-label="Sửa '+esc(g.data.name)+'">'+icon('edit')+'</button><button class="icon-button delete" data-action="delete" data-id="'+g.id+'" title="Xóa game" aria-label="Xóa '+esc(g.data.name)+'">'+icon('trash')+'</button></div></article>';
    }).join('')+'</div>';
  } else {
    let rows=view==='questions'?state.history.filter(h=>h.status==='waiting'):state.history;
    rows=rows.filter(h=>matches(h.name+' '+h.run_name,h.status)); $('#collection-count').textContent=rows.length;
    if (!rows.length) { $('#content').innerHTML=empty(view==='questions'?'Không có câu hỏi đang chờ':'Chưa có lượt chạy phù hợp',view==='questions'?'Khi AI cần bạn xác nhận cách chơi hoặc đối tượng, câu hỏi sẽ xuất hiện tại đây.':'Kết quả mới và các bài trong thư mục runs sẽ xuất hiện ở đây.'); return; }
    $('#content').innerHTML='<div class="history-wrap"><table><thead><tr><th>Game / lượt chạy</th><th>Trạng thái</th><th>Cập nhật</th><th>Kết quả</th><th></th></tr></thead><tbody>'+rows.map(h=>'<tr><td><strong>'+esc(h.name)+'</strong><span class="subtext" title="'+esc(h.run_name)+'">'+esc(h.run_name)+'</span><span class="run-model-note">'+esc(executionLabel(h.execution))+'</span></td><td>'+badge(h.status)+'</td><td>'+date(h.updated)+'</td><td>'+(h.files.length?downloads(h.run_name,h.files):'<span class="no-download">Chưa xuất Word</span>')+'</td><td>'+(h.job_id?'<button class="button '+(h.status==='waiting'?'soft':'secondary')+' small" data-action="job" data-id="'+h.job_id+'">'+(h.status==='waiting'?'Trả lời AI':'Chi tiết')+icon('arrow')+'</button>':'<button class="button secondary small" data-action="import" data-id="'+esc(h.run_name)+'">'+icon('plus')+'Nhập thành game</button>')+'</td></tr>').join('')+'</tbody></table></div>';
    $$('#content tbody tr').forEach((row,index)=>{
      const quota=rows[index].quota || {};
      if(quota['5h'] || quota.week)row.cells[1].insertAdjacentHTML('beforeend','<span class="run-quota-note">Tài khoản: 5 giờ '+esc(quota['5h']?.after_percent ?? quota['5h']?.latest_percent ?? '—')+'% · tuần '+esc(quota.week?.after_percent ?? quota.week?.latest_percent ?? '—')+'%</span>');
    });
  }
}
function navigate(target) {
  view=target; $('#search').value=''; $('#status-filter').value='';
  const titles={games:'Thư viện game',questions:'AI đang hỏi',history:'Lịch sử & kết quả'};
  const descriptions={games:'Ý tưởng của bạn. Câu chuyện của game. Hai bản Word sẵn sàng để duyệt.',questions:'Xác nhận những gì AI chưa rõ để bài viết mô tả đúng sản phẩm của bạn.',history:'Tất cả lượt chạy ở một nơi. Mở kết quả cũ, theo dõi bài mới và tải Word.'};
  $('#page-title').textContent=titles[view]; $('#breadcrumb').textContent=titles[view];
  $('#page-description').textContent=descriptions[view]; $('#collection-title').textContent=view==='games'?'Tất cả game':view==='questions'?'Cần bạn xác nhận':'Tất cả lượt chạy';
  $$('[data-nav]').forEach(b=>b.classList.toggle('active',b.dataset.nav===view)); renderCollection();
}
async function refresh() {
  if (refreshing) return;
  refreshing=true;
  try {
    const next=await api('/api/state');
    const changed=JSON.stringify(next)!==JSON.stringify(state);
    state=next; if (changed) render(); $('#connection-error').classList.add('hidden');
    if (selectedJob && $('#job-dialog').open && !busy) await refreshJob();
  } catch (error) { $('#connection-error').textContent=error.message==='Failed to fetch'?'Mất kết nối với máy chủ local. Kiểm tra terminal đang chạy trang quản trị.':error.message; $('#connection-error').classList.remove('hidden'); }
  finally { refreshing=false; }
}
function openGame(id=null, imported=null) {
  importedBrief=imported;
  editing=id?state.games.find(g=>g.id===id):null; selectedVideo=null; formDirty=false;
  $('#game-form').reset(); errorAt('#form-error',''); $('#form-title').textContent=editing?'Sửa thông tin game':'Thêm game mới';
  for (const key of ['name','site_url','game_url','idea_origin','story','game_style','controls_pc','controls_mobile']) $('#game-form').elements[key].value=editing?.data[key] || imported?.fields[key] || '';
  if (!editing && !imported?.fields.site_url) $('#game-form').elements.site_url.value='https://slope3.com/';
  $('#drop-title').textContent=editing?editing.data.video_name:imported?.video_available?imported.video_name:'Kéo thả video vào đây';
  $('#drop-meta').textContent=editing?duration(editing.data.video_seconds)+' · '+bytes(editing.data.video_bytes)+' · Bấm để thay video':imported?.video_available?'Dùng video của lượt cũ · Bấm để thay video':'hoặc bấm để chọn · MP4, MOV, MKV, WEBM · tối đa 4 GB';
  $('#video-preview').classList.add('hidden'); $('#video-preview').pause(); $('#video-preview').removeAttribute('src');
  if(videoURL){ URL.revokeObjectURL(videoURL); videoURL=null; }
  $('#save-hint').textContent=editing?'Lưu bản sửa · Lượt cũ giữ đầu vào riêng':'Lưu local · Có thể chỉnh sửa sau';
  $('#game-dialog').showModal(); $('#game-form').elements.name.focus();
}
async function openSavedAnswers(gameId) {
  savedDirty.clear();
  savedGameId=gameId;
  const game=state.games.find(g=>g.id===gameId);
  $('#saved-answers-title').textContent='Câu hỏi đã lưu · '+(game?.data.name || 'Game');
  $('#saved-answers-list').innerHTML='<div class="empty"><span class="spinner"></span></div>';
  errorAt('#saved-answers-error','');
  $('#saved-answers-dialog').showModal();
  try {
    savedEntries=(await api('/api/games/'+gameId+'/answers')).entries;
    renderSavedAnswers();
  } catch(error) { errorAt('#saved-answers-error',error.message); }
}
function renderSavedAnswers() {
  $('#saved-answers-list').innerHTML=savedEntries.length?savedEntries.map((entry,index)=>{
    const q=entry.question;
    return '<section class="saved-answer-card" data-saved-index="'+index+'"><span class="saved-kind">'+(q.kind==='object'?'ĐỐI TƯỢNG':'CÂU HỎI')+'</span><h3>'+esc(q.name || q.question_vi || q.question)+'</h3>'+(q.name?'<p>'+esc(q.question_vi || q.question)+'</p>':'')+'<label>Quyết định<select class="saved-decision"><option value="pending" '+(q.decision==='pending'?'selected':'')+'>Chưa chốt</option><option value="observed" '+(q.decision==='observed'?'selected':'')+'>Quan sát trong video (không tự dùng lại)</option><option value="confirmed" '+(q.decision==='confirmed'?'selected':'')+'>Tôi xác nhận</option><option value="excluded" '+(q.decision==='excluded'?'selected':'')+'>Bỏ khỏi bài</option></select></label><label>Câu trả lời đã chốt<textarea class="saved-answer" rows="3" maxlength="12000">'+esc(q.answer)+'</textarea></label><div class="saved-answer-footer"><small>Lưu '+date(entry.updated)+'</small><button class="button primary small" data-save-answer="'+index+'">Lưu thay đổi</button></div></section>';
  }).join(''):'<div class="empty"><h3>Chưa có câu hỏi đã lưu</h3><p>Câu trả lời được ghi nhớ sau khi bạn lưu ở một lượt viết bài.</p></div>';
}
async function saveStoredAnswer(index, button) {
  const entry=savedEntries[index], card=button.closest('.saved-answer-card');
  if(!entry||!card)return;
  button.disabled=true;errorAt('#saved-answers-error','');
  try {
    const result=await api('/api/games/'+savedGameId+'/answers/'+entry.key,{
      answer:$('.saved-answer',card).value,decision:$('.saved-decision',card).value,updated:entry.updated});
    savedEntries[index]=result.entry;savedDirty.delete(String(index));card.classList.remove('is-dirty');
    $('.saved-answer-footer small',card).textContent='Lưu '+date(result.entry.updated);
    button.disabled=false;toast('Đã lưu. Lượt chạy mới sẽ dùng câu trả lời này.');
  } catch(error) { errorAt('#saved-answers-error',error.message);button.disabled=false; }
}
function chooseVideo(file) {
  if (!file) return;
  if (!/\.(mp4|mov|mkv|webm|avi|m4v)$/i.test(file.name)) { errorAt('#form-error','Chọn file video MP4, MOV, MKV, WEBM, AVI hoặc M4V.'); return; }
  if(file.size>4*1024**3){errorAt('#form-error','Video vượt quá giới hạn 4 GB.');return;}
  selectedVideo=file; formDirty=true; errorAt('#form-error','');
  $('#drop-title').textContent=file.name; $('#drop-meta').textContent=bytes(file.size)+' · Bấm để thay video';
  if(videoURL) URL.revokeObjectURL(videoURL); videoURL=URL.createObjectURL(file);
  $('#video-preview').src=videoURL; $('#video-preview').classList.remove('hidden');
}
async function confirmAction(title,text,label='Xóa game') {
  const dialog=$('#confirm-dialog'); $('#confirm-title').textContent=title; $('#confirm-text').textContent=text; $('#confirm-ok').textContent=label;
  dialog.showModal();
  return await new Promise(resolve=>{
    const finish=value=>{dialog.close();$('#confirm-ok').onclick=null;$('#confirm-cancel').onclick=null;dialog.oncancel=null;resolve(value);};
    $('#confirm-ok').onclick=()=>finish(true); $('#confirm-cancel').onclick=()=>finish(false);
    dialog.oncancel=e=>{e.preventDefault();finish(false);};
  });
}
async function closeGame() {
  if(uploading) return;
  if(formDirty && !await confirmAction('Đóng mà chưa lưu?','Những thay đổi trong form này chưa được lưu.','Bỏ thay đổi')) return;
  $('#video-preview').pause(); $('#game-dialog').close();
}
function uploadGame(form) {
  return new Promise((resolve,reject)=>{
    const xhr=new XMLHttpRequest(); xhr.open('POST',editing?'/api/games/'+editing.id:'/api/games');
    xhr.setRequestHeader('X-Office-Token',token);
    xhr.upload.onprogress=e=>{if(e.lengthComputable){const percent=Math.round(e.loaded/e.total*100);$('#upload-progress').value=percent;$('#save-hint').textContent=percent===100?'Đang kiểm tra video và lưu game…':'Đang tải video lên local: '+percent+'%';}};
    xhr.onload=()=>{try{const data=JSON.parse(xhr.responseText);if(xhr.status<200||xhr.status>=300)reject(new Error(data.error));else resolve(data);}catch{reject(new Error('Máy chủ trả kết quả không hợp lệ.'));}};
    xhr.onerror=()=>reject(new Error('Mất kết nối khi tải video. Hãy thử lại.')); xhr.send(form);
  });
}
$('#game-form').addEventListener('submit',async e=>{
  e.preventDefault(); if(uploading) return; if(!selectedVideo&&!editing&&!importedBrief?.video_available){errorAt('#form-error','Hãy chọn video gameplay trước khi lưu.');$('#dropzone').focus();return;}
  const form=new FormData($('#game-form')); if(selectedVideo)form.append('video',selectedVideo);if(editing)form.append('revision',editing.revision);
  if(importedBrief?.video_available&&!selectedVideo)form.append('import_run',importedBrief.run_name);
  uploading=true; $('#save-game').disabled=true; $$('.close-game').forEach(b=>b.disabled=true); $('#upload-progress').classList.remove('hidden'); errorAt('#form-error','');
  try{await uploadGame(form);formDirty=false;$('#game-dialog').close();$('#video-preview').pause();toast(editing?'Đã lưu bản sửa. Lượt chạy cũ giữ nguyên đầu vào.':'Đã lưu game. Bạn có thể chạy viết bài.');await refresh();}
  catch(error){errorAt('#form-error',error.message);}
  finally{uploading=false;$('#save-game').disabled=false;$$('.close-game').forEach(b=>b.disabled=false);$('#upload-progress').classList.add('hidden');}
});

async function openJob(key) {
  selectedJob=key; details=null;questionDirty=false;tab='progress';errorAt('#job-error','');
  $('#job-title').textContent='Đang mở lượt chạy…';$('#job-content').innerHTML='<div class="empty"><span class="spinner"></span></div>';
  $('#job-dialog').showModal();try{await refreshJob(true);}catch(error){errorAt('#job-error',error.message);}
}
async function refreshJob(first=false) {
  const key=selectedJob; const next=await api('/api/jobs/'+key); if(key!==selectedJob)return;
  const oldStatus=details?.job.status; details=next;
  if(first || (oldStatus==='running' && next.job.status==='waiting'))tab=next.job.status==='waiting'?'questions':tab;
  $('#job-title').textContent=details.job.data.name; const execution=details.job.execution || details.job.data.execution || {};
  $('#job-subtitle').textContent='Lượt '+details.job.id.slice(0,8)+' · Đầu vào v'+details.job.revision+' · '+(execution.model || 'Model mặc định')+(execution.reasoning_effort?' / '+execution.reasoning_effort:'')+' · '+date(details.job.created);
  const status=details.job.status;
  const messages={running:'Đang xử lý bài viết. Bạn có thể đóng cửa sổ này và tiếp tục quản lý game.',stopping:'Đang dừng Codex, FFmpeg và các tiến trình của lượt này…',waiting:'AI cần bạn xác nhận thêm. Trả lời hoặc bỏ những chi tiết chưa rõ rồi chạy tiếp.',completed:'Đã hoàn tất hai bản Word. Bạn có thể tải về và duyệt nội dung.',stopped:'Đã dừng. Các bước hoàn tất được giữ lại để chạy tiếp.',failed:details.job.error || 'Lượt chạy gặp lỗi. Xem nhật ký và báo cáo QA.',interrupted:'Lượt chạy bị gián đoạn. Bạn có thể chạy tiếp từ dữ liệu đã lưu.'};
  messages.translating='Đang dịch các câu hỏi còn thiếu sang tiếng Việt. Bản dịch được lưu lại để dùng tiếp.';
  $('#job-banner').innerHTML='<div class="job-banner '+esc(status)+'">'+(activeState(status)?'<span class="spinner"></span>':icon(status==='completed'?'check':status==='waiting'?'question':'history'))+'<span>'+esc(messages[status] || status)+'</span></div>';
  const questions=details.questions.questions || [];
  $('#question-count').textContent=questions.filter(q=>q.decision==='pending').length || questions.length || '';
  if(!questionDirty && !busy) renderJobBody();
  if(details.question_translation?.status==='failed' && !activeState(status))errorAt('#job-error','Dịch câu hỏi: '+details.question_translation.error);
  renderJobActions();
}
function setTab(next) { tab=next;renderJobBody();renderJobActions(); }
function renderJobActions() {
  if(!details)return;
  const status=details.job.status, active=activeState(status), hasQuestions=!!details.questions.questions?.length || !!details.questions.state;
  let html='';
  if(active)html='<button class="button stop" data-job-action="stop" '+(status==='stopping'?'disabled':'')+'>'+icon('stop')+(status==='translating'?'Dừng dịch câu hỏi':'Dừng viết bài')+'</button>';
  else if(tab==='questions' && hasQuestions)html='<button class="button secondary" data-job-action="save">Lưu trả lời</button><button class="button primary" data-job-action="approve">'+icon('play')+'Lưu, duyệt & chạy tiếp</button>';
  else if(['waiting_for_capacity','queued'].includes(status))html='<button class="button secondary" data-job-action="stop">Hủy chờ quota</button>';
  else if(['waiting','failed','stopped','interrupted','cancelled'].includes(status))html=details.questions.state==='pending'?'<button class="button primary" data-job-action="questions">'+icon('question')+'Mở câu hỏi</button>':'<button class="button primary" data-job-action="resume">'+icon('play')+'Chạy tiếp</button>';
  $('#job-actions').innerHTML=html; $$('#job-actions button').forEach(b=>b.disabled=busy || (active&&status==='stopping'));
  $('#job-footer-note').textContent=questionDirty?'Có câu trả lời chưa lưu.':active?'Đóng cửa sổ này vẫn tiếp tục chạy.':'Chạy tiếp dùng đầu vào đã lưu của lượt này.';
}
function renderJobBody() {
  if(!details)return;
  $$('[data-tab]').forEach(b=>{const active=b.dataset.tab===tab;b.classList.toggle('active',active);b.setAttribute('aria-selected',String(active));});
  const {job}=details, active=activeState(job.status), content=$('#job-content');
  if(tab==='progress') {
    let stage=0; const marks=[['Extracting','analyze'],['Finding','notes'],['writing full'],['Deterministic','Repair round','QA after'],['Translating','translate'],['Exporting','SUCCESS']];
    const log=details.log || ''; let last=-1;
    marks.forEach((items,index)=>items.forEach(text=>{const position=log.lastIndexOf(text);if(position>last){stage=index;last=position;}}));
    if(job.status==='completed')stage=6;
    if(job.status==='waiting')stage=(log.includes('[4/7]')?2:1);
    const steps=['Phân tích video','Nguồn & xác nhận','Viết bài EN','Kiểm tra & sửa','Dịch sang VI','Xuất Word'];
    const result=details.files.length?'<div class="result-box"><div><h3>Hai ngôn ngữ. Một bài viết nhất quán.</h3><p>'+(job.status==='completed'?'Đã qua kiểm tra trước khi xuất.':'Các file Word đã xuất trước đó của lượt này.')+'</p></div>'+downloads(job.run_name,details.files)+'</div>':'';
    const qa=details.qa; let qaHTML='';
    if(qa && Object.keys(qa).length){const verdict=qa.overall_pass===true?'· Đạt':qa.overall_pass===false?'· Chưa đạt':qa.pass===true?'· QA cấu trúc đạt, chờ duyệt biên tập':'· Chưa đạt';qaHTML='<div class="qa-box"><h4>Kiểm tra bài viết '+verdict+'</h4>'+(qa.summary?'<span>'+Number(qa.summary.unique_sources || 0)+' nguồn · '+Number(qa.summary.source_mentions || 0)+' trích dẫn · '+Number(qa.summary.gameplay_images || 0)+' ảnh gameplay</span>':'')+((qa.issues || []).length?'<ul>'+qa.issues.map(i=>'<li>'+esc(i.message || i.code || JSON.stringify(i))+'</li>').join('')+'</ul>':'')+((qa.editorial_issues || []).filter(i=>i.severity==='error').map(i=>'<p>'+esc(i.message || i.reason || JSON.stringify(i))+'</p>').join(''))+'</div>';}
    const totals=details.usage.measured_totals || {}, usage=Object.keys(totals).length?'<span>'+esc(Number(totals.total_tokens || 0).toLocaleString('vi-VN'))+' token đã ghi nhận'+(details.usage.measurement_status==='partial'?' (chưa đủ)':'')+'</span>':'<span>Cập nhật tự động</span>';
    const quota=quotaSummary(details.quota),quotaHTML=quota?'<section class="quota-box"><h4>Hạn mức Codex toàn tài khoản</h4><div class="quota-grid">'+quota+'</div><p>Snapshot trước và sau các lượt gọi cho bài này. Mức tăng có thể gồm hoạt động Codex khác; khi cửa sổ reset, không tính mức tăng.</p></section>':details.quota?.samples?.length?'<section class="quota-box"><h4>Hạn mức Codex</h4><p>Chưa lấy được phần trăm 5 giờ hoặc tuần từ tài khoản.</p></section>':'<section class="quota-box"><h4>Usage 5 giờ / tuần</h4><p>Chưa có snapshot cho lượt này. Các lượt chạy mới sẽ tự lưu trước và sau khi gọi Codex.</p></section>';
    const oldScroll=$('.log-output')?.scrollTop || 0;
    const wasBottom=$('.log-output')?$('.log-output').scrollHeight-oldScroll-$('.log-output').clientHeight<40:true;
    content.innerHTML='<div class="progress-track">'+steps.map((label,index)=>'<div class="progress-step '+(index<stage?'done':index===stage?'current':'')+'">'+label+'</div>').join('')+'</div>'+result+(job.status==='waiting'?'<div class="notice warning">Đang chờ bạn trả lời. <button class="button secondary small" data-job-action="questions">Mở câu hỏi '+icon('arrow')+'</button></div>':'')+qaHTML+quotaHTML+'<div class="log-heading"><span>NHẬT KÝ LƯỢT CHẠY</span>'+usage+'</div><pre class="log-output">'+esc(log || 'Đang chuẩn bị…')+'</pre>';
    $('.log-output').scrollTop=wasBottom?$('.log-output').scrollHeight:oldScroll;
  } else if(tab==='questions') {
    const questions=details.questions.questions || [];
    if(!details.questions.state){content.innerHTML=empty('Chưa có câu hỏi','Sau khi phân tích video, AI sẽ liệt kê đối tượng và những điểm cần bạn xác nhận.');return;}
    const unresolved=questions.filter(q=>q.decision==='pending').length;
    const missingVi=questions.some(q=>['question','name','appearance','answer'].some(k=>q[k] && !q[k+'_vi']));
    content.innerHTML='<div class="question-toolbar"><div><h3>Thông tin đúng bắt đầu từ bạn</h3><p>'+questions.length+' mục · '+unresolved+' chưa chốt. Có thể bổ sung đối tượng AI bỏ sót.</p></div><div class="question-tools">'+(missingVi && state.settings.features?.question_translation?'<button class="button soft small" data-job-action="translate" '+(active?'disabled':'')+'>Dịch câu hỏi sang VI</button>':'')+'<button class="button secondary small" data-job-action="exclude" '+(active?'disabled':'')+'>Bỏ các mục chưa rõ</button></div></div><div class="notice info">“Xác nhận” = thông tin do bạn chốt. “Bỏ khỏi bài” = không đưa chi tiết đó vào nội dung. Với câu hỏi nhiều ý, ghi rõ các ý đã biết; AI sẽ bỏ phần còn thiếu.</div><fieldset '+(active?'disabled':'')+' id="question-fields">'+questions.map((q,index)=>{
      const options=q.kind==='object' && q.decision==='observed'?[['observed','Giữ điều thấy rõ trong video'],['pending','Chưa chốt'],['confirmed','Tôi xác nhận nội dung này'],['excluded','Bỏ chi tiết khỏi bài']]:[['pending','Chưa trả lời'],['confirmed','Tôi xác nhận nội dung này'],['excluded','Bỏ chi tiết khỏi bài']];
      const frames=(q.frame_ids || []).slice(0,4).map(frame=>'<a href="/api/jobs/'+job.id+'/frame/'+encodeURIComponent(frame)+'" target="_blank" rel="noopener"><img loading="lazy" src="/api/jobs/'+job.id+'/frame/'+encodeURIComponent(frame)+'" alt="Khung hình minh họa '+esc(q.name || '')+'"><small>'+esc(frame)+'</small></a>').join('');
      return '<section class="question-card" data-question="'+esc(q.id)+'"><div class="question-top"><strong>'+String(index+1).padStart(2,'0')+'. '+esc(q.name || 'Xác nhận thêm')+'</strong><select class="question-decision" aria-label="Trạng thái câu trả lời">'+options.map(([value,label])=>'<option value="'+value+'" '+(q.decision===value?'selected':'')+'>'+label+'</option>').join('')+'</select></div><div class="question-pair"><div><span>CÂU HỎI GỐC</span><p>'+esc(q.question)+'</p></div><div class="question-vietnamese"><span>TIẾNG VIỆT</span><p>'+esc(q.question_vi || 'Chưa có bản dịch. Bấm “Dịch câu hỏi sang VI” hoặc nhập bản dịch bên dưới.')+'</p></div></div><details class="question-edit"><summary>Chỉnh câu hỏi / bản dịch</summary><div class="two-columns"><label>Câu hỏi gốc<textarea data-field="question" rows="3" maxlength="12000">'+esc(q.question)+'</textarea></label><label>Bản dịch tiếng Việt<textarea data-field="question_vi" rows="3" maxlength="12000">'+esc(q.question_vi)+'</textarea></label></div></details>'+(q.kind==='object'?'<div class="two-columns"><label>Tên đối tượng<input data-field="name" value="'+esc(q.name)+'" maxlength="12000"></label><label>Hình dáng / dấu hiệu nhận biết<input data-field="appearance" value="'+esc(q.appearance)+'" maxlength="12000"></label></div>':'')+'<label>'+(q.kind==='object'?'Vai trò, cơ chế hoặc câu trả lời đã chốt':'Câu trả lời đã chốt')+'<textarea data-field="answer" rows="3" maxlength="12000" placeholder="Có thể trả lời bằng tiếng Việt…">'+esc(q.answer)+'</textarea></label>'+(frames?'<div class="question-frames">'+frames+'</div>':'')+'</section>';
    }).join('')+'<details class="manual-object"><summary>+ Bổ sung đối tượng hoặc luật chơi AI chưa liệt kê</summary><label>Tên<input id="manual-name" maxlength="160" placeholder="Ví dụ: Quy luật xóa hàng và cột"></label><label>Hình dáng (nếu có)<input id="manual-appearance" maxlength="2000"></label><label>Vai trò / cơ chế đã xác nhận<textarea id="manual-behavior" rows="3" maxlength="12000" placeholder="Lấp kín một hàng ngang hoặc cột dọc thì các ô biến mất…"></textarea></label><button class="button secondary" data-job-action="add-object">Lưu đối tượng mới</button></details></fieldset>';
    $$('.question-card',content).forEach(card=>{
      const q=questions.find(row=>row.id===card.dataset.question);
      for(const [field,label] of [['name','Tên đối tượng · Tiếng Việt'],['appearance','Hình dáng / dấu hiệu · Tiếng Việt'],['answer','Vai trò / câu trả lời đã chốt · Tiếng Việt']]){
        const original=card.querySelector('[data-field="'+field+'"]');
        if(!original)continue;
        const translated=document.createElement('label');translated.textContent=label;
        const input=document.createElement('textarea');input.dataset.field=field+'_vi';input.rows=field==='answer'?3:2;input.maxLength=12000;input.value=q[field+'_vi'] || '';input.placeholder='Chưa có bản dịch; bấm dịch hoặc nhập tiếng Việt tại đây.';
        translated.append(input);
        const pair=document.createElement('div');pair.className='two-columns';
        original.parentElement.replaceWith(pair);pair.append(original.parentElement || original,translated);
      }
    });
  } else if(tab==='input') {
    const fields={name:'Tên game',site_url:'Site game',game_url:'URL chơi game',video_name:'Video gameplay',idea_origin:'Ý tưởng & nguồn gốc',story:'Cốt truyện',game_style:'Phong cách game',controls_pc:'Điều khiển PC',controls_mobile:'Điều khiển điện thoại'};
    content.innerHTML='<div class="notice info">Đây là đầu vào v'+job.revision+' đã dùng cho lượt này. Sửa game trong thư viện sẽ áp dụng cho lượt mới.</div><dl class="input-summary"><div class="input-row"><dt>Model / suy luận</dt><dd>'+esc(executionLabel(job.execution || job.data.execution) || 'Theo cấu hình Codex lúc chạy')+'</dd></div>'+Object.entries(fields).map(([key,label])=>'<div class="input-row"><dt>'+label+'</dt><dd>'+esc(job.data[key] || 'Để AI phát triển ý tưởng')+'</dd></div>').join('')+'</dl>';
  } else {
    const history=details.answer_history || [];
    content.innerHTML=history.length?'<p class="muted">Mỗi lần lưu giữ cả nội dung cũ và mới. Mở một phiên bản để xem các câu trả lời đã lưu.</p>'+history.map((h,index)=>'<details class="answer-version"><summary>'+date(h.saved_at)+' · '+(h.after?.state==='approved'?'Đã duyệt':'Bản nháp')+(index===0?' · Mới nhất':'')+'</summary><pre>'+esc((h.after?.questions || []).map(q=>(q.name || q.question)+'\n'+({pending:'Chưa chốt',confirmed:'Đã xác nhận',excluded:'Bỏ khỏi bài',observed:'Quan sát video'}[q.decision] || '')+'\n'+(q.answer || '(chưa điền)')).join('\n\n'))+'</pre></details>').join(''):empty('Chưa có lịch sử trả lời','Các phiên bản câu trả lời sẽ được giữ lại mỗi khi bạn bấm lưu.');
  }
}
function collectAnswers() {
  return $$('.question-card').map(card=>{
    const result={id:card.dataset.question,decision:$('.question-decision',card).value};
    $$('[data-field]',card).forEach(input=>result[input.dataset.field]=input.value);
    return result;
  });
}
async function saveAnswers(approve) {
  const result=await api('/api/jobs/'+selectedJob+'/answers',{questions:collectAnswers(),approve,version:details.questions.version});
  details.questions=result.questions;
  questionDirty=false;
}
async function jobAction(action,button) {
  if(busy || !details)return;
  if(action==='questions'){setTab('questions');return;}
  if(action==='exclude'){
    $$('.question-decision').forEach(s=>{if(s.value==='pending')s.value='excluded';});questionDirty=true;renderJobActions();toast('Đã chọn bỏ các mục chưa rõ. Bấm lưu để áp dụng.');return;
  }
  busy=true;button.disabled=true;errorAt('#job-error','');
  try {
    if(action==='translate'){
      if(questionDirty)throw new Error('Lưu câu trả lời đang sửa trước khi dịch câu hỏi.');
      await api('/api/jobs/'+selectedJob+'/translate-questions',{});
    }
    if(['save','approve'].includes(action) && ['#manual-name','#manual-behavior','#manual-appearance'].some(id=>$(id)?.value.trim()))throw new Error('Bấm “Lưu đối tượng mới” để lưu phần bổ sung trước khi duyệt câu trả lời.');
    if(action==='stop')await api('/api/jobs/'+selectedJob+'/stop',{});
    if(action==='save'){await saveAnswers(false);toast('Đã lưu trả lời và lịch sử chỉnh sửa.');}
    if(action==='approve'){await saveAnswers(true);await api('/api/jobs/'+selectedJob+'/resume',{});tab='progress';toast('Đã duyệt. Workflow đang chạy tiếp.');}
    if(action==='resume'){await api('/api/jobs/'+selectedJob+'/resume',{});tab='progress';}
    if(action==='add-object'){
      const name=$('#manual-name').value,behavior=$('#manual-behavior').value,appearance=$('#manual-appearance').value;
      if(!name.trim()||!behavior.trim())throw new Error('Nhập tên và vai trò/cơ chế của đối tượng mới.');
      if(questionDirty)await saveAnswers(false);
      await api('/api/jobs/'+selectedJob+'/objects',{name,behavior,appearance});toast('Đã thêm đối tượng do bạn xác nhận.');
    }
  } catch(error){errorAt('#job-error',error.message);}
  finally{busy=false;await refreshJob().catch(error=>errorAt('#job-error',error.message));}
}
async function closeJob() {
  if(busy)return;
  if(questionDirty&&!await confirmAction('Câu trả lời chưa lưu','Đóng cửa sổ sẽ bỏ những chỉnh sửa chưa lưu.','Bỏ thay đổi'))return;
  selectedJob=null;details=null;questionDirty=false;$('#job-dialog').close();
}
document.addEventListener('click',async e=>{
  const nav=e.target.closest('[data-nav]');if(nav){navigate(nav.dataset.nav);return;}
  const action=e.target.closest('[data-action]');
  if(action && !action.disabled){
    const {id}=action.dataset;
    if(action.dataset.action==='new')openGame();
    if(action.dataset.action==='edit')openGame(id);
    if(action.dataset.action==='saved')await openSavedAnswers(id);
    if(action.dataset.action==='job')await openJob(id);
    if(action.dataset.action==='import'){
      action.disabled=true;try{openGame(null,await api('/api/runs/'+encodeURIComponent(id)+'/brief'));}catch(error){toast(error.message);}finally{action.disabled=false;}
    }
    if(action.dataset.action==='delete'){
      const game=state.games.find(g=>g.id===id);
      if(await confirmAction('Xóa '+game.data.name+'?','Game sẽ được gỡ khỏi thư viện. Các lượt chạy, video và file Word đã tạo vẫn được giữ trong máy.')){
        try{await api('/api/games/'+id,undefined,'DELETE');toast('Đã xóa game khỏi thư viện.');await refresh();}catch(error){toast(error.message);}
      }
    }
    if(action.dataset.action==='run'){
      action.dataset.requestKey ||= crypto.randomUUID();
      action.disabled=true;try{const result=await api('/api/games/'+id+'/run',{...selectedExecution(),idempotency_key:action.dataset.requestKey});await refresh();await openJob(result.job.id);}catch(error){toast(error.message);action.disabled=false;}
    }
  }
  const jobButton=e.target.closest('[data-job-action]');if(jobButton&&!jobButton.disabled)await jobAction(jobButton.dataset.jobAction,jobButton);
  const tabButton=e.target.closest('[data-tab]');if(tabButton){if(questionDirty && tab!=='questions')return;if(questionDirty && tabButton.dataset.tab!=='questions'){toast('Hãy lưu câu trả lời trước khi chuyển tab.');return;}setTab(tabButton.dataset.tab);}
});
$('#new-game').onclick=()=>openGame();
$('#search').oninput=renderCollection;$('#status-filter').onchange=renderCollection;
$('#run-model').onchange=()=>{remember('office-model',$('#run-model').value);updateEfforts();};
$('#run-effort').onchange=()=>remember('office-effort',$('#run-effort').value);
$('#custom-model').oninput=()=>remember('office-custom-model',$('#custom-model').value);
$('#video-input').onchange=e=>chooseVideo(e.target.files[0]);
$('#dropzone').onclick=()=>{if(!uploading)$('#video-input').click();};
$('#dropzone').onkeydown=e=>{if(['Enter',' '].includes(e.key)){e.preventDefault();$('#video-input').click();}};
for(const type of ['dragenter','dragover'])$('#dropzone').addEventListener(type,e=>{e.preventDefault();$('#dropzone').classList.add('dragging');});
for(const type of ['dragleave','drop'])$('#dropzone').addEventListener(type,e=>{e.preventDefault();$('#dropzone').classList.remove('dragging');if(type==='drop'&&!uploading)chooseVideo(e.dataTransfer.files[0]);});
$('#game-form').addEventListener('input',()=>formDirty=true);
$$('.close-game').forEach(button=>button.onclick=closeGame);
$('#game-dialog').addEventListener('cancel',e=>{e.preventDefault();closeGame();});
$('#close-job').onclick=closeJob;$('#job-dialog').addEventListener('cancel',e=>{e.preventDefault();closeJob();});
async function closeSavedAnswers(){
  if(savedDirty.size && !await confirmAction('Câu trả lời chưa lưu','Các chỉnh sửa chưa lưu sẽ bị bỏ khi đóng cửa sổ.','Bỏ thay đổi'))return;
  savedDirty.clear();$('#saved-answers-dialog').close();
}
$('#close-saved-answers').onclick=closeSavedAnswers;
$('#saved-answers-dialog').addEventListener('cancel',e=>{e.preventDefault();closeSavedAnswers();});
for(const event of ['input','change'])$('#saved-answers-list').addEventListener(event,e=>{
  const card=e.target.closest('[data-saved-index]');if(card){savedDirty.add(card.dataset.savedIndex);card.classList.add('is-dirty');}
});
$('#saved-answers-dialog').addEventListener('click',e=>{const button=e.target.closest('[data-save-answer]');if(button)saveStoredAnswer(Number(button.dataset.saveAnswer),button);});
for(const event of ['input','change'])$('#job-content').addEventListener(event,e=>{if(e.target.closest('.question-card, .manual-object')){questionDirty=true;renderJobActions();}});
window.addEventListener('beforeunload',e=>{if(formDirty&&$('#game-dialog').open || questionDirty || uploading || savedDirty.size){e.preventDefault();e.returnValue='';}});
refresh();setInterval(refresh,3000);
