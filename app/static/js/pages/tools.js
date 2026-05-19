/**
 * 工具管理页 — 插件化工具注册
 */
const PageTools = (() => {
  let _tools = [];
  let _categories = [];
  let _activeCategory = '';

  function init() {
    Router.on('tool-mgmt', load);
  }

  async function load() {
    await loadTools();
    render();
  }

  async function loadTools() {
    try {
      const data = await API.request('/api/tools');
      _tools = data.items || [];
      _categories = data.categories || [];
    } catch (e) {
      console.error('加载工具列表失败:', e);
      _tools = [];
      _categories = [];
    }
  }

  function render() {
    // 渲染分类下拉框选项
    const selectEl = document.getElementById('tool-category-filter');
    if (selectEl) {
      const currentVal = selectEl.value;
      selectEl.innerHTML = '<option value="">全部分类</option>' +
        _categories.map(c => `<option value="${c}"${c === currentVal ? ' selected' : ''}>${c}</option>`).join('');
    }

    // 搜索过滤
    const searchInput = document.getElementById('tool-search');
    const keyword = (searchInput?.value || '').trim().toLowerCase();

    // 渲染表格
    const tbody = document.getElementById('tool-table-body');
    if (!tbody) return;

    let filtered = _tools;
    if (_activeCategory) {
      filtered = filtered.filter(t => t.category === _activeCategory);
    }
    if (keyword) {
      filtered = filtered.filter(t =>
        t.name.toLowerCase().includes(keyword) ||
        t.description.toLowerCase().includes(keyword)
      );
    }

    if (!filtered.length) {
      tbody.innerHTML = '<tr><td colspan="6" class="empty">暂无工具</td></tr>';
      return;
    }

    const categoryBadge = {
      'kb': '📚 知识库',
      'sql': '📊 SQL',
      'kg': '🕸️ 图谱',
      'system': '⚙️ 系统',
      'general': '🔧 通用',
    };

    tbody.innerHTML = filtered.map(t => `
      <tr>
        <td><strong>${UI.escapeHtml(t.name)}</strong>${t.is_builtin ? ' <span class="tag tag-blue">内置</span>' : ''}</td>
        <td style="max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${UI.escapeHtml(t.description)}">${UI.escapeHtml(t.description.slice(0, 50))}${t.description.length > 50 ? '...' : ''}</td>
        <td>${categoryBadge[t.category] || t.category}</td>
        <td>${t.is_active ? '<span style="color:#52c41a">● 启用</span>' : '<span style="color:#ff4d4f">● 禁用</span>'}</td>
        <td>
          <button class="btn btn-xs" onclick="PageTools.toggleActive(${t.id}, ${!t.is_active})">${t.is_active ? '禁用' : '启用'}</button>
          ${!t.is_builtin ? `<button class="btn btn-xs" style="margin-left:4px" onclick="PageTools.deleteTool(${t.id}, '${t.name}')">删除</button>` : ''}
        </td>
      </tr>
    `).join('');
  }

  function filterCategory(cat) {
    _activeCategory = cat;
    render();
  }

  async function toggleActive(id, newActive) {
    try {
      await API.request(`/api/tools/${id}`, {
        method: 'PUT',
        body: { is_active: newActive },
      });
      await loadTools();
      render();
    } catch (e) {
      alert('操作失败: ' + e.message);
    }
  }

  async function deleteTool(id, name) {
    if (!confirm(`确定删除工具「${name}」？`)) return;
    try {
      await API.request(`/api/tools/${id}`, { method: 'DELETE' });
      await loadTools();
      render();
    } catch (e) {
      alert('删除失败: ' + e.message);
    }
  }

  function showCreateModal() {
    UI.showDynamicModal('新增工具', `
      <div class="form-group"><label>工具名称 *</label><input id="new-tool-name" class="input" placeholder="如：my_weather"></div>
      <div class="form-group"><label>描述 *</label><textarea id="new-tool-desc" class="input" rows="2" placeholder="给 LLM 看的功能描述"></textarea></div>
      <div class="form-group"><label>分类</label>
        <select id="new-tool-category" class="select">
          <option value="general">🔧 通用</option>
          <option value="kb">📚 知识库</option>
          <option value="sql">📊 SQL</option>
          <option value="kg">🕸️ 图谱</option>
          <option value="system">⚙️ 系统</option>
        </select>
      </div>
      <div class="form-group"><label>Handler 路径 *</label><input id="new-tool-handler" class="input" placeholder="app.core.tools:my_function"></div>
      <div class="form-group"><label>参数 JSON Schema</label><textarea id="new-tool-params" class="input" rows="4" placeholder='{"type":"object","properties":{},"required":[]}'></textarea></div>
    `, [
      {
        text: '取消',
        class: 'btn',
        onClick: () => UI.hideModal()
      },
      {
        text: '创建',
        class: 'btn btn-primary',
        onClick: async () => {
          const name = document.getElementById('new-tool-name').value.trim();
          const desc = document.getElementById('new-tool-desc').value.trim();
          const category = document.getElementById('new-tool-category').value;
          const handler = document.getElementById('new-tool-handler').value.trim();
          let params = {};
          try {
            const pStr = document.getElementById('new-tool-params').value.trim();
            if (pStr) params = JSON.parse(pStr);
          } catch (e) {
            alert('JSON Schema 格式错误');
            return;
          }

          if (!name || !desc || !handler) {
            alert('请填写必填项');
            return;
          }

          try {
            await API.request('/api/tools', {
              method: 'POST',
              body: { name, description: desc, parameters: params, handler, category },
            });
            UI.hideModal();
            await loadTools();
            render();
            alert('创建成功');
          } catch (e) {
            alert('创建失败: ' + e.message);
          }
        }
      }
    ]);
  }

  return { init, load, filterCategory, toggleActive, deleteTool, showCreateModal, searchTools: render };
})();
