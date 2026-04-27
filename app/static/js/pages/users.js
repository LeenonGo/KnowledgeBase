/**
 * 用户管理页
 */
const PageUsers = (() => {
  let allUsers = [];
  let userPage = 1;

  async function load(page) {
    userPage = page || 1;
    try {
      const data = await API.request(`/api/users?page=${userPage}&page_size=10`);
      allUsers = data.items || [];
      await UI.loadDepts();
      const deptSel = document.getElementById('user-dept-filter');
      if (deptSel) {
        deptSel.innerHTML = '<option value="">全部部门</option>' +
          UI.getDeptList().map(d => `<option value="${d.id}">${d.name}</option>`).join('');
      }
      filter();
      UI.renderPagination('user-pagination', data.total, userPage, 10, 'PageUsers.load');
    } catch (e) { console.error(e); }
  }

  function filter() {
    const keyword = (document.getElementById('user-search')?.value || '').trim().toLowerCase();
    const roleFilter = document.getElementById('user-role-filter')?.value || '';
    const statusFilter = document.getElementById('user-status-filter')?.value || '';
    const deptFilter = document.getElementById('user-dept-filter')?.value || '';
    let filtered = allUsers;
    if (keyword) filtered = filtered.filter(u =>
      u.username.toLowerCase().includes(keyword) || u.display_name.toLowerCase().includes(keyword));
    if (roleFilter) filtered = filtered.filter(u => u.role === roleFilter);
    if (statusFilter) filtered = filtered.filter(u => u.status === statusFilter);
    if (deptFilter) filtered = filtered.filter(u => u.department_id === deptFilter);

    const tbody = document.getElementById('user-table-body');
    document.getElementById('user-count').textContent = filtered.length + ' 人';
    if (!filtered.length) {
      tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:40px;color:#999;">暂无用户</td></tr>';
      return;
    }
    const colors = ['#1890ff','#52c41a','#fa8c16','#eb2f96','#722ed1','#13c2c2'];
    tbody.innerHTML = filtered.map((u, i) => {
      const color = colors[i % colors.length];
      const roleTag = u.role === 'super_admin' ? 'tag-purple' : u.role === 'kb_admin' ? 'tag-blue' : 'tag-green';
      const statusTag = u.status === 'active' ? 'tag-green' : 'tag-red';
      const statusText = u.status === 'active' ? '启用' : '禁用';
      return `<tr>
        <td><div class="flex gap-8" style="align-items:center;"><div class="avatar" style="background:${color};">${u.display_name[0]}</div><span>${u.display_name}</span></div></td>
        <td>${u.username}</td><td>${u.department_name || '-'}</td><td>${u.position || '-'}</td>
        <td><span class="tag ${roleTag}">${u.role}</span></td>
        <td><span class="tag ${statusTag}">${statusText}</span></td>
        <td>${u.last_login ? u.last_login.replace('T',' ').substring(0,16) : '-'}</td>
        <td><button class="btn btn-sm" onclick="PageUsers.showEdit('${u.id}')">编辑</button>
          ${u.status === 'active'
            ? `<button class="btn btn-sm" style="color:#ff4d4f;" onclick="PageUsers.disable('${u.id}')">禁用</button>`
            : `<button class="btn btn-sm" onclick="PageUsers.enable('${u.id}')">启用</button>`}
        </td></tr>`;
    }).join('');
  }

  function showCreate() {
    UI.loadDepts().then(() => {
      document.getElementById('user-modal-title').textContent = '创建用户';
      document.getElementById('user-modal-btn').textContent = '创建';
      document.getElementById('edit-user-id').value = '';
      const usernameEl = document.getElementById('new-user-username');
      usernameEl.value = ''; usernameEl.disabled = false;
      document.getElementById('new-user-name').value = '';
      document.getElementById('new-user-password').value = '';
      document.getElementById('new-user-email').value = '';
      document.getElementById('new-user-position').value = '';
      document.getElementById('new-user-role').value = 'user';
      document.getElementById('password-field').style.display = 'block';
      UI.fillDeptSelect('new-user-dept');
      UI.showModal('create-user');
    });
  }

  function showEdit(userId) {
    const u = allUsers.find(x => x.id === userId);
    if (!u) return;
    UI.loadDepts().then(() => {
      document.getElementById('user-modal-title').textContent = '编辑用户';
      document.getElementById('user-modal-btn').textContent = '保存';
      document.getElementById('edit-user-id').value = userId;
      const usernameEl = document.getElementById('new-user-username');
      usernameEl.value = u.username; usernameEl.disabled = true;
      document.getElementById('new-user-name').value = u.display_name;
      document.getElementById('new-user-password').value = '';
      document.getElementById('new-user-email').value = u.email || '';
      document.getElementById('new-user-position').value = u.position || '';
      document.getElementById('new-user-role').value = u.role;
      document.getElementById('password-field').style.display = 'none';
      UI.fillDeptSelect('new-user-dept', u.department_id);
      UI.showModal('create-user');
    });
  }

  async function save() {
    const editId = document.getElementById('edit-user-id').value;
    const name = document.getElementById('new-user-name').value.trim();
    if (!name) { alert('请填写姓名'); return; }
    // 校验密码复杂度（新建用户时）
    if (!editId) {
      const pw = document.getElementById('new-user-password').value;
      if (pw) {
        const err = typeof validatePassword === 'function' ? validatePassword(pw) : '';
        if (err) { alert(err); return; }
      }
    }
    try {
      if (editId) {
        await API.request(`/api/users/${editId}`, {
          method: 'PUT',
          body: {
            display_name: name,
            email: document.getElementById('new-user-email').value,
            position: document.getElementById('new-user-position').value,
            department_id: document.getElementById('new-user-dept').value || null,
            role: document.getElementById('new-user-role').value,
          },
        });
      } else {
        const username = document.getElementById('new-user-username').value.trim();
        if (!username) { alert('请填写用户名'); return; }
        const pw = document.getElementById('new-user-password').value;
        await API.request('/api/users', {
          method: 'POST',
          body: {
            username, display_name: name,
            email: document.getElementById('new-user-email').value,
            password: pw || 'admin123',
            position: document.getElementById('new-user-position').value,
            department_id: document.getElementById('new-user-dept').value || null,
            role: document.getElementById('new-user-role').value,
          },
        });
      }
      UI.hideModal();
      load(userPage);
    } catch (e) { alert(e.message); }
  }

  async function disable(userId, username) {
    if (!confirm(`确认禁用用户？`)) return;
    await API.request(`/api/users/${userId}`, { method: 'PUT', body: { status: 'disabled' } });
    load(userPage);
  }

  async function enable(userId) {
    await API.request(`/api/users/${userId}`, { method: 'PUT', body: { status: 'active' } });
    load(userPage);
  }

  return { load, filter, showCreate, showEdit, save, disable, enable };
})();

Router.on('user-mgmt', () => PageUsers.load());
