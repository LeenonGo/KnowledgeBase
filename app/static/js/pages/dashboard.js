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
          // 对数缩放：小值有区分度，大值不会过高
          let h;
          if (d.count === 0) { h = 4; }
          else if (maxVal <= 5) { h = 20 + Math.round((d.count / maxVal) * 100); }
          else { h = Math.round(Math.log(1 + d.count) / Math.log(1 + maxVal) * 120); }
          h = Math.max(4, Math.min(120, h));
          const isToday = d.date === new Date().toISOString().slice(5, 10).replace('-', '-');
          return `<div class="bar" style="height:${h}px;background:${isToday ? '#1890ff' : '#91caff'};${d.count === 0 ? 'opacity:0.3' : ''}">
            <span class="bar-value">${d.count}</span>
            <span class="bar-label">${d.date}</span>
          </div>`;
        }).join('');
      }

      // 待处理事项
      const qualStats = await API.request('/api/stats/quality');
      document.getElementById('todo-down').textContent = qualStats.down_count || 0;
      document.getElementById('todo-queries').textContent = qualStats.today_queries || 0;

      // 解析失败数
      try {
        const docs = await API.request('/api/documents?page=1&page_size=1');
        // 如果有 failed 状态的文档可以统计
        document.getElementById('todo-failed').textContent = 0;
      } catch {}

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
