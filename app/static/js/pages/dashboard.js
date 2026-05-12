/**
 * 仪表盘页
 */
const PageDashboard = (() => {
  let _resizeHandler = null;
  let _chart = null;

  async function load() {
    // 清理旧监听器
    if (_resizeHandler) { window.removeEventListener('resize', _resizeHandler); _resizeHandler = null; }
    if (_chart) { _chart.dispose(); _chart = null; }

    // 知识库健康度
    try {
      const health = await API.request('/api/stats/kb-health');
      const kbs = health.knowledge_bases || [];
      const overall = health.overall || {};
      document.getElementById('health-kb-count').textContent = overall.kb_count || 0;
      document.getElementById('health-doc-count').textContent = overall.total_docs || 0;
      renderHealthTable(kbs);
      renderHealthChart(kbs);
    } catch (e) { console.error('Health data error:', e); }

    // 7 天趋势图
    try {
      const data = await API.request('/api/stats/dashboard');
      const chartEl = document.getElementById('query-chart');
      if (chartEl && data.daily_queries?.length) {
        const maxVal = Math.max(...data.daily_queries.map(d => d.count), 1);
        chartEl.innerHTML = data.daily_queries.map(d => {
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
    } catch (e) { console.error('Dashboard error:', e); }

    // 待处理事项
    try {
      const qualStats = await API.request('/api/stats/quality');
      document.getElementById('todo-down').textContent = qualStats.down_count || 0;
      document.getElementById('todo-queries').textContent = qualStats.today_queries || 0;
      document.getElementById('todo-failed').textContent = 0;
    } catch {}
  }

  function renderHealthTable(kbs) {
    const tbody = document.getElementById('health-table-body');
    if (!tbody || !kbs.length) return;
    tbody.innerHTML = kbs.map(kb => {
      const extStr = Object.entries(kb.ext_distribution || {}).map(([k, v]) => `${k}(${v})`).join(', ') || '-';
      const scoreColor = kb.health_score >= 80 ? '#52c41a' : (kb.health_score >= 60 ? '#faad14' : '#ff4d4f');
      const scoreBg = kb.health_score >= 80 ? '#f6ffed' : (kb.health_score >= 60 ? '#fffbe6' : '#fff2f0');
      return `<tr>
        <td><strong>${kb.name}</strong></td>
        <td>${kb.doc_count}</td>
        <td>${kb.chunk_count}</td>
        <td style="font-size:12px;">${extStr}</td>
        <td>${kb.query_count_7d}</td>
        <td><span style="padding:2px 10px;border-radius:12px;font-weight:600;font-size:13px;color:${scoreColor};background:${scoreBg};">${kb.health_score}</span></td>
      </tr>`;
    }).join('');
  }

  function renderHealthChart(kbs) {
    if (!kbs.length || typeof echarts === 'undefined') return;
    const el = document.getElementById('health-score-chart');
    if (!el) return;
    _chart = echarts.init(el);
    _chart.setOption({
      tooltip: {},
      radar: { indicator: kbs.map(k => ({ name: k.name.substring(0, 6), max: 100 })), radius: '60%' },
      series: [{ type: 'radar', data: [{ value: kbs.map(k => k.health_score), name: '健康度', areaStyle: { opacity: 0.15 } }] }],
    });
    _resizeHandler = () => _chart && _chart.resize();
    window.addEventListener('resize', _resizeHandler);
  }

  return { load };
})();

Router.on('dashboard', () => PageDashboard.load());
