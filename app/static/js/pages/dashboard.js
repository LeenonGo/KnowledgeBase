/**
 * 仪表盘页
 */
const PageDashboard = (() => {
  async function load() {
    try {
      const data = await API.request('/api/stats/dashboard');

      // 统计卡片
      document.getElementById('stat-kb').textContent = data.kb_count;
      document.getElementById('stat-docs').textContent = data.doc_count;
      document.getElementById('stat-queries').textContent = data.today_queries;
      document.getElementById('stat-likes').textContent = data.like_rate + '%';
      document.getElementById('kb-total').textContent = data.kb_count;

      // 7 天趋势图
      const chartEl = document.getElementById('query-chart');
      if (chartEl && data.daily_queries?.length) {
        const maxVal = Math.max(...data.daily_queries.map(d => d.count), 1);
        chartEl.innerHTML = data.daily_queries.map(d => {
          const h = Math.max(20, Math.round(d.count / maxVal * 120));
          const isToday = d.date === new Date().toISOString().slice(5, 10).replace('-', '-');
          return `<div class="bar" style="height:${h}px;background:${isToday ? '#1890ff' : '#91caff'};">
            <span class="bar-value">${d.count}</span>
            <span class="bar-label">${d.date}</span>
          </div>`;
        }).join('');
      }

      // 热门知识库
      const kbData = await API.request('/api/knowledge-bases?page=1&page_size=5');
      const kbs = kbData.items || [];
      const hotEl = document.getElementById('hot-kb-list');
      if (!kbs.length) {
        hotEl.innerHTML = '<div class="text-muted" style="padding:20px;text-align:center;">暂无知识库</div>';
      } else {
        hotEl.innerHTML = kbs.map(k =>
          `<div class="flex-between" style="padding:8px;border-bottom:1px solid #f5f5f5;">
            <span>📖 ${k.name}</span>
            <span class="text-muted">${k.doc_count} 文档</span></div>`
        ).join('');
      }
    } catch (e) { console.error('Dashboard error:', e); }
  }

  return { load };
})();

Router.on('dashboard', () => PageDashboard.load());
