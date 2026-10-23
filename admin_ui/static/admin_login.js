'use strict';
document.getElementById('admin-login-form').onsubmit = async event => {
  event.preventDefault();
  const error = document.getElementById('login-error');
  const password = document.getElementById('admin-password').value;
  const confirm = document.getElementById('admin-confirm');
  const button = event.target.querySelector('button');
  error.classList.add('hidden');
  if (confirm && confirm.value !== password) {
    error.textContent = 'Hai mật khẩu chưa khớp.'; error.classList.remove('hidden'); return;
  }
  button.disabled = true;
  try {
    const configured = document.querySelector('meta[name=admin-configured]').content === 'yes';
    const response = await fetch('/admin/auth/' + (configured ? 'login' : 'setup'), {
      method:'POST',headers:{'Content-Type':'application/json','X-Office-Token':document.querySelector('meta[name=office-token]').content},
      body:JSON.stringify({password})});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Không đăng nhập được.');
    location.assign('/admin');
  } catch (e) { error.textContent=e.message; error.classList.remove('hidden'); }
  finally { button.disabled=false; }
};
