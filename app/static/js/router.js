/**
 * Hash Router — 基于 URL hash 的前端路由
 *
 * 用法:
 *   Router.navigate('dashboard')  →  #/dashboard
 *   Router.navigate('kb-detail', { id: 'abc' })  →  #/kb-detail?id=abc
 *   Router.on('kb-detail', (params) => { ... })
 */
const Router = (() => {
  const routes = new Map();
  let currentScreen = null;

  /** 注册路由回调 */
  function on(screenName, handler) {
    routes.set(screenName, handler);
  }

  /** 导航到指定页面 */
  function navigate(screenName, params = {}) {
    const query = new URLSearchParams(params).toString();
    window.location.hash = query ? `/${screenName}?${query}` : `/${screenName}`;
  }

  /** 解析当前 hash */
  function parseHash() {
    const hash = window.location.hash.slice(1) || '/login';
    const [path, qs] = hash.split('?');
    const screenName = path.replace(/^\//, '');
    const params = Object.fromEntries(new URLSearchParams(qs || ''));
    return { screenName, params };
  }

  /** 执行路由切换 */
  function resolve() {
    const { screenName, params } = parseHash();

    // 隐藏所有 screen
    document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));

    // 显示目标 screen
    const target = document.getElementById(screenName);
    if (target) {
      target.classList.add('active');
    }

    // 侧边栏高亮
    document.querySelectorAll('.sidebar a').forEach(a => a.classList.remove('active'));
    const navMap = {
      'dashboard': '仪表盘', 'kb-list': '知识库列表', 'kb-detail': '知识库列表',
      'doc-upload': '知识库列表', 'qa-chat': '智能问答', 'user-mgmt': '用户管理',
      'dept-tree': '部门管理', 'perm-mgmt': '权限管理', 'audit-log': '审计日志',
      'quality': '质量监控', 'evaluation': '效果评测', 'sys-config': '系统配置',
    };
    const label = navMap[screenName];
    if (label) {
      const link = Array.from(document.querySelectorAll('.sidebar a')).find(a => a.textContent.includes(label));
      if (link) link.classList.add('active');
    }

    currentScreen = screenName;

    // 调用注册的回调
    const handler = routes.get(screenName);
    if (handler) handler(params);
  }

  /** 检查登录状态，未登录则跳转 login */
  function requireAuth() {
    if (!API.getToken()) {
      navigate('login');
      return false;
    }
    return true;
  }

  // 监听 hash 变化
  window.addEventListener('hashchange', resolve);

  // 登录后进入 app
  function enterApp() {
    if (!document.location.hash || document.location.hash === '#/login') {
      navigate('dashboard');
    } else {
      resolve();
    }
  }

  return { on, navigate, resolve, requireAuth, enterApp, getCurrent: () => currentScreen };
})();
