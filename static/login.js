'use strict';
const el = id => document.getElementById(id);
let creatingOwner = false;
const submit = el('submit-button');
function message(text, success = false) {
  el('form-message').textContent = text;
  el('form-message').classList.toggle('ok', success);
}
async function request(path, body) {
  const res = await fetch(path, {
    method: body ? 'POST' : 'GET', credentials: 'same-origin', cache: 'no-store',
    headers: body ? {'Content-Type': 'application/json'} : {},
    body: body ? JSON.stringify(body) : undefined
  });
  const result = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Không thể kết nối máy chủ.');
  return result;
}
async function initialize() {
  try {
    const config = await request('/api/auth/config');
    const googleLink = el('google-login');
    if (config.google_login_available) {
      googleLink.classList.remove('disabled');
      googleLink.removeAttribute('aria-disabled');
      googleLink.removeAttribute('tabindex');
      el('google-help').textContent = 'Dùng tài khoản Google đã được cấp quyền chủ sở hữu.';
    } else {
      googleLink.addEventListener('click', e => e.preventDefault());
      el('google-help').textContent = 'Google chưa được cấu hình: cần Client ID và Client Secret ở Render.';
    }
    creatingOwner = config.setup_required;
    if (creatingOwner) {
      el('form-category').textContent = 'THIẾT LẬP CHỦ SỞ HỮU';
      el('form-title').textContent = 'Tạo không gian của bạn.';
      el('form-desc').textContent = 'Tạo tài khoản chủ sở hữu đầu tiên. Đăng ký sẽ tự động khóa sau bước này.';
      el('password-hint').textContent = 'Tối thiểu 12 ký tự';
      el('password').setAttribute('autocomplete', 'new-password');
      el('confirm-wrap').classList.remove('hidden');
      el('confirm-password').required = true;
      el('setup-wrap').classList.toggle('hidden', !config.setup_token_required);
      el('submit-label').textContent = 'Tạo tài khoản & vào studio';
      if (!config.local_setup_allowed && !config.setup_token_required) {
        submit.disabled = true;
        message('Thiết lập tài khoản đầu tiên chỉ được phép trên localhost. Nếu chạy trên server, hãy đặt VIETFRAME_SETUP_TOKEN.');
      }
    }
  } catch(err) { submit.disabled = true; message(err.message); }
}
el('toggle-password').addEventListener('click', () => {
  const shown = el('password').type === 'text';
  el('password').type = shown ? 'password' : 'text';
  el('toggle-password').textContent = shown ? 'Hiện' : 'Ẩn';
  el('toggle-password').setAttribute('aria-pressed', String(!shown));
});
el('auth-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  if (submit.disabled) return;
  const email = el('email').value.trim();
  const password = el('password').value;
  if (!el('email').checkValidity()) return message('Hãy nhập địa chỉ email hợp lệ.');
  if (password.length < 12) return message('Mật khẩu cần ít nhất 12 ký tự.');
  if (creatingOwner && password !== el('confirm-password').value) return message('Hai mật khẩu chưa giống nhau.');
  submit.disabled = true;
  message('Đang xác thực…', true);
  try {
    const payload = {email, password};
    if (creatingOwner) payload.setup_token = el('setup-token').value.trim();
    await request(creatingOwner ? '/api/auth/setup' : '/api/auth/login', payload);
    window.location.replace('/');
  } catch(err) {
    message(err.message);
    submit.disabled = false;
  }
});
document.addEventListener('DOMContentLoaded', () => {
  const codes = {
    not_configured: 'Google chưa được cấu hình. Cần Client ID và Client Secret trong Render.',
    invalid_state: 'Phiên Google không hợp lệ hoặc đã hết hạn. Vui lòng thử lại.',
    rejected: 'Google không xác minh được tài khoản chủ sở hữu. Kiểm tra email và ứng dụng OAuth.',
    unavailable: 'Tạm thời không kết nối được Google. Vui lòng thử lại.',
    cancelled: 'Bạn đã hủy đăng nhập Google.'
  };
  const code = new URLSearchParams(location.search).get('google_error');
  if (code && codes[code]) message(codes[code]);
  initialize();
});
