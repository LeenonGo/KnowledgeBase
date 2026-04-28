/**
 * 登录页
 */
const PageLogin = (() => {
  function init() {
    // 自动填充测试账号（仅开发环境）
    const userEl = document.getElementById('login-user');
    if (userEl && !userEl.value) userEl.value = 'admin';
  }

  async function doLogin() {
    const user = document.getElementById('login-user').value.trim();
    const pass = document.getElementById('login-pass').value.trim();
    if (!user || !pass) { alert('请输入用户名和密码'); return; }
    try {
      const data = await API.request('/api/login', {
        method: 'POST',
        body: { username: user, password: pass },
      });
      localStorage.setItem('kb_token', data.token);
      localStorage.setItem('kb_user', JSON.stringify(data.user));
      // 刷新页面确保所有状态完全重置
      window.location.reload();
    } catch (e) {
      alert(e.message);
    }
  }

  function showApp() {
    document.getElementById('login').style.display = 'none';
    document.getElementById('sidebar').style.display = 'block';
    document.getElementById('top-header').style.display = 'flex';
    document.body.classList.add('has-header');
    const user = API.getUser();
    const label = (user.display_name || user.username || 'U')[0].toUpperCase();
    const name = user.display_name || user.username || '';
    const role = user.role || '';
    document.getElementById('header-avatar').textContent = label;
    document.getElementById('header-username').textContent = name;
    document.getElementById('header-role').textContent = role;
    document.getElementById('dropdown-avatar').textContent = label;
    document.getElementById('dropdown-name').textContent = name;
    document.getElementById('dropdown-role').textContent = role;
    applyRoleAccess(user.role);
    Router.enterApp();
  }

  function applyRoleAccess(role) {
    const isAdmin = role === 'super_admin';
    ['menu-users', 'menu-depts', 'menu-perms', 'menu-config', 'menu-quality', 'menu-audit', 'menu-eval'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.style.display = isAdmin ? 'block' : 'none';
    });
    document.querySelectorAll('.kb-admin-only').forEach(el => el.style.display = isAdmin ? '' : 'none');
    document.querySelectorAll('.kb-edit-only').forEach(el => el.style.display = (isAdmin || role === 'kb_admin') ? '' : 'none');
  }

  function logout() {
    API.clearAuth();
    if (typeof PageQA !== 'undefined' && PageQA.reset) PageQA.reset();
    document.getElementById('sidebar').style.display = 'none';
    document.getElementById('top-header').style.display = 'none';
    document.body.classList.remove('has-header');
    document.getElementById('login').style.display = 'flex';
    const dd = document.getElementById('user-dropdown');
    if (dd) dd.style.display = 'none';
    Router.navigate('login');
  }

  return { init, doLogin, showApp, logout, applyRoleAccess };
})();

// 注册路由
Router.on('login', () => {
  document.getElementById('sidebar').style.display = 'none';
  const th = document.getElementById('top-header');
  if (th) th.style.display = 'none';
  document.getElementById('login').style.display = 'flex';
});

/* ===== 用户下拉菜单 ===== */
function toggleUserDropdown() {
  const dd = document.getElementById('user-dropdown');
  dd.style.display = dd.style.display === 'none' ? 'block' : 'none';
}
// 点击外部关闭下拉
document.addEventListener('click', e => {
  const wrap = document.getElementById('user-avatar-wrap');
  const dd = document.getElementById('user-dropdown');
  if (wrap && dd && !wrap.contains(e.target) && !dd.contains(e.target)) {
    dd.style.display = 'none';
}
});

/* ===== 密码复杂度校验 ===== */
function validatePassword(pw) {
  if (pw.length < 8) return '密码至少需要 8 位';
  if (!/[a-zA-Z]/.test(pw)) return '密码需包含字母';
  if (!/[0-9]/.test(pw)) return '密码需包含数字';
  return '';
}

function checkPasswordStrength(pw) {
  const el = document.getElementById('cp-strength');
  if (!el) return;
  if (!pw) { el.innerHTML = ''; return; }
  const err = validatePassword(pw);
  if (err) {
    el.innerHTML = '<span style="color:#ff4d4f;">✗ ' + err + '</span>';
  } else {
    let level = '弱', color = '#fa8c16';
    if (pw.length >= 12 && /[a-zA-Z].*[0-9]|[0-9].*[a-zA-Z]/.test(pw) && /[^a-zA-Z0-9]/.test(pw)) { level = '强'; color = '#52c41a'; }
    else if (pw.length >= 10) { level = '中'; color = '#1890ff'; }
    el.innerHTML = '<span style="color:' + color + ';">✓ 密码合规 · 强度: ' + level + '</span>';
  }
}

/* ===== 修改密码 ===== */
function showChangePasswordModal() {
  document.getElementById('user-dropdown').style.display = 'none';
  document.getElementById('cp-old-password').value = '';
  document.getElementById('cp-new-password').value = '';
  document.getElementById('cp-confirm-password').value = '';
  document.getElementById('cp-strength').innerHTML = '';
  UI.showModal('change-password');
}

async function doChangePassword() {
  const oldPw = document.getElementById('cp-old-password').value;
  const newPw = document.getElementById('cp-new-password').value;
  const confirmPw = document.getElementById('cp-confirm-password').value;
  if (!oldPw) { alert('请输入当前密码'); return; }
  const err = validatePassword(newPw);
  if (err) { alert(err); return; }
  if (newPw !== confirmPw) { alert('两次输入的新密码不一致'); return; }
  if (oldPw === newPw) { alert('新密码不能与当前密码相同'); return; }
  try {
    await API.request('/api/change-password', {
      method: 'POST',
      body: { old_password: oldPw, new_password: newPw },
    });
    UI.hideModal();
    alert('密码修改成功，请重新登录');
    PageLogin.logout();
  } catch (e) {
    alert(e.message);
  }
}
