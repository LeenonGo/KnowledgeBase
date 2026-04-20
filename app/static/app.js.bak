// ─── Token 管理 + 全局 fetch 拦截 ──────────────
(function() {
  const _origFetch = window.fetch;
  window.fetch = function(url, opts) {
    opts = opts || {};
    opts.headers = opts.headers || {};
    // 只拦截 /api/ 请求，登录接口除外
    if(typeof url === 'string' && url.startsWith('/api/') && !url.startsWith('/api/login')) {
      const token = localStorage.getItem('kb_token');
      if(token) {
        if(opts.headers instanceof Headers) {
          opts.headers.set('Authorization', 'Bearer ' + token);
        } else {
          opts.headers['Authorization'] = 'Bearer ' + token;
        }
      }
    }
    // XMLHttpRequest 也要处理（上传用的 xhr）
    return _origFetch.call(this, url, opts).then(res => {
      if(res.status === 401 && !url.toString().includes('/api/login')) {
        localStorage.removeItem('kb_token');
        localStorage.removeItem('kb_user');
        document.getElementById('sidebar').style.display = 'none';
        document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
        document.getElementById('login').style.display = 'flex';
        document.getElementById('login').classList.add('active');
      }
      return res;
    });
  };
  // 拦截 XMLHttpRequest（上传接口）
  const _origOpen = XMLHttpRequest.prototype.open;
  const _origSend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function(method, url) {
    this._url = url;
    return _origOpen.apply(this, arguments);
  };
  XMLHttpRequest.prototype.send = function(body) {
    if(this._url && this._url.startsWith('/api/')) {
      const token = localStorage.getItem('kb_token');
      if(token) this.setRequestHeader('Authorization', 'Bearer ' + token);
    }
    return _origSend.apply(this, arguments);
  };
})();

let currentKbId = null;
let currentKbRole = null;
let kbPage = 1, userPage = 1, docPage = 1, auditPage = 1;
// ─── 分页组件 ───────────────────────────────────
function renderPagination(containerId, total, page, pageSize, onPageChange) {
  const container = document.getElementById(containerId);
  if(!container) return;
  const totalPages = Math.ceil(total / pageSize);
  if(totalPages <= 1) { container.innerHTML = ''; return; }
  let html = '<div class="pagination">';
  if(page > 1) html += '<div class="page-btn" onclick="'+onPageChange+'('+(page-1)+')">‹</div>';
  for(let p = 1; p <= totalPages; p++) {
    if(p === page) html += '<div class="page-btn active">'+p+'</div>';
    else if(Math.abs(p - page) <= 2 || p === 1 || p === totalPages) html += '<div class="page-btn" onclick="'+onPageChange+'('+p+')">'+p+'</div>';
    else if(Math.abs(p - page) === 3) html += '<div class="page-btn">...</div>';
  }
  if(page < totalPages) html += '<div class="page-btn" onclick="'+onPageChange+'('+(page+1)+')">›</div>';
  html += '</div>';
  container.innerHTML = html;
}

let kbList = []; // 缓存知识库列表
let deptList = []; // 缓存部门列表
let userList = []; // 缓存用户列表

// ─── Navigation ─────────────────────────────────
function nav(screenName) {
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  document.getElementById(screenName).classList.add('active');
  // Sidebar highlight
  document.querySelectorAll('.sidebar a').forEach(a => a.classList.remove('active'));
  const navMap = {
    'dashboard':'仪表盘','kb-list':'知识库列表','kb-detail':'知识库列表',
    'doc-upload':'知识库列表','qa-chat':'智能问答','user-mgmt':'用户管理',
    'dept-tree':'部门管理','perm-mgmt':'权限管理','audit-log':'审计日志',
    'quality':'质量监控','sys-config':'系统配置'
  };
  const label = navMap[screenName];
  if(label) {
    const link = Array.from(document.querySelectorAll('.sidebar a')).find(a => a.textContent.includes(label));
    if(link) link.classList.add('active');
  }
  // 页面切换时加载数据
  if(screenName === 'kb-list') loadKBList();
  if(screenName === 'kb-detail') loadKBDocs();
  if(screenName === 'dashboard') loadDashboard();
  if(screenName === 'user-mgmt') loadUserList();
  if(screenName === 'dept-tree') loadDeptTree();
  if(screenName === 'audit-log') loadAuditLogs();
}

// ─── 审计日志 ───────────────────────────────────
async function loadAuditLogs(page) {
  auditPage = page || 1;
  const action = document.getElementById('audit-action-filter').value;
  let url = '/api/audit-logs?page='+auditPage+'&page_size=20';
  if(action) url += '&action=' + action;
  try {
    const data = await fetch(url).then(r => r.json());
    const logs = data.items || [];
    const tbody = document.getElementById('audit-log-body');
    document.getElementById('audit-count').textContent = data.total + ' 条记录';
    renderPagination('audit-pagination', data.total, auditPage, 20, 'loadAuditLogs');
    if(!logs.length) {
      tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:40px;color:#999;">暂无数据</td></tr>';
      return;
    }
    const actionLabels = {login:'登录',upload:'上传',delete_doc:'删除文档',query:'查询',create_kb:'创建知识库',delete_kb:'删除知识库',create_user:'创建用户',delete_user:'删除用户',config_models:'配置模型',reindex:'重建索引',create_dept:'创建部门',delete_dept:'删除部门'};
    tbody.innerHTML = logs.map(l => {
      const time = l.created_at ? l.created_at.replace('T',' ').substring(0,19) : '';
      const actionLabel = actionLabels[l.action] || l.action;
      const statusTag = l.status === 'success' ? '<span class="tag tag-green">成功</span>' : '<span class="tag tag-red">失败</span>';
      return '<tr><td>'+time+'</td><td>'+l.username+'</td><td>'+l.ip_address+'</td><td>'+actionLabel+'</td><td>'+l.resource+'</td><td>'+(l.detail||'')+'</td><td>'+statusTag+'</td></tr>';
    }).join('');
  } catch(e) {
    console.error('加载审计日志失败', e);
  }
}

// ─── 权限管理 ───────────────────────────────────





function switchTab(tab, tabId) {
  tab.parentElement.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  tab.classList.add('active');
  // 隐藏同组的所有 panel
  const panels = tab.parentElement.parentElement.querySelectorAll(':scope > div[id]');
  panels.forEach(el => {
    if(el.id && el.id.includes('-tab-')) el.style.display = 'none';
  });
  document.getElementById(tabId).style.display = 'block';
  // 加载配置
  if(tabId === 'config-tab-model') loadModelConfig();
  // KB详情Tab数据加载
  if(tabId === 'kb-tab-settings') loadKBSettings();
}

// ─── Login ──────────────────────────────────────
async function doLogin() {
  const user = document.getElementById('login-user').value.trim();
  const pass = document.getElementById('login-pass').value.trim();
  if(!user || !pass) { alert('请输入用户名和密码'); return; }
  try {
    const res = await fetch('/api/login', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({username: user, password: pass}),
    });
    if(!res.ok) {
      const err = await res.json();
      alert(err.detail || '登录失败');
      return;
    }
    const data = await res.json();
    localStorage.setItem('kb_token', data.token);
    localStorage.setItem('kb_user', JSON.stringify(data.user));
    showApp();
  } catch(e) {
    alert('网络错误: ' + e.message);
  }
}

function showApp() {
  document.getElementById('login').style.display = 'none';
  document.getElementById('sidebar').style.display = 'block';
  const user = JSON.parse(localStorage.getItem('kb_user') || '{}');
  const el = document.getElementById('current-user');
  if(el) el.textContent = (user.display_name || user.username || '') + ' [' + (user.role || '') + ']';
  applyRoleAccess(user.role);
  nav('dashboard');
}

function applyRoleAccess(role) {
  const isAdmin = role === 'super_admin';
  const adminMenus = ['menu-users', 'menu-depts', 'menu-perms', 'menu-config', 'menu-quality'];
  adminMenus.forEach(id => {
    const el = document.getElementById(id);
    if(el) el.style.display = isAdmin ? 'block' : 'none';
  });
  // kb_admin 和 user 隐藏管理类按钮
  document.querySelectorAll('.kb-admin-only').forEach(el => el.style.display = isAdmin ? '' : 'none');
  document.querySelectorAll('.kb-edit-only').forEach(el => el.style.display = (isAdmin || role === 'kb_admin') ? '' : 'none');
}
function logout() {
  localStorage.removeItem('kb_token');
  localStorage.removeItem('kb_user');
  document.getElementById('sidebar').style.display = 'none';
  document.getElementById("login").style.display = "flex";
  nav('login');
}

// ─── Dashboard ──────────────────────────────────
async function loadDashboard() {
  try {
    const [docData, kbData] = await Promise.all([
      fetch('/api/documents?page=1&page_size=1').then(r => r.json()),
      fetch('/api/knowledge-bases?page=1&page_size=5').then(r => r.json())
    ]);
    const totalDocs = docData.total || 0;
    const totalKbs = kbData.total || 0;
    const kbs = kbData.items || [];
    document.getElementById('stat-docs').textContent = totalDocs;
    document.getElementById('stat-kb').textContent = totalKbs;
    document.getElementById('kb-total').textContent = totalKbs;
    const hotEl = document.getElementById('hot-kb-list');
    if(!kbs.length) {
      hotEl.innerHTML = '<div class="text-muted" style="padding:20px;text-align:center;">暂无知识库</div>';
    } else {
      hotEl.innerHTML = kbs.map(k =>
        '<div class="flex-between" style="padding:8px;border-bottom:1px solid #f5f5f5;">'
        + '<span>📖 '+k.name+'</span>'
        + '<span class="tag tag-blue">活跃</span></div>'
      ).join('');
    }
  } catch(e) { console.error('Dashboard error:', e); }
}

// ─── Departments API ────────────────────────────
async function loadDepts() {
  try { deptList = await fetch('/api/departments').then(r => r.json()); }
  catch(e) { deptList = []; }
  return deptList;
}

async function loadDeptTree() {
  const depts = await loadDepts();
  const card = document.querySelector('#dept-tree .card');
  if(!depts.length) {
    card.innerHTML = '<div class="text-muted" style="text-align:center;padding:40px;">暂无部门</div>';
    return;
  }
  // 构建树形结构
  const root = depts.find(d => !d.parent_id);
  const children = depts.filter(d => d.parent_id);
  let html = '';
  if(root) {
    html += '<div class="tree-item" style="padding-left:8px;">'
      + '<div class="node">🏢 <strong>'+root.name+'</strong> <span class="text-muted">'+root.path+'</span></div>';
    children.forEach(c => {
      html += '<div class="tree-item" style="padding-left:32px;">'
        + '<div class="node">📂 '+c.name+' <span class="text-muted">'+c.path+'</span></div></div>';
    });
    html += '</div>';
  }
  card.innerHTML = html;
}

function fillDeptSelect(selectId, selectedId) {
  const sel = document.getElementById(selectId);
  if(!sel) return;
  sel.innerHTML = '<option value="">-- 无 --</option>' + deptList.map(d => '<option value="'+d.id+'"'+(d.id===selectedId?' selected':'')+'>'+d.name+'</option>').join('');
}

// ─── Users API ──────────────────────────────────
async function loadUsers(page) {
  userPage = page || 1;
  try { const data = await fetch('/api/users?page='+userPage+'&page_size=10').then(r => r.json()); userList = data.items || []; return userList; }
  catch(e) { userList = []; return []; }
}

let allUsers = [];

async function loadUserList(page) {
  userPage = page || 1;
  allUsers = await loadUsers(userPage);
  // 填充部门筛选下拉
  await loadDepts();
  const deptSel = document.getElementById('user-dept-filter');
  if(deptSel) {
    deptSel.innerHTML = '<option value="">全部部门</option>' + deptList.map(d => '<option value="'+d.id+'">'+d.name+'</option>').join('');
  }
  filterUsers();
  // pagination
  try { const data = await fetch('/api/users?page='+userPage+'&page_size=10').then(r=>r.json()); renderPagination('user-pagination', data.total, userPage, 10, 'loadUserList'); } catch(e) {}
}

function filterUsers() {
  const keyword = (document.getElementById('user-search')?.value || '').trim().toLowerCase();
  const roleFilter = document.getElementById('user-role-filter')?.value || '';
  const statusFilter = document.getElementById('user-status-filter')?.value || '';
  const deptFilter = document.getElementById('user-dept-filter')?.value || '';
  let filtered = allUsers;
  if(keyword) filtered = filtered.filter(u => u.username.toLowerCase().includes(keyword) || u.display_name.toLowerCase().includes(keyword));
  if(roleFilter) filtered = filtered.filter(u => u.role === roleFilter);
  if(statusFilter) filtered = filtered.filter(u => u.status === statusFilter);
  if(deptFilter) filtered = filtered.filter(u => u.department_id === deptFilter);
  const tbody = document.getElementById('user-table-body');
  document.getElementById('user-count').textContent = filtered.length + ' 人';
  if(!filtered.length) {
    tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:40px;color:#999;">暂无用户</td></tr>';
    return;
  }
  const avatarColors = ['#1890ff','#52c41a','#fa8c16','#eb2f96','#722ed1','#13c2c2'];
  tbody.innerHTML = filtered.map((u, i) => {
    const color = avatarColors[i % avatarColors.length];
    const roleTag = u.role === 'super_admin' ? 'tag-purple' : u.role === 'kb_admin' ? 'tag-blue' : 'tag-green';
    const statusTag = u.status === 'active' ? 'tag-green' : 'tag-red';
    const statusText = u.status === 'active' ? '启用' : '禁用';
    return '<tr>'
      + '<td><div class="flex gap-8" style="align-items:center;"><div class="avatar" style="background:'+color+';">'+u.display_name[0]+'</div><span>'+u.display_name+'</span></div></td>'
      + '<td>'+u.username+'</td>'
      + '<td>'+(u.department_name||'-')+'</td>'
      + '<td>'+(u.position||'-')+'</td>'
      + '<td><span class="tag '+roleTag+'">'+u.role+'</span></td>'
      + '<td><span class="tag '+statusTag+'">'+statusText+'</span></td>'
      + '<td>'+(u.last_login ? u.last_login.replace('T',' ').substring(0,16) : '-')+'</td>'
      + '<td><button class="btn btn-sm" onclick="showEditUserModal(\''+u.id+'\')">编辑</button> '
      + (u.status === 'active'
        ? '<button class="btn btn-sm" style="color:#ff4d4f;" onclick="disableUser(\''+u.id+'\',\''+u.username+'\')">禁用</button>'
        : '<button class="btn btn-sm" onclick="enableUser(\''+u.id+'\',\''+u.username+'\')">启用</button>')
      + '</td></tr>';
  }).join('');
}

function fillUserSelect(selectId) {
  const sel = document.getElementById(selectId);
  if(!sel) return;
  sel.innerHTML = userList.map(u => '<option value="'+u.id+'">'+u.display_name+' ('+u.username+')</option>').join('');
}

// ─── Knowledge Base ─────────────────────────────
async function loadKBList(page) {
  kbPage = page || 1;
  try {
    const data = await fetch('/api/knowledge-bases?page='+kbPage+'&page_size=10').then(r => r.json());
    kbList = data.items || [];
    const tbody = document.getElementById('kb-table-body');
    document.getElementById('kb-total').textContent = data.total || 0;
    if(!kbList.length) {
      tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:40px;color:#999;">暂无知识库，点击右上角创建</td></tr>';
    } else {
      tbody.innerHTML = kbList.map(k =>
        '<tr>'
        + '<td><strong>📖 '+k.name+'</strong><br><span class="text-muted">'+(k.description||'')+'</span></td>'
        + '<td>'+(k.doc_count||0)+'</td><td>'+(k.chunk_count||0)+'</td>'
        + '<td><span class="tag tag-blue">'+k.embedding_model+'</span></td>'
        + '<td><span class="tag tag-green">'+k.status+'</span></td>'
        + '<td><button class="btn btn-sm" onclick="openKBDetail(\''+k.id+'\',\''+k.name+'\')">管理</button> <button class="btn btn-sm btn-danger" onclick="deleteKB(\''+k.id+'\')">删除</button></td>'
        + '</tr>'
      ).join('');
    }
    renderPagination('kb-pagination', data.total, kbPage, 10, 'loadKBList');
  } catch(e) { console.error(e); }
}

function openKBDetail(kbId, kbName) {
  currentKbId = kbId;
  const user = JSON.parse(localStorage.getItem('kb_user') || '{}');
  const role = user.role;
  document.getElementById('kb-detail-name').textContent = kbName;
  const canEdit = role === 'super_admin' || role === 'kb_admin';
  document.querySelectorAll('.kb-edit-only').forEach(el => el.style.display = canEdit ? '' : 'none');
  document.querySelectorAll('.kb-admin-only').forEach(el => el.style.display = role === 'super_admin' ? '' : 'none');
  // 重置到文档管理tab
  const tabs = document.querySelectorAll('#kb-detail-tabs .tab');
  tabs.forEach((t, i) => { t.classList.toggle('active', i === 0); });
  document.getElementById('kb-tab-docs').style.display = 'block';
  document.getElementById('kb-tab-settings').style.display = 'none';
  nav('kb-detail');
  loadKBDocs();
}

async function loadKBDocs(page) {
  docPage = page || 1;
  try {
    const url = currentKbId ? '/api/documents?kb_id='+currentKbId+'&page='+docPage+'&page_size=20' : '/api/documents?page='+docPage+'&page_size=20';
    const data = await fetch(url+'&page='+docPage+'&page_size=20').then(r => r.json());
    const docs = data.items || [];
    const tbody = document.getElementById('doc-table-body');
    if(!docs.length) {
      tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;padding:40px;color:#999;">暂无文档，请上传</td></tr>';
    } else {
      tbody.innerHTML = docs.map(d =>
        '<tr><td>📎 '+d.filename+'</td><td>'+(d.size||'-')+'</td><td>'+d.chunks+'</td>'
        + '<td><span class="tag tag-green">已索引</span></td>'
        + '<td class="flex gap-8"><button class="btn btn-sm" onclick="viewChunks(\''+d.filename+'\')">查看分块</button>' +' <button class="btn btn-sm btn-danger" onclick="deleteDoc(\''+d.filename+'\')">删除</button></td></tr>'
      ).join('');
    }
    document.getElementById('kb-stat-docs').textContent = data.total || docs.length;
    renderPagination('doc-pagination', data.total || 0, docPage, 20, 'loadKBDocs');
    document.getElementById('kb-stat-chunks').textContent = docs.reduce((a,d)=>a+(d.chunks||0),0);
  } catch(e) { console.error(e); }
  // 加载部门授权数和创建时间
  try {
    const acc = await fetch('/api/kb-access?kb_id='+currentKbId).then(r => r.json());
    document.getElementById('kb-stat-depts').textContent = acc.length;
  } catch(e) {}
  const kb = kbList.find(k => k.id === currentKbId);
  if(kb) document.getElementById('kb-stat-created').textContent = (kb.created_at||'').substring(0,10);
}








// ─── KB 设置 ──────────────────────────────────
async function loadKBSettings() {
  if(!currentKbId) return;
  const kb = kbList.find(k => k.id === currentKbId);
  if(!kb) return;
  document.getElementById('kb-set-name').value = kb.name || '';
  document.getElementById('kb-set-desc').value = kb.description || '';
  document.getElementById('kb-set-status').value = kb.status || 'active';
  document.getElementById('kb-set-emb-model').value = kb.embedding_model || '';
  document.getElementById('kb-set-llm-model').value = kb.llm_model || '';
}

async function saveKBSettings() {
  if(!currentKbId) return;
  try {
    await fetch('/api/knowledge-bases/' + currentKbId, {
      method: 'PUT',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        name: document.getElementById('kb-set-name').value.trim(),
        description: document.getElementById('kb-set-desc').value.trim(),
        status: document.getElementById('kb-set-status').value,
        embedding_model: document.getElementById('kb-set-emb-model').value.trim(),
        llm_model: document.getElementById('kb-set-llm-model').value.trim(),
      })
    });
    // 刷新KB列表缓存
    const d = await fetch('/api/knowledge-bases?page=1&page_size=100').then(r => r.json()); kbList = d.items || [];
    document.getElementById('kb-detail-name').textContent = document.getElementById('kb-set-name').value.trim();
    alert('保存成功');
  } catch(e) { alert('保存失败: ' + e.message); }
}


async function deleteDoc(filename) {
  if(!confirm('确认删除 "'+filename+'"？')) return;
  try {
    const url = currentKbId ? '/api/documents/'+encodeURIComponent(filename)+'?kb_id='+currentKbId : '/api/documents/'+encodeURIComponent(filename);
    await fetch(url, {method:'DELETE'});
    loadKBDocs();
  } catch(e) { console.error(e); }
}

// ─── Document Upload ────────────────────────────
let selectedFile = null;
const uploadZone = document.getElementById('upload-zone');
if(uploadZone) {
  uploadZone.onclick = () => document.getElementById('file-input').click();
  uploadZone.ondragover = e => { e.preventDefault(); uploadZone.style.borderColor = '#1890ff'; };
  uploadZone.ondragleave = () => uploadZone.style.borderColor = '#d9d9d9';
  uploadZone.ondrop = e => {
    e.preventDefault(); uploadZone.style.borderColor = '#d9d9d9';
    if(e.dataTransfer.files[0]) handleFile(e.dataTransfer.files[0]);
  };
  document.getElementById('file-input').onchange = e => {
    if(e.target.files[0]) handleFile(e.target.files[0]);
  };
}

function handleFile(file) {
  selectedFile = file;
  document.getElementById('selected-files').innerHTML =
    '<div style="padding:12px;background:#e6f7ff;border-radius:6px;display:flex;justify-content:space-between;align-items:center;">'
    + '<span>📎 '+file.name+'</span>'
    + '<span class="text-muted">'+(file.size/1024/1024).toFixed(2)+' MB</span></div>';
  document.getElementById('step1-next').disabled = false;
}

function toggleChunkConfig(type) {
  const showSize = type !== 'structural';
  document.getElementById('chunk-config-size').style.display = showSize ? 'block' : 'none';
  document.getElementById('chunk-config-structural').style.display = type === 'structural' ? 'block' : 'none';
  const hint = document.getElementById('chunk-config-hint');
  if(type === 'fixed') hint.textContent = '按固定字符数硬切，支持重叠';
  else if(type === 'semantic') hint.textContent = '按句子边界拆分，保证语义完整，块间按完整句子重叠';
}

let lastUploadedFile = null;

function goUploadStep(step) {
  // 隐藏所有步骤内容
  document.getElementById('upload-step-1').style.display = 'none';
  document.getElementById('upload-step-2').style.display = 'none';
  document.getElementById('upload-step-3').style.display = 'none';
  // 更新步骤条
  for(let i=1;i<=3;i++) {
    const el = document.getElementById('step-'+i);
    el.classList.remove('active','done');
    if(i < step) el.classList.add('done');
    if(i === step) el.classList.add('active');
  }
  // 显示当前步骤
  document.getElementById('upload-step-'+step).style.display = 'block';
  // Step 2 显示文件信息
  if(step === 2 && selectedFile) {
    document.getElementById('step2-file-info').innerHTML =
      '<strong>📎 '+selectedFile.name+'</strong> <span class="text-muted">'+(selectedFile.size/1024/1024).toFixed(2)+' MB</span>';
  }
}

async function doUpload() {
  if(!selectedFile) return;
  goUploadStep(3);
  document.getElementById('upload-progress').style.display = 'block';
  document.getElementById('upload-result').style.display = 'none';
  document.getElementById('upload-actions').style.display = 'none';
  document.getElementById('upload-spinner').style.display = 'inline-block';
  document.getElementById('upload-status-text').textContent = '正在上传并处理...';
  document.getElementById('upload-progress-bar').style.width = '0%';
  document.getElementById('upload-progress-text').textContent = '0%';

  lastUploadedFile = selectedFile.name;
  const fd = new FormData();
  fd.append('file', selectedFile);
  if(currentKbId) fd.append('kb_id', currentKbId);
  const strategy = document.getElementById('chunk-strategy').value || 'semantic';
  fd.append('chunk_strategy', strategy);
  if(strategy === 'structural') {
    fd.append('chunk_size', document.getElementById('structural-chunk-size').value || '1024');
    fd.append('heading_level', document.getElementById('structural-heading-level').value || '2');
  } else {
    fd.append('chunk_size', document.getElementById('chunk-size').value || '512');
    fd.append('chunk_overlap', document.getElementById('chunk-overlap').value || '64');
  }

  try {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/upload');
    xhr.upload.onprogress = e => {
      if(e.lengthComputable) {
        const pct = Math.round(e.loaded/e.total*100);
        document.getElementById('upload-progress-bar').style.width = pct+'%';
        document.getElementById('upload-progress-text').textContent = pct+'%';
      }
    };
    xhr.onload = () => {
      if(xhr.status >= 200 && xhr.status < 300) {
        const data = JSON.parse(xhr.responseText);
        document.getElementById('upload-spinner').style.display = 'none';
        document.getElementById('upload-status-text').textContent = '✅ 上传完成';
        document.getElementById('upload-progress-bar').style.width = '100%';
        document.getElementById('upload-progress-text').textContent = '100%';
        document.getElementById('upload-result').innerHTML =
          '<div style="padding:16px;background:#ecfdf5;border-radius:8px;color:#065f46;font-size:15px;">'
          +'<div style="font-weight:600;margin-bottom:8px;">✅ '+data.filename+'</div>'
          +'<div>'+data.message+'</div></div>';
        document.getElementById('upload-result').style.display = 'block';
        document.getElementById('upload-actions').style.display = 'flex';
        selectedFile = null;
        loadKBDocs();
      } else {
        document.getElementById('upload-spinner').style.display = 'none';
        document.getElementById('upload-status-text').textContent = '❌ 上传失败';
        document.getElementById('upload-result').innerHTML =
          '<div style="padding:16px;background:#fff1f0;border-radius:8px;color:#cf1322;">上传失败: '+xhr.statusText+'</div>';
        document.getElementById('upload-result').style.display = 'block';
      }
    };
    xhr.onerror = () => {
      document.getElementById('upload-spinner').style.display = 'none';
      document.getElementById('upload-status-text').textContent = '❌ 网络错误';
      document.getElementById('upload-result').innerHTML =
        '<div style="padding:16px;background:#fff1f0;border-radius:8px;color:#cf1322;">网络错误，请重试</div>';
      document.getElementById('upload-result').style.display = 'block';
    };
    xhr.send(fd);
  } catch(e) { console.error(e); }
}

function resetUpload() {
  selectedFile = null;
  lastUploadedFile = null;
  document.getElementById('selected-files').innerHTML = '';
  document.getElementById('step1-next').disabled = true;
  document.getElementById('file-input').value = '';
  document.getElementById('upload-result').innerHTML = '';
  document.getElementById('upload-result').style.display = 'none';
  document.getElementById('upload-actions').style.display = 'none';
  document.getElementById('upload-progress-bar').style.width = '0%';
  document.getElementById('upload-progress-text').textContent = '0%';
  goUploadStep(1);
}

function viewLastUploadChunks() {
  if(lastUploadedFile) {
    viewChunks(lastUploadedFile);
  }
}

// ─── QA Chat ────────────────────────────────────
async function askQuestion() {
  const input = document.getElementById('qa-input');
  const question = input.value.trim();
  if(!question) return;
  input.disabled = true;
  document.getElementById('qa-send-btn').disabled = true;
  document.getElementById('qa-send-btn').textContent = '思考中...';
  addMessage('user', question);
  input.value = '';
  const loadingId = addMessage('loading', '正在检索知识库并生成回答，请稍候...');
  try {
    const topK = parseInt(document.getElementById('qa-topk').value) || 5;
    const body = {question, top_k: topK};
    if(currentKbId) body.kb_id = currentKbId;

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 60000); // 60s 超时
    const res = await fetch('/api/query', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(body),
      signal: controller.signal
    });
    clearTimeout(timeout);

    if(!res.ok) {
      const errData = await res.json().catch(()=>({}));
      throw new Error(errData.detail || '服务器错误 ('+res.status+')');
    }
    const data = await res.json();
    removeMessage(loadingId);
    let answer = data.answer || '未获取到回答';
    if(data.sources && data.sources.length) {
      answer += '<div style="margin-top:8px;">'+data.sources.map(s =>
        '<span class="source-tag">📎 '+s+'</span>').join(' ')+'</div>';
    }
    addMessage('assistant', answer);
  } catch(e) {
    removeMessage(loadingId);
    if(e.name === 'AbortError') {
      addMessage('assistant', '❌ 请求超时（60秒），请检查网络或稍后重试。');
    } else {
      addMessage('assistant', '❌ 请求失败：'+e.message);
    }
  } finally {
    input.disabled = false;
    document.getElementById('qa-send-btn').disabled = false;
    document.getElementById('qa-send-btn').textContent = '发送';
    input.focus();
  }
}


function md2html(md) {
  if(!md) return '';
  let html = md;
  // code blocks (```...```)
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, function(m, lang, code) {
    return '<pre style="background:#1e1e1e;color:#d4d4d4;padding:12px;border-radius:6px;overflow-x:auto;font-size:13px;margin:8px 0;"><code>'+code.replace(/</g,'&lt;').replace(/>/g,'&gt;')+'</code></pre>';
  });
  // inline code
  html = html.replace(/`([^`]+)`/g, '<code style="background:#f0f0f0;padding:2px 6px;border-radius:3px;font-size:13px;">$1</code>');
  // bold
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  // italic
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
  // headers
  html = html.replace(/^### (.+)$/gm, '<h4 style="margin:12px 0 6px;font-size:15px;">$1</h4>');
  html = html.replace(/^## (.+)$/gm, '<h3 style="margin:14px 0 8px;font-size:16px;">$1</h3>');
  html = html.replace(/^# (.+)$/gm, '<h2 style="margin:16px 0 8px;font-size:18px;">$1</h2>');
  // unordered lists
  html = html.replace(/^- (.+)$/gm, '<li style="margin-left:16px;">$1</li>');
  // ordered lists
  html = html.replace(/^\d+\. (.+)$/gm, '<li style="margin-left:16px;list-style:decimal;">$1</li>');
  // paragraphs (double newline)
  html = html.replace(/\n\n/g, '</p><p style="margin:8px 0;">');
  // single newline to <br>
  html = html.replace(/\n/g, '<br>');
  // reference tags [来源: xxx, 第X块]
  html = html.replace(/\[来源: ([^\]]+)\]/g, '<span class="source-tag" style="display:inline-block;font-size:11px;background:#e6f7ff;color:#1890ff;padding:2px 8px;border-radius:4px;margin:2px;border:1px solid #91d5ff;">📎 $1</span>');
  return '<p style="margin:0;">'+html+'</p>';
}

function addMessage(role, content) {
  const id = 'msg-'+Date.now();
  const div = document.getElementById('chat-messages');
  const empty = div.querySelector('div[style*="text-align:center"]');
  if(empty) empty.remove();
  const el = document.createElement('div');
  el.className = 'message '+role;
  el.id = id;
  const avatar = role === 'user' ? '你' : 'AI';
  const bg = role === 'user' ? '#1890ff' : '#f5f5f5';
  const color = role === 'user' ? '#fff' : '#333';
  let html = role === 'loading' ? '<div style="color:#999;">⏳ 思考中...</div>' : (role === 'assistant' ? md2html(content) : content);
  if(role !== 'user' && role !== 'loading') {
    html += '<div class="chat-actions">'
      + '<button class="feedback-btn" title="👍" onclick="this.style.opacity=this.style.opacity===\'1\'?\'.4\':\'1\'">👍</button>'
      + '<button class="feedback-btn" title="👎" onclick="this.style.opacity=this.style.opacity===\'1\'?\'.4\':\'1\'">👎</button>'
      + '</div>';
  }
  el.innerHTML = '<div class="avatar" style="background:'+bg+';color:'+color+'">'+avatar+'</div><div class="bubble">'+html+'</div>';
  div.appendChild(el);
  div.scrollTop = div.scrollHeight;
  return id;
}
function removeMessage(id) { const el = document.getElementById(id); if(el) el.remove(); }
function askPreset(btn) {
  const q = btn.textContent.replace(/^📋\s*/, '');
  document.getElementById('qa-input').value = q;
  askQuestion();
}

function newChat() {
  document.getElementById('chat-list').innerHTML = '<div class="chat-item active"><div class="title">新对话</div><div class="meta">刚刚</div></div>';
  document.getElementById('chat-messages').innerHTML = '<div style="text-align:center;padding:60px 20px;color:#999;" id="qa-empty-state">'
    +'<div style="font-size:48px;margin-bottom:16px;">💬</div>'
    +'<div style="font-size:16px;">输入问题开始对话</div>'
    +'<div style="margin-top:24px;display:flex;flex-direction:column;gap:10px;align-items:center;">'
    +'<button class="btn" style="max-width:500px;width:100%;justify-content:flex-start;text-align:left;font-size:13px;padding:10px 16px;" onclick="askPreset(this)">📋 知识库系统有什么功能模块？</button>'
    +'<button class="btn" style="max-width:500px;width:100%;justify-content:flex-start;text-align:left;font-size:13px;padding:10px 16px;" onclick="askPreset(this)">📋 P1阶段将会更新什么模块？</button>'
    +'</div></div>';
}

// ─── Modals ─────────────────────────────────────
function showModal(name) {
  document.getElementById('modal-overlay').style.display = 'flex';
  document.getElementById('modal-'+name).style.display = 'block';
  // 弹窗打开时填充下拉框
  if(name === 'create-kb') { loadDepts().then(()=>fillDeptSelect('new-kb-dept')); }
  // create-user / edit-user 的部门填充由 showCreateUserModal / showEditUserModal 处理
  // add-dept-access 的部门填充由 showAddDeptAccess 处理
  if(name === 'add-user-access') { loadUsers().then(()=>fillUserSelect('user-access-user')); }
  if(name === 'add-dept') { loadDepts().then(()=>fillDeptSelect('new-dept-parent')); }
}
function hideModal() {
  document.getElementById('modal-overlay').style.display = 'none';
  document.querySelectorAll('.modal').forEach(m => m.style.display = 'none');
}

async function createKB() {
  const name = document.getElementById('new-kb-name').value.trim();
  if(!name) { alert('请输入知识库名称'); return; }
  try {
    await fetch('/api/knowledge-bases', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        name,
        description: document.getElementById('new-kb-desc').value.trim()
      })
    });
    hideModal();
    loadKBList();
  } catch(e) { alert('创建失败'); }
}

function showCreateUserModal() {
  loadDepts().then(() => {
    document.getElementById('user-modal-title').textContent = '创建用户';
    document.getElementById('user-modal-btn').textContent = '创建';
    document.getElementById('edit-user-id').value = '';
    document.getElementById('new-user-username').value = '';
    document.getElementById('new-user-username').disabled = false;
    document.getElementById('new-user-name').value = '';
    document.getElementById('new-user-password').value = '';
    document.getElementById('new-user-email').value = '';
    document.getElementById('new-user-position').value = '';
    document.getElementById('new-user-role').value = 'user';
    document.getElementById('password-field').style.display = 'block';
    fillDeptSelect('new-user-dept');
    showModal('create-user');
  });
}

function showEditUserModal(userId) {
  const u = allUsers.find(x => x.id === userId);
  if(!u) return;
  loadDepts().then(() => {
    document.getElementById('user-modal-title').textContent = '编辑用户';
    document.getElementById('user-modal-btn').textContent = '保存';
    document.getElementById('edit-user-id').value = userId;
    document.getElementById('new-user-username').value = u.username;
    document.getElementById('new-user-username').disabled = true;
    document.getElementById('new-user-name').value = u.display_name;
    document.getElementById('new-user-password').value = '';
    document.getElementById('new-user-email').value = u.email || '';
    document.getElementById('new-user-position').value = u.position || '';
    document.getElementById('new-user-role').value = u.role;
    document.getElementById('password-field').style.display = 'none';
    const sel = document.getElementById('new-user-dept');
    sel.innerHTML = '<option value="">-- 无 --</option>' + deptList.map(d => '<option value="'+d.id+'">'+d.name+'</option>').join('');
    sel.value = u.department_id || '';
    showModal('create-user');
  });
}

async function saveUser() {
  const editId = document.getElementById('edit-user-id').value;
  const name = document.getElementById('new-user-name').value.trim();
  if(!name) { alert('请填写姓名'); return; }
  try {
    if(editId) {
      const res = await fetch('/api/users/' + editId, {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          display_name: name,
          email: document.getElementById('new-user-email').value.trim(),
          position: document.getElementById('new-user-position').value.trim(),
          department_id: document.getElementById('new-user-dept').value || null,
          role: document.getElementById('new-user-role').value,
        })
      });
      if(!res.ok) { const err = await res.json(); alert(err.detail || '保存失败'); return; }
      hideModal();
      loadUserList();
      return;
    }
    const username = document.getElementById('new-user-username').value.trim();
    if(!username) { alert('请填写用户名'); return; }
    const res = await fetch('/api/users', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        username,
        display_name: name,
        email: document.getElementById('new-user-email').value.trim(),
        position: document.getElementById('new-user-position').value.trim(),
        department_id: document.getElementById('new-user-dept').value || null,
        role: document.getElementById('new-user-role').value,
        password: document.getElementById('new-user-password').value || undefined,
      })
    });
    if(!res.ok) {
      const err = await res.json();
      alert(err.detail || '创建失败');
      return;
    }
    hideModal();
    loadUserList();
  } catch(e) { alert('操作失败: ' + e.message); }
}

async function disableUser(userId, username) {
  
  try {
    await fetch('/api/users/' + userId, {method: 'DELETE'});
    loadUserList();
  } catch(e) { alert('操作失败'); }
}

async function enableUser(userId, username) {
  
  try {
    await fetch('/api/users/' + userId, {
      method: 'PUT',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({status: 'active'})
    });
    loadUserList();
  } catch(e) { alert('操作失败'); }
}

async function createDept() {
  const name = document.getElementById('new-dept-name').value.trim();
  if(!name) { alert('请输入部门名称'); return; }
  try {
    await fetch('/api/departments', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        name,
        path: '/' + name,
        parent_id: document.getElementById('new-dept-parent').value || null
      })
    });
    hideModal();
    loadDeptTree();
  } catch(e) { alert('创建失败'); }
}

function createRole() { hideModal(); alert('角色创建（P1 实现）'); }



// ─── Prompt Management ──────────────────────────
let promptsCache = {};

async function loadPrompts() {
  try {
    promptsCache = await fetch('/api/config/prompts').then(r => r.json());
    loadPromptEditor();
  } catch(e) { console.error('Load prompts error:', e); }
}

function loadPromptEditor() {
  const type = document.getElementById('prompt-selector').value;
  document.getElementById('prompt-qa-panel').style.display = type === 'qa' ? 'block' : 'none';
  document.getElementById('prompt-rewrite-panel').style.display = type === 'rewrite' ? 'block' : 'none';
  document.getElementById('prompt-refuse-panel').style.display = type === 'refuse' ? 'block' : 'none';

  const p = promptsCache[type] || {};
  if(type === 'qa') {
    document.getElementById('prompt-qa-system').value = p.system || '';
    document.getElementById('prompt-qa-user').value = p.user || '';
  } else if(type === 'rewrite') {
    document.getElementById('prompt-rewrite-system').value = p.system || '';
    document.getElementById('prompt-rewrite-user').value = p.user || '';
  } else if(type === 'refuse') {
    document.getElementById('prompt-refuse-answer').value = p.answer || '';
  }
}

async function savePrompts() {
  // Collect all prompt data from inputs
  promptsCache.qa = promptsCache.qa || {};
  promptsCache.qa.system = document.getElementById('prompt-qa-system').value;
  promptsCache.qa.user = document.getElementById('prompt-qa-user').value;
  promptsCache.qa.name = '问答主 Prompt';

  promptsCache.rewrite = promptsCache.rewrite || {};
  promptsCache.rewrite.system = document.getElementById('prompt-rewrite-system').value;
  promptsCache.rewrite.user = document.getElementById('prompt-rewrite-user').value;
  promptsCache.rewrite.name = '查询改写 Prompt';

  promptsCache.refuse = promptsCache.refuse || {};
  promptsCache.refuse.answer = document.getElementById('prompt-refuse-answer').value;
  promptsCache.refuse.name = '拒答话术';

  try {
    const res = await fetch('/api/config/prompts', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(promptsCache)
    });
    if(res.ok) { alert('✅ Prompt 已保存！'); }
    else { alert('保存失败'); }
  } catch(e) { alert('保存失败: '+e.message); }
}

// ─── Chunk Viewer ───────────────────────────────
let chunkData = [];
let currentChunkId = null;

async function viewChunks(filename) {
  document.getElementById('chunk-viewer-filename').textContent = filename;
  nav('chunk-viewer');
  try {
    const url = currentKbId
      ? '/api/documents/'+encodeURIComponent(filename)+'/chunks?kb_id='+currentKbId
      : '/api/documents/'+encodeURIComponent(filename)+'/chunks';
    const data = await fetch(url).then(r => r.json());
    chunkData = data.chunks || [];
    document.getElementById('chunk-viewer-count').textContent = data.total + ' 块';
    renderChunks(chunkData);
  } catch(e) {
    document.getElementById('chunk-list').innerHTML = '<div class="text-muted" style="text-align:center;padding:40px;">加载失败: '+e.message+'</div>';
  }
}

function renderChunks(chunks) {
  const el = document.getElementById('chunk-list');
  if(!chunks.length) {
    el.innerHTML = '<div class="text-muted" style="text-align:center;padding:40px;">暂无分块</div>';
    return;
  }
  el.innerHTML = chunks.map(c =>
    '<div class="chunk-card" id="chunk-card-'+c.id+'">'
    + '<div class="chunk-header" onclick="toggleChunk(\''+c.id+'\')">'
    + '<div><span class="chunk-index">#'+c.index+'</span> <span class="chunk-meta">'+c.char_count+' 字</span></div>'
    + '<div class="chunk-actions">'
    + '<button class="btn btn-sm" onclick="event.stopPropagation();editChunk(\''+c.id+'\')">✏️ 编辑</button>'
    + '<button class="btn btn-sm btn-danger" onclick="event.stopPropagation();deleteChunkDirect(\''+c.id+'\')">🗑️</button>'
    + '</div>'
    + '</div>'
    + '<div class="chunk-body" id="chunk-body-'+c.id+'">'+escapeHtml(c.text)+'</div>'
    + '</div>'
  ).join('');
}

function escapeHtml(str) {
  return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function toggleChunk(id) {
  const body = document.getElementById('chunk-body-'+id);
  const card = document.getElementById('chunk-card-'+id);
  if(body.classList.contains('collapsed')) {
    body.classList.remove('collapsed');
    card.classList.add('expanded');
  } else {
    body.classList.add('collapsed');
    card.classList.remove('expanded');
  }
}

function expandAll() {
  document.querySelectorAll('.chunk-body').forEach(b => b.classList.remove('collapsed'));
  document.querySelectorAll('.chunk-card').forEach(c => c.classList.add('expanded'));
}
function collapseAll() {
  document.querySelectorAll('.chunk-body').forEach(b => b.classList.add('collapsed'));
  document.querySelectorAll('.chunk-card').forEach(c => c.classList.remove('expanded'));
}

function filterChunks() {
  const q = document.getElementById('chunk-search').value.trim().toLowerCase();
  if(!q) { renderChunks(chunkData); return; }
  renderChunks(chunkData.filter(c => c.text.toLowerCase().includes(q)));
}

function sortChunks() {
  const mode = document.getElementById('chunk-sort').value;
  let sorted = [...chunkData];
  if(mode === 'length-desc') sorted.sort((a,b) => b.char_count - a.char_count);
  else if(mode === 'length-asc') sorted.sort((a,b) => a.char_count - b.char_count);
  else sorted.sort((a,b) => a.index - b.index);
  renderChunks(sorted);
}

function editChunk(id) {
  currentChunkId = id;
  const chunk = chunkData.find(c => c.id === id);
  if(!chunk) return;
  document.getElementById('chunk-edit-index').textContent = '#'+chunk.index;
  document.getElementById('chunk-edit-text').value = chunk.text;
  document.getElementById('chunk-edit-charcount').textContent = chunk.char_count;
  showModal('chunk-edit');
}

function hideChunkEdit() { hideModal(); currentChunkId = null; }

async function saveChunkEdit() {
  const text = document.getElementById('chunk-edit-text').value.trim();
  if(!text) { alert('内容不能为空'); return; }
  try {
    const res = await fetch('/api/chunks/'+currentChunkId, {
      method: 'PUT',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({text})
    });
    if(res.ok) {
      const chunk = chunkData.find(c => c.id === currentChunkId);
      if(chunk) { chunk.text = text; chunk.char_count = text.length; }
      renderChunks(chunkData);
      hideChunkEdit();
    } else {
      alert('保存失败');
    }
  } catch(e) { alert('保存失败: '+e.message); }
}

async function deleteChunkDirect(id) {
  if(!confirm('确认删除此分块？')) return;
  try {
    await fetch('/api/chunks/'+id, {method:'DELETE'});
    chunkData = chunkData.filter(c => c.id !== id);
    chunkData.forEach((c,i) => c.index = i+1);
    document.getElementById('chunk-viewer-count').textContent = chunkData.length + ' 块';
    renderChunks(chunkData);
  } catch(e) { alert('删除失败'); }
}

async function deleteCurrentChunk() {
  if(!currentChunkId) return;
  if(!confirm('确认删除此分块？')) return;
  await deleteChunkDirect(currentChunkId);
  hideChunkEdit();
}

// Update char count live
const chunkEditText = document.getElementById('chunk-edit-text');
if(chunkEditText) {
  chunkEditText.addEventListener('input', function() {
    document.getElementById('chunk-edit-charcount').textContent = this.value.length;
  });
}


// ─── Model Config ───────────────────────────────
const PROVIDER_PRESETS = {
  dashscope: { base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1', needs_key: true },
  ollama:    { base_url: 'http://localhost:11434/v1', needs_key: false },
  openai:    { base_url: 'https://api.openai.com/v1', needs_key: true },
  custom:    { base_url: '', needs_key: true },
};

function toggleLLMFields() {
  const p = document.getElementById('llm-provider').value;
  const preset = PROVIDER_PRESETS[p] || {};
  document.getElementById('llm-base-url').value = preset.base_url || '';
  document.getElementById('llm-api-key-group').style.display = preset.needs_key ? 'block' : 'none';
  // 填充常见模型
  const modelMap = {
    dashscope: 'qwen3.6-plus', ollama: 'llama3', openai: 'gpt-4o', custom: ''
  };
  document.getElementById('llm-model').value = modelMap[p] || '';
}

function toggleEmbFields() {
  const p = document.getElementById('emb-provider').value;
  const preset = PROVIDER_PRESETS[p] || {};
  document.getElementById('emb-base-url').value = preset.base_url || '';
  document.getElementById('emb-api-key-group').style.display = preset.needs_key ? 'block' : 'none';
  const modelMap = {
    dashscope: 'text-embedding-v3', ollama: 'bge-m3', openai: 'text-embedding-3-small', custom: ''
  };
  document.getElementById('emb-model').value = modelMap[p] || '';
}

async function loadModelConfig() {
  try {
    const cfg = await fetch('/api/config/models').then(r => r.json());
    if(cfg.llm) {
      // provider detection
      const url = cfg.llm.base_url || '';
      let prov = 'custom';
      if(url.includes('dashscope')) prov = 'dashscope';
      else if(url.includes('localhost:11434') || url.includes('ollama')) prov = 'ollama';
      else if(url.includes('api.openai.com')) prov = 'openai';
      document.getElementById('llm-provider').value = prov;
      document.getElementById('llm-model').value = cfg.llm.model || '';
      document.getElementById('llm-base-url').value = url;
      document.getElementById('llm-api-key').value = cfg.llm.api_key || '';
      document.getElementById('llm-max-tokens').value = cfg.llm.max_tokens || 2048;
      document.getElementById('llm-temperature').value = cfg.llm.temperature || 0.7;
    }
    if(cfg.embedding) {
      const url = cfg.embedding.base_url || '';
      let prov = 'custom';
      if(url.includes('dashscope')) prov = 'dashscope';
      else if(url.includes('localhost:11434') || url.includes('ollama')) prov = 'ollama';
      else if(url.includes('api.openai.com')) prov = 'openai';
      document.getElementById('emb-provider').value = prov;
      document.getElementById('emb-model').value = cfg.embedding.model || '';
      document.getElementById('emb-base-url').value = url;
      document.getElementById('emb-api-key').value = cfg.embedding.api_key || '';
      document.getElementById('emb-dimensions').value = cfg.embedding.dimensions || '';
    }
  } catch(e) { console.error('Load config error:', e); }
}

async function saveModelConfig() {
  const cfg = {
    llm: {
      provider: document.getElementById('llm-provider').value,
      base_url: document.getElementById('llm-base-url').value,
      api_key: document.getElementById('llm-api-key').value,
      model: document.getElementById('llm-model').value,
      max_tokens: parseInt(document.getElementById('llm-max-tokens').value) || 2048,
      temperature: parseFloat(document.getElementById('llm-temperature').value) || 0.7,
    },
    embedding: {
      provider: document.getElementById('emb-provider').value,
      base_url: document.getElementById('emb-base-url').value,
      api_key: document.getElementById('emb-api-key').value,
      model: document.getElementById('emb-model').value,
      dimensions: parseInt(document.getElementById('emb-dimensions').value) || null,
    }
  };
  try {
    const res = await fetch('/api/config/models', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(cfg)
    });
    if(res.ok) {
      alert('✅ 配置已保存！更换 Embedding 模型后请重建索引。');
    } else {
      alert('保存失败');
    }
  } catch(e) { alert('保存失败: '+e.message); }
}

async function reindexAll() {
  const el = document.getElementById('reindex-status');
  el.style.display = 'block';
  el.innerHTML = '<span class="tag tag-blue">重建中...</span>';
  try {
    const res = await fetch('/api/reindex', {method:'POST'});
    const data = await res.json();
    el.innerHTML = '<span class="tag tag-green">✅ '+data.message+'（'+data.count+' 个文档块）</span>';
  } catch(e) {
    el.innerHTML = '<span class="tag tag-red">❌ 失败: '+e.message+'</span>';
  }
}

async function reindexCurrentKB() {
  if(!currentKbId) { alert('请先选择一个知识库'); return; }
  const el = document.getElementById('reindex-status');
  el.style.display = 'block';
  el.innerHTML = '<span class="tag tag-blue">重建中...</span>';
  try {
    const res = await fetch('/api/reindex?kb_id='+currentKbId, {method:'POST'});
    const data = await res.json();
    el.innerHTML = '<span class="tag tag-green">✅ '+data.message+'（'+data.count+' 个文档块）</span>';
  } catch(e) {
    el.innerHTML = '<span class="tag tag-red">❌ 失败: '+e.message+'</span>';
  }
}

// ─── Init ───────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  loadDepts();
  loadUsers();
  loadModelConfig();
  loadPrompts();
});

async function deleteKB(kbId) {
  if(!confirm('确认删除该知识库？')) return;
  try {
    await fetch('/api/knowledge-bases/'+kbId, {method:'DELETE'});
    loadKBList(kbPage);
  } catch(e) { alert('删除失败'); }
}
