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
      showApp();
    } catch (e) {
      alert(e.message);
    }
  }

  function showApp() {
    document.getElementById('login').style.display = 'none';
    document.getElementById('sidebar').style.display = 'block';
    const user = API.getUser();
    const el = document.getElementById('current-user');
    if (el) el.textContent = (user.display_name || user.username || '') + ' [' + (user.role || '') + ']';
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
    document.getElementById('sidebar').style.display = 'none';
    document.getElementById('login').style.display = 'flex';
    Router.navigate('login');
  }

  return { init, doLogin, showApp, logout, applyRoleAccess };
})();

// 注册路由
Router.on('login', () => {
  document.getElementById('sidebar').style.display = 'none';
  document.getElementById('login').style.display = 'flex';
});
