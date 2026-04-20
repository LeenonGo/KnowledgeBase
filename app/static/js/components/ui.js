/**
 * UI 通用组件 — 分页、模态框、Tab 切换、Markdown 渲染
 */
const UI = (() => {

  // ─── 分页 ────────────────────────────────────────
  function renderPagination(containerId, total, page, pageSize, onPageChange) {
    const container = document.getElementById(containerId);
    if (!container) return;
    const totalPages = Math.ceil(total / pageSize);
    if (totalPages <= 1) { container.innerHTML = ''; return; }
    let html = '<div class="pagination">';
    if (page > 1) html += `<div class="page-btn" onclick="${onPageChange}(${page - 1})">‹</div>`;
    for (let p = 1; p <= totalPages; p++) {
      if (p === page) html += `<div class="page-btn active">${p}</div>`;
      else if (Math.abs(p - page) <= 2 || p === 1 || p === totalPages)
        html += `<div class="page-btn" onclick="${onPageChange}(${p})">${p}</div>`;
      else if (Math.abs(p - page) === 3) html += '<div class="page-btn">...</div>';
    }
    if (page < totalPages) html += `<div class="page-btn" onclick="${onPageChange}(${page + 1})">›</div>`;
    html += '</div>';
    container.innerHTML = html;
  }

  // ─── 模态框 ──────────────────────────────────────
  function showModal(name) {
    document.getElementById('modal-overlay').style.display = 'flex';
    document.getElementById('modal-' + name).style.display = 'block';
  }

  function hideModal() {
    document.getElementById('modal-overlay').style.display = 'none';
    document.querySelectorAll('.modal').forEach(m => m.style.display = 'none');
  }

  // ─── Tab 切换 ────────────────────────────────────
  function switchTab(tab, tabId) {
    tab.parentElement.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
    const panels = tab.parentElement.parentElement.querySelectorAll(':scope > div[id]');
    panels.forEach(el => {
      if (el.id && el.id.includes('-tab-')) el.style.display = 'none';
    });
    document.getElementById(tabId).style.display = 'block';
    return tabId; // 返回当前 tab id，方便页面回调
  }

  // ─── Markdown → HTML ────────────────────────────
  function md2html(md) {
    if (!md) return '';
    let html = md;
    html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (m, lang, code) =>
      `<pre style="background:#1e1e1e;color:#d4d4d4;padding:12px;border-radius:6px;overflow-x:auto;font-size:13px;margin:8px 0;"><code>${code.replace(/</g,'&lt;').replace(/>/g,'&gt;')}</code></pre>`
    );
    html = html.replace(/`([^`]+)`/g, '<code style="background:#f0f0f0;padding:2px 6px;border-radius:3px;font-size:13px;">$1</code>');
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
    html = html.replace(/^### (.+)$/gm, '<h4 style="margin:12px 0 6px;font-size:15px;">$1</h4>');
    html = html.replace(/^## (.+)$/gm, '<h3 style="margin:14px 0 8px;font-size:16px;">$1</h3>');
    html = html.replace(/^# (.+)$/gm, '<h2 style="margin:16px 0 8px;font-size:18px;">$1</h2>');
    html = html.replace(/^- (.+)$/gm, '<li style="margin-left:16px;">$1</li>');
    html = html.replace(/^\d+\. (.+)$/gm, '<li style="margin-left:16px;list-style:decimal;">$1</li>');
    html = html.replace(/\n\n/g, '</p><p style="margin:8px 0;">');
    html = html.replace(/\n/g, '<br>');
    html = html.replace(/\[来源: ([^\]]+)\]/g,
      '<span class="source-tag" style="display:inline-block;font-size:11px;background:#e6f7ff;color:#1890ff;padding:2px 8px;border-radius:4px;margin:2px;border:1px solid #91d5ff;">📎 $1</span>'
    );
    return '<p style="margin:0;">' + html + '</p>';
  }

  // ─── 部门下拉填充 ────────────────────────────────
  let deptList = [];
  async function loadDepts() {
    try { deptList = await API.request('/api/departments'); }
    catch { deptList = []; }
    return deptList;
  }
  function fillDeptSelect(selectId, selectedId) {
    const sel = document.getElementById(selectId);
    if (!sel) return;
    sel.innerHTML = '<option value="">-- 无 --</option>' +
      deptList.map(d => `<option value="${d.id}"${d.id === selectedId ? ' selected' : ''}>${d.name}</option>`).join('');
  }

  return {
    renderPagination, showModal, hideModal, switchTab, md2html,
    loadDepts, fillDeptSelect, getDeptList: () => deptList,
  };
})();
