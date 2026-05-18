/**
 * SQL 查询审计日志页
 */
const PageSQLAudit = (() => {
  let currentPage = 1;

  function init() {
    Router.on('sql-audit', load);
  }

  async function load() {
    currentPage = 1;
    await loadLogs();
  }

  async function loadLogs(page) {
    if (page) currentPage = page;
    const status = document.getElementById('sql-audit-status-filter')?.value || '';
    const format = document.getElementById('sql-audit-format-filter')?.value || '';

    let url = `/api/sql/audit-logs?page=${currentPage}&page_size=20`;
    if (status) url += `&status=${status}`;
    if (format) url += `&output_format=${format}`;

    try {
      const data = await API.request(url);
      renderTable(data.items || []);
      document.getElementById('sql-audit-count').textContent = `共 ${data.total} 条`;
      UI.renderPagination('sql-audit-pagination', data.total, currentPage, 20, 'PageSQLAudit.loadLogs');
    } catch (e) {
      document.getElementById('sql-audit-body').innerHTML =
        `<tr><td colspan="7" class="empty">加载失败: ${e.message}</td></tr>`;
    }
  }

  function renderTable(items) {
    const tbody = document.getElementById('sql-audit-body');
    if (!items.length) {
      tbody.innerHTML = '<tr><td colspan="7" class="empty">暂无查询记录</td></tr>';
      return;
    }

    const formatBadge = { table: '📊 表格', json: '📋 JSON', report: '📝 报告' };
    const statusBadge = s => s === 'success'
      ? '<span style="color:#52c41a">● 成功</span>'
      : '<span style="color:#ff4d4f">● 失败</span>';

    tbody.innerHTML = items.map(l => {
      const time = l.created_at ? l.created_at.slice(0, 16).replace('T', ' ') : '';
      const q = l.question.length > 30 ? l.question.slice(0, 30) + '…' : l.question;
      return `<tr style="cursor:pointer" onclick="PageSQLAudit.showDetail('${l.id}')">
        <td style="white-space:nowrap">${time}</td>
        <td>${UI.escapeHtml(l.username)}</td>
        <td>${UI.escapeHtml(q)}</td>
        <td>${formatBadge[l.output_format] || l.output_format}</td>
        <td>${l.row_count}</td>
        <td>${l.total_ms}ms</td>
        <td>${statusBadge(l.status)}</td>
      </tr>`;
    }).join('');
  }

  let _allLogs = [];

  async function showDetail(id) {
    // 从当前页数据中查找
    try {
      const data = await API.request(`/api/sql/audit-logs?page=${currentPage}&page_size=100`);
      _allLogs = data.items || [];
    } catch(e) { return; }

    const log = _allLogs.find(l => l.id === id);
    if (!log) return;

    const panel = document.getElementById('sql-audit-detail');
    panel.style.display = 'block';

    const sql = log.generated_sql || '(无)';
    const errorHtml = log.error
      ? `<div style="color:#ff4d4f;margin-top:8px"><strong>❌ 错误：</strong>${UI.escapeHtml(log.error)}</div>`
      : '';

    panel.innerHTML = `
      <div class="card">
        <div class="flex-between">
          <h3 style="margin:0">📋 查询详情</h3>
          <button class="btn btn-sm" onclick="document.getElementById('sql-audit-detail').style.display='none'">✕ 关闭</button>
        </div>
        <div style="margin-top:12px">
          <p><strong>问题：</strong>${UI.escapeHtml(log.question)}</p>
          <p><strong>输出格式：</strong>${log.output_format} · <strong>用户：</strong>${UI.escapeHtml(log.username)} · <strong>时间：</strong>${log.created_at}</p>
          <p><strong>行数：</strong>${log.row_count} · <strong>SQL耗时：</strong>${log.elapsed_ms}ms · <strong>总耗时：</strong>${log.total_ms}ms</p>
          <div style="margin-top:8px">
            <strong>生成的 SQL：</strong>
            <pre class="sql-code" style="margin-top:4px">${UI.escapeHtml(sql)}</pre>
          </div>
          ${errorHtml}
        </div>
      </div>`;
  }

  return { init, load, loadLogs, showDetail };
})();
