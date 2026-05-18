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

  /**
   * 动态模态框：传入标题、HTML 内容、按钮数组
   * buttons: [{ text, class, onClick }]
   */
  function showDynamicModal(title, bodyHtml, buttons) {
    // 移除上一个动态模态框
    const old = document.getElementById('modal-dynamic');
    if (old) old.remove();

    const btnsHtml = (buttons || []).map((b, i) => {
      const cls = b.class || 'btn';
      return `<button class="${cls}" id="modal-dyn-btn-${i}">${b.text}</button>`;
    }).join('');

    const div = document.createElement('div');
    div.id = 'modal-dynamic';
    div.className = 'modal';
    div.style.cssText = 'display:block;max-width:640px;width:90vw;max-height:80vh;overflow-y:auto;';
    div.innerHTML = `
      <div class="modal-header">
        <span>${title}</span>
        <button onclick="UI.hideModal()" style="border:none;background:none;font-size:20px;cursor:pointer;">×</button>
      </div>
      <div class="modal-body">${bodyHtml}</div>
      <div class="modal-footer">${btnsHtml}</div>
    `;

    document.getElementById('modal-overlay').style.display = 'flex';
    document.getElementById('modal-overlay').appendChild(div);

    // 绑定按钮事件
    (buttons || []).forEach((b, i) => {
      const btn = document.getElementById(`modal-dyn-btn-${i}`);
      if (btn && b.onClick) btn.addEventListener('click', b.onClick);
    });
  }

  function hideModal() {
    document.getElementById('modal-overlay').style.display = 'none';
    document.querySelectorAll('.modal').forEach(m => m.style.display = 'none');
    const dyn = document.getElementById('modal-dynamic');
    if (dyn) dyn.remove();
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

    // 1. 代码块（必须在其他规则之前）
    html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (m, lang, code) =>
      `<pre class="md-code"><code>${code.replace(/</g,'&lt;').replace(/>/g,'&gt;')}</code></pre>`
    );

    // 2. 表格（在换行处理之前，按行解析）
    html = html.replace(/(^|\n)((?:\|.+)\|\n)+/gm, (match) => {
      const lines = match.trim().split('\n').filter(l => l.trim());
      if (lines.length < 2) return match;
      // 检查第二行是否是分隔行 :---:|---:|---
      if (!/^\|[-:\s|]+\|$/.test(lines[1].trim())) return match;
      // 解析表头
      const headerCells = lines[0].split('|').slice(1, -1);
      if (!headerCells.length) return match;
      // 解析表体（跳过分隔行）
      const bodyRows = [];
      for (let i = 2; i < lines.length; i++) {
        const cells = lines[i].split('|').slice(1, -1);
        if (cells.length) bodyRows.push(cells);
      }
      // 渲染
      let table = '<table class="md-table"><thead><tr>';
      headerCells.forEach(c => { table += `<th>${c.trim()}</th>`; });
      table += '</tr></thead><tbody>';
      bodyRows.forEach(row => {
        table += '<tr>';
        row.forEach(c => { table += `<td>${c.trim()}</td>`; });
        table += '</tr>';
      });
      table += '</tbody></table>';
      return '\n' + table + '\n';
    });

    // 3. 引用块
    html = html.replace(/(^|\n)> (.+)/gm, '$1<blockquote class="md-blockquote">$2</blockquote>');
    // 合并连续 blockquote
    html = html.replace(/<\/blockquote>\n<blockquote class="md-blockquote">/g, '<br>');

    // 4. 水平线
    html = html.replace(/(^|\n)---+(\n|$)/g, '$1<hr class="md-hr">$2');

    // 5. 标题
    html = html.replace(/^#### (.+)$/gm, '<h4 class="md-h4">$1</h4>');
    html = html.replace(/^### (.+)$/gm, '<h3 class="md-h3">$1</h3>');
    html = html.replace(/^## (.+)$/gm, '<h2 class="md-h2">$1</h2>');
    html = html.replace(/^# (.+)$/gm, '<h1 class="md-h1">$1</h1>');

    // 6. 粗体/斜体/行内代码
    html = html.replace(/`([^`]+)`/g, '<code class="md-inline-code">$1</code>');
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');

    // 7. 无序列表
    html = html.replace(/(^|\n)(- .+(?:\n- .+)*)/gm, (match) => {
      const items = match.trim().split('\n').map(i => `<li>${i.replace(/^- /, '')}</li>`).join('');
      return `<ul class="md-ul">${items}</ul>`;
    });

    // 8. 有序列表
    html = html.replace(/(^|\n)(\d+\. .+(?:\n\d+\. .+)*)/gm, (match) => {
      const items = match.trim().split('\n').map(i => `<li>${i.replace(/^\d+\. /, '')}</li>`).join('');
      return `<ol class="md-ol">${items}</ol>`;
    });

    // 9. 来源标签
    html = html.replace(/\[来源: ([^\]]+)\]/g,
      '<span class="source-tag">📎 $1</span>'
    );

    // 10. 段落（双换行 → <p>，单换行 → <br>）
    html = html.replace(/\n\n/g, '</p><p class="md-p">');
    html = html.replace(/\n/g, '<br>');

    return '<p class="md-p">' + html + '</p>';
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

  // ─── HTML 转义 ────────────────────────────────────
  function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  // ─── 图表渲染 ────────────────────────────────────
  // 预处理：提取 [CHART] 块，避免被 md2html 破坏
  function extractCharts(md) {
    const charts = [];
    const placeholder = md.replace(/\[CHART\][\s\S]*?\[\/CHART\]/g, (match) => {
      const idx = charts.length;
      charts.push(match.replace('[CHART]', '').replace('[/CHART]', '').trim());
      return `__CHART_${idx}__`;
    });
    return { text: placeholder, charts };
  }

  // 后处理：把 __CHART_N__ 占位符替换为实际图表 DOM
  function renderCharts(container, charts) {
    if (!charts || !charts.length || typeof echarts === 'undefined') return;
    const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT, null, false);
    const textNodes = [];
    while (walker.nextNode()) textNodes.push(walker.currentNode);

    textNodes.forEach(node => {
      const match = node.textContent.match(/__CHART_(\d+)__/);
      if (!match) return;
      const idx = parseInt(match[1]);
      if (idx >= charts.length) return;
      try {
        const option = JSON.parse(charts[idx]);
        const chartDiv = document.createElement('div');
        chartDiv.className = 'echart-container';
        chartDiv.style.cssText = 'width:100%;height:320px;margin:12px 0;';
        const before = node.textContent.slice(0, match.index);
        const after = node.textContent.slice(match.index + match[0].length);
        const parent = node.parentNode;
        if (before) parent.insertBefore(document.createTextNode(before), node);
        parent.insertBefore(chartDiv, node);
        if (after) parent.insertBefore(document.createTextNode(after), node);
        parent.removeChild(node);
        const chart = echarts.init(chartDiv);
        chart.setOption(option);
        const ro = new ResizeObserver(() => chart.resize());
        ro.observe(chartDiv);
      } catch (e) {
        console.warn('[Chart] 解析失败:', e);
      }
    });
  }

  return {
    renderPagination, showModal, showDynamicModal, hideModal, switchTab, md2html, escapeHtml,
    extractCharts, renderCharts,
    loadDepts, fillDeptSelect, getDeptList: () => deptList,
  };
})();
