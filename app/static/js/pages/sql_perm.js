/**
 * SQL 表级权限管理页
 */
const PageSQLPerm = (() => {
  let _perms = [];
  let _roles = [];
  let _tables = [];
  let _activeRole = '';

  // 电商Demo数据库的所有表
  const ALL_TABLES = [
    {name: 'users', desc: '用户表'},
    {name: 'orders', desc: '订单表'},
    {name: 'order_items', desc: '订单明细表'},
    {name: 'products', desc: '商品表'},
    {name: 'categories', desc: '品类表'},
    {name: 'reviews', desc: '评价表'},
    {name: 'addresses', desc: '地址表'},
    {name: 'coupons', desc: '优惠券表'},
    {name: 'login_logs', desc: '登录日志表'},
  ];

  function init() {
    Router.on('sql-perm', load);
  }

  async function load() {
    await loadPermissions();
    render();
  }

  async function loadPermissions() {
    try {
      const data = await API.request('/api/sql/permissions');
      _perms = data.items || [];
      _roles = data.roles || [];
      _tables = data.tables || [];
    } catch (e) {
      console.error('加载权限失败:', e);
      _perms = [];
      _roles = [];
    }
  }

  function render() {
    // 渲染角色下拉框
    const selectEl = document.getElementById('perm-role-filter');
    if (selectEl) {
      selectEl.innerHTML = '<option value="">选择角色查看权限</option>' +
        _roles.map(r => `<option value="${r}"${r === _activeRole ? ' selected' : ''}>${r}</option>`).join('');
    }

    // 渲染权限表格
    const tbody = document.getElementById('perm-table-body');
    if (!tbody) return;

    if (!_activeRole) {
      tbody.innerHTML = '<tr><td colspan="5" class="empty">请选择角色</td></tr>';
      return;
    }

    const rolePerms = _perms.filter(p => p.role === _activeRole);
    const permMap = {};
    rolePerms.forEach(p => { permMap[p.table_name] = p; });

    tbody.innerHTML = ALL_TABLES.map(t => {
      const p = permMap[t.name] || {};
      const canQuery = p.can_query !== false;
      const maxRows = p.max_rows || 500;
      const denyCols = p.columns_deny || '';
      const permId = p.id || '';

      return `<tr>
        <td><strong>${t.name}</strong><br><span style="color:#999;font-size:12px">${t.desc}</span></td>
        <td>
          <label class="toggle-switch">
            <input type="checkbox" ${canQuery ? 'checked' : ''} onchange="PageSQLPerm.toggleQuery('${t.name}', this.checked)">
            <span class="toggle-slider"></span>
          </label>
          <span style="margin-left:8px;${canQuery ? 'color:#52c41a' : 'color:#ff4d4f'}">${canQuery ? '允许' : '禁止'}</span>
        </td>
        <td>
          <div style="display:flex;gap:4px;align-items:center">
            <input type="number" value="${maxRows}" min="0" max="10000" style="width:80px;padding:4px" id="maxrows-${t.name}" ${!canQuery ? 'disabled' : ''}>
            <button class="btn btn-xs" onclick="PageSQLPerm.updateMaxRows('${t.name}')" ${!canQuery ? 'disabled' : ''}>💾</button>
          </div>
        </td>
        <td>
          <div style="display:flex;gap:4px;align-items:center">
            <input type="text" value="${denyCols}" placeholder="如: password,salary" style="width:150px;padding:4px" id="denycols-${t.name}" ${!canQuery ? 'disabled' : ''}>
            <button class="btn btn-xs" onclick="PageSQLPerm.updateDenyCols('${t.name}')" ${!canQuery ? 'disabled' : ''}>💾</button>
          </div>
        </td>
      </tr>`;
    }).join('');
  }

  function filterRole(role) {
    _activeRole = role;
    render();
  }

  async function toggleQuery(tableName, canQuery) {
    const p = _perms.find(x => x.role === _activeRole && x.table_name === tableName);
    if (p) {
      await API.request(`/api/sql/permissions/${p.id}`, {
        method: 'PUT',
        body: { can_query: canQuery },
      });
    } else {
      await API.request('/api/sql/permissions', {
        method: 'POST',
        body: { role: _activeRole, table_name: tableName, can_query: canQuery },
      });
    }
    await loadPermissions();
    render();
  }

  async function updateMaxRows(tableName) {
    const input = document.getElementById('maxrows-' + tableName);
    const maxRows = parseInt(input.value);
    const p = _perms.find(x => x.role === _activeRole && x.table_name === tableName);
    if (p) {
      try {
        await API.request(`/api/sql/permissions/${p.id}`, {
          method: 'PUT',
          body: { max_rows: maxRows },
        });
        input.style.borderColor = '#52c41a';
        setTimeout(() => { input.style.borderColor = ''; }, 1500);
      } catch (e) {
        input.style.borderColor = '#ff4d4f';
        alert('保存失败: ' + e.message);
      }
    }
  }

  async function updateDenyCols(tableName) {
    const input = document.getElementById('denycols-' + tableName);
    const denyCols = input.value;
    const p = _perms.find(x => x.role === _activeRole && x.table_name === tableName);
    if (p) {
      try {
        await API.request(`/api/sql/permissions/${p.id}`, {
          method: 'PUT',
          body: { columns_deny: denyCols },
        });
        input.style.borderColor = '#52c41a';
        setTimeout(() => { input.style.borderColor = ''; }, 1500);
      } catch (e) {
        input.style.borderColor = '#ff4d4f';
        alert('保存失败: ' + e.message);
      }
    }
  }

  return { init, load, filterRole, toggleQuery, updateMaxRows, updateDenyCols };
})();
