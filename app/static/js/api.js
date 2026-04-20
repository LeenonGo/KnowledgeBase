/**
 * API 封装 — 统一 Token 注入、错误处理、401 拦截
 */
const API = (() => {
  const _origFetch = window.fetch.bind(window);

  function getToken() {
    return localStorage.getItem('kb_token');
  }

  function getUser() {
    try { return JSON.parse(localStorage.getItem('kb_user') || '{}'); }
    catch { return {}; }
  }

  function clearAuth() {
    localStorage.removeItem('kb_token');
    localStorage.removeItem('kb_user');
  }

  /** 带 Token 的 fetch */
  async function request(url, opts = {}) {
    opts.headers = opts.headers || {};
    const token = getToken();
    if (token && url.startsWith('/api/') && !url.startsWith('/api/login')) {
      opts.headers['Authorization'] = 'Bearer ' + token;
    }
    if (opts.body && typeof opts.body === 'object' && !(opts.body instanceof FormData)) {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(opts.body);
    }
    const res = await _origFetch(url, opts);
    if (res.status === 401 && !url.includes('/api/login')) {
      clearAuth();
      Router.navigate('login');
      throw new Error('未登录或 Token 已过期');
    }
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `请求失败 (${res.status})`);
    }
    return res.json();
  }

  /** 带上传进度的 XHR（用于文件上传） */
  function upload(fd, onProgress) {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open('POST', '/api/upload');
      const token = getToken();
      if (token) xhr.setRequestHeader('Authorization', 'Bearer ' + token);
      if (onProgress) {
        xhr.upload.onprogress = e => {
          if (e.lengthComputable) onProgress(Math.round(e.loaded / e.total * 100));
        };
      }
      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(JSON.parse(xhr.responseText));
        } else {
          try { reject(new Error(JSON.parse(xhr.responseText).detail || xhr.statusText)); }
          catch { reject(new Error(xhr.statusText)); }
        }
      };
      xhr.onerror = () => reject(new Error('网络错误'));
      xhr.send(fd);
    });
  }

  return { request, upload, getToken, getUser, clearAuth };
})();
