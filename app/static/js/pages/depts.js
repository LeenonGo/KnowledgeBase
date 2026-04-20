/**
 * 部门管理页
 */
const PageDepts = (() => {
  async function load() {
    const depts = await UI.loadDepts();
    const card = document.querySelector('#dept-tree .card');
    if (!depts.length) {
      card.innerHTML = '<div class="text-muted" style="text-align:center;padding:40px;">暂无部门</div>';
      return;
    }
    const root = depts.find(d => !d.parent_id);
    const children = depts.filter(d => d.parent_id);
    let html = '';
    if (root) {
      html += `<div class="tree-item" style="padding-left:8px;">
        <div class="node">🏢 <strong>${root.name}</strong> <span class="text-muted">${root.path}</span></div>`;
      children.forEach(c => {
        html += `<div class="tree-item" style="padding-left:32px;">
          <div class="node">📂 ${c.name} <span class="text-muted">${c.path}</span></div></div>`;
      });
      html += '</div>';
    }
    card.innerHTML = html;
  }

  async function create() {
    const name = document.getElementById('new-dept-name').value.trim();
    if (!name) { alert('请输入部门名称'); return; }
    try {
      await API.request('/api/departments', {
        method: 'POST',
        body: {
          name,
          parent_id: document.getElementById('new-dept-parent').value || null,
          description: document.getElementById('new-dept-desc').value,
        },
      });
      UI.hideModal();
      load();
    } catch { alert('创建失败'); }
  }

  return { load, create };
})();

Router.on('dept-tree', () => PageDepts.load());
