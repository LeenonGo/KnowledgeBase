/**
 * 仪表盘页
 */
const PageDashboard = (() => {
  async function load() {
    try {
      const [docData, kbData] = await Promise.all([
        API.request('/api/documents?page=1&page_size=1'),
        API.request('/api/knowledge-bases?page=1&page_size=5'),
      ]);
      document.getElementById('stat-docs').textContent = docData.total || 0;
      document.getElementById('stat-kb').textContent = kbData.total || 0;
      document.getElementById('kb-total').textContent = kbData.total || 0;

      const kbs = kbData.items || [];
      const hotEl = document.getElementById('hot-kb-list');
      if (!kbs.length) {
        hotEl.innerHTML = '<div class="text-muted" style="padding:20px;text-align:center;">暂无知识库</div>';
      } else {
        hotEl.innerHTML = kbs.map(k =>
          `<div class="flex-between" style="padding:8px;border-bottom:1px solid #f5f5f5;">
            <span>📖 ${k.name}</span><span class="tag tag-blue">活跃</span></div>`
        ).join('');
      }
    } catch (e) { console.error('Dashboard error:', e); }
  }

  return { load };
})();

Router.on('dashboard', () => PageDashboard.load());
