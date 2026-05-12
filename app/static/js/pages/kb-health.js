/**
 * 知识库健康度看板
 */
const PageKBHealth = (() => {

  async function load() {
    try {
      const data = await API.request('/api/stats/kb-health');
      renderOverview(data.overall);
      renderTable(data.knowledge_bases);
      renderCharts(data.knowledge_bases);
    } catch (e) {
      console.error('加载健康度数据失败:', e);
    }
  }

  function renderOverview(overall) {
    const el = document.getElementById('health-overview');
    if (!el || !overall) return;
    const cards = [
      { label: '知识库总数', value: overall.kb_count, icon: '📂', color: '#1890ff' },
      { label: '文档总数', value: overall.total_docs, icon: '📄', color: '#52c41a' },
      { label: '分块总数', value: overall.total_chunks, icon: '🧩', color: '#722ed1' },
      { label: '健康知识库', value: `${overall.healthy_kb_count}/${overall.kb_count}`, icon: '💚', color: '#13c2c2' },
    ];
    el.innerHTML = cards.map(c => `
      <div class="card" style="text-align:center;padding:20px;">
        <div style="font-size:32px;margin-bottom:8px;">${c.icon}</div>
        <div style="font-size:28px;font-weight:700;color:${c.color};">${c.value}</div>
        <div style="font-size:13px;color:#999;margin-top:4px;">${c.label}</div>
      </div>
    `).join('');
  }

  function renderTable(kbs) {
    const tbody = document.getElementById('health-table-body');
    if (!tbody) return;
    if (!kbs || !kbs.length) {
      tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:40px;color:#999;">暂无数据</td></tr>';
      return;
    }
    tbody.innerHTML = kbs.map(kb => {
      const extStr = Object.entries(kb.ext_distribution || {}).map(([k, v]) => `${k}(${v})`).join(', ') || '-';
      const scoreColor = kb.health_score >= 80 ? '#52c41a' : (kb.health_score >= 60 ? '#faad14' : '#ff4d4f');
      const scoreBg = kb.health_score >= 80 ? '#f6ffed' : (kb.health_score >= 60 ? '#fffbe6' : '#fff2f0');
      return `<tr>
        <td><strong>${kb.name}</strong><br><span style="font-size:11px;color:#999;">${kb.description || ''}</span></td>
        <td>${kb.doc_count}</td>
        <td>${kb.chunk_count}</td>
        <td>${kb.total_chars ? (kb.total_chars > 10000 ? (kb.total_chars / 10000).toFixed(1) + '万' : kb.total_chars) : '-'}</td>
        <td style="font-size:12px;">${extStr}</td>
        <td>${kb.query_count_7d}</td>
        <td><span style="display:inline-block;padding:2px 10px;border-radius:12px;font-weight:600;font-size:13px;color:${scoreColor};background:${scoreBg};">${kb.health_score}</span></td>
      </tr>`;
    }).join('');
  }

  function renderCharts(kbs) {
    if (!kbs || !kbs.length || typeof echarts === 'undefined') return;

    // 文档数量分布柱状图
    const docChart = echarts.init(document.getElementById('health-doc-chart'));
    docChart.setOption({
      tooltip: { trigger: 'axis' },
      xAxis: { type: 'category', data: kbs.map(k => k.name), axisLabel: { rotate: 20, fontSize: 11 } },
      yAxis: { type: 'value' },
      series: [
        { name: '文档数', type: 'bar', data: kbs.map(k => k.doc_count), itemStyle: { color: '#1890ff' }, barMaxWidth: 40 },
        { name: '分块数', type: 'bar', data: kbs.map(k => k.chunk_count), itemStyle: { color: '#52c41a' }, barMaxWidth: 40 },
      ],
    });

    // 健康度评分雷达图
    const scoreChart = echarts.init(document.getElementById('health-score-chart'));
    scoreChart.setOption({
      tooltip: {},
      radar: {
        indicator: kbs.map(k => ({ name: k.name.substring(0, 6), max: 100 })),
        radius: '65%',
      },
      series: [{
        type: 'radar',
        data: [{
          value: kbs.map(k => k.health_score),
          name: '健康度',
          areaStyle: { opacity: 0.15 },
          lineStyle: { color: '#1890ff' },
          itemStyle: { color: '#1890ff' },
        }],
      }],
    });

    // 响应式
    window.addEventListener('resize', () => { docChart.resize(); scoreChart.resize(); });
  }

  return { load };
})();

Router.on('kb-health', () => PageKBHealth.load());
