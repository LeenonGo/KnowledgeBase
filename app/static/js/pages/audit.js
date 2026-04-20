/**
 * 审计日志页
 */
const PageAudit = (() => {
  let auditPage = 1;

  async function load(page) {
    auditPage = page || 1;
    const action = document.getElementById('audit-action-filter').value;
    let url = `/api/audit-logs?page=${auditPage}&page_size=20`;
    if (action) url += '&action=' + action;
    try {
      const data = await API.request(url);
      const logs = data.items || [];
      const tbody = document.getElementById('audit-log-body');
      document.getElementById('audit-count').textContent = data.total + ' 条记录';
      UI.renderPagination('audit-pagination', data.total, auditPage, 20, 'PageAudit.load');
      if (!logs.length) {
        tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:40px;color:#999;">暂无数据</td></tr>';
        return;
      }
      const labels = {login:'登录',upload:'上传',delete_doc:'删除文档',query:'查询',create_kb:'创建知识库',delete_kb:'删除知识库',create_user:'创建用户',delete_user:'删除用户',config_models:'配置模型',reindex:'重建索引',create_dept:'创建部门',delete_dept:'删除部门'};
      tbody.innerHTML = logs.map(l => {
        const time = l.created_at ? l.created_at.replace('T',' ').substring(0,19) : '';
        const actionLabel = labels[l.action] || l.action;
        const statusTag = l.status === 'success' ? '<span class="tag tag-green">成功</span>' : '<span class="tag tag-red">失败</span>';
        return `<tr><td>${time}</td><td>${l.username}</td><td>${l.ip_address}</td><td>${actionLabel}</td><td>${l.resource}</td><td>${l.detail||''}</td><td>${statusTag}</td></tr>`;
      }).join('');
    } catch (e) { console.error('加载审计日志失败', e); }
  }

  return { load };
})();

Router.on('audit-log', () => PageAudit.load());
