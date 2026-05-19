/**
 * 知识图谱可视化页 — D3 力导向图
 */
const PageKG = (() => {
  let graphData = { nodes: [], edges: [] };
  let simulation = null;
  let svg = null;
  let currentKbId = null;
  let selectedNode = null;

  // D3 选择器
  let linkGroup, nodeGroup, labelGroup;
  let zoom;

  function init() {
    Router.on('kg-graph', load);
  }

  async function load(params) {
    console.log('[KG] load called, params:', params);
    currentKbId = params.kb_id || window.__currentKbId || '';
    if (!currentKbId) { try { currentKbId = localStorage.getItem('__currentKbId') || ''; } catch(e){} }
    console.log('[KG] currentKbId:', currentKbId);
    // 清空旧图谱
    graphData = { nodes: [], edges: [] };
    if (simulation) { simulation.stop(); simulation = null; }
    const container = document.getElementById('kg-graph-container');
    if (container) container.innerHTML = '<div class="empty" style="padding:40px;text-align:center">加载中...</div>';
    renderStats({ entity_count: 0, relation_count: 0, displayed_nodes: 0, displayed_edges: 0 });
    if (!currentKbId) {
      if (container) container.innerHTML = '<div class="empty" style="padding:40px;text-align:center">请从知识库详情页进入图谱视图</div>';
      return;
    }
    await loadGraph();
  }

  async function loadGraph() {
    try {
      console.log('[KG] loadGraph kb_id:', currentKbId);
      const data = await API.request(`/api/kg/${currentKbId}/graph?limit=150`);
      console.log('[KG] graph data:', data);
      graphData = data;
      renderStats(data.stats);
      // 延迟渲染，确保容器宽度正确
      setTimeout(() => renderGraph(data.nodes, data.edges), 100);
    } catch (e) {
      console.error('Load KG error:', e);
      document.getElementById('kg-graph-container').innerHTML =
        `<div class="empty" style="padding:40px;text-align:center">加载失败: ${e.message}</div>`;
    }
  }

  function renderStats(stats) {
    document.getElementById('kg-entity-count').textContent = stats.entity_count || 0;
    document.getElementById('kg-relation-count').textContent = stats.relation_count || 0;
    document.getElementById('kg-displayed').textContent =
      `${stats.displayed_nodes || 0} 节点 / ${stats.displayed_edges || 0} 边`;
  }

  function renderGraph(nodes, edges, containerId) {
    const container = document.getElementById(containerId || 'kg-graph-container');
    container.innerHTML = '';

    if (!nodes.length) {
      container.innerHTML = '<div class="empty" style="padding:40px;text-align:center">暂无图谱数据，请先上传文档</div>';
      return;
    }

    const rect = container.getBoundingClientRect();
    const width = Math.max(rect.width || 800, 600);
    const height = Math.max(rect.height || 500, 400);

    // 创建 SVG
    svg = d3.select(container)
      .append('svg')
      .attr('viewBox', `0 0 ${width} ${height}`)
      .attr('preserveAspectRatio', 'xMidYMid meet')
      .style('width', '100%')
      .style('height', '100%')
      .style('background', '#fafbfc');

    // 缩放
    zoom = d3.zoom()
      .scaleExtent([0.2, 4])
      .on('zoom', (event) => {
        svg.select('g.graph-root').attr('transform', event.transform);
      });
    svg.call(zoom);

    // 根 group
    const root = svg.append('g').attr('class', 'graph-root');

    // 箭头 marker
    svg.append('defs').append('marker')
      .attr('id', 'arrowhead')
      .attr('viewBox', '0 -5 10 10')
      .attr('refX', 25)
      .attr('refY', 0)
      .attr('markerWidth', 8)
      .attr('markerHeight', 8)
      .attr('orient', 'auto')
      .append('path')
      .attr('d', 'M0,-5L10,0L0,5')
      .attr('fill', '#999');

    // 边
    linkGroup = root.append('g').attr('class', 'links');
    const links = linkGroup.selectAll('line')
      .data(edges)
      .enter().append('line')
      .attr('stroke', '#ccc')
      .attr('stroke-width', 1.5)
      .attr('marker-end', 'url(#arrowhead)');

    // 边标签
    const edgeLabelGroup = root.append('g').attr('class', 'edge-labels');
    const edgeLabels = edgeLabelGroup.selectAll('text')
      .data(edges)
      .enter().append('text')
      .attr('font-size', 10)
      .attr('fill', '#888')
      .attr('text-anchor', 'middle')
      .attr('dy', -4)
      .text(d => d.label);

    // 节点
    nodeGroup = root.append('g').attr('class', 'nodes');
    const nodeRadius = d => Math.max(12, Math.min(30, 8 + d.frequency * 2));
    const nodes_g = nodeGroup.selectAll('circle')
      .data(nodes)
      .enter().append('circle')
      .attr('r', d => nodeRadius(d))
      .attr('fill', d => d.color || '#95A5A6')
      .attr('stroke', '#fff')
      .attr('stroke-width', 2)
      .style('cursor', 'pointer')
      .on('click', (event, d) => showNodeDetail(d))
      .call(d3.drag()
        .on('start', dragStart)
        .on('drag', dragging)
        .on('end', dragEnd));

    // 节点标签
    labelGroup = root.append('g').attr('class', 'labels');
    const labels = labelGroup.selectAll('text')
      .data(nodes)
      .enter().append('text')
      .attr('font-size', 11)
      .attr('fill', '#333')
      .attr('text-anchor', 'middle')
      .attr('dy', d => nodeRadius(d) + 14)
      .attr('pointer-events', 'none')
      .text(d => d.name.length > 8 ? d.name.slice(0, 8) + '…' : d.name);

    // 力模拟
    simulation = d3.forceSimulation(nodes)
      .force('link', d3.forceLink(edges).id(d => d.id).distance(120))
      .force('charge', d3.forceManyBody().strength(-300))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide().radius(d => nodeRadius(d) + 5))
      .on('tick', () => {
        links
          .attr('x1', d => d.source.x)
          .attr('y1', d => d.source.y)
          .attr('x2', d => d.target.x)
          .attr('y2', d => d.target.y);

        edgeLabels
          .attr('x', d => (d.source.x + d.target.x) / 2)
          .attr('y', d => (d.source.y + d.target.y) / 2);

        nodes_g
          .attr('cx', d => d.x)
          .attr('cy', d => d.y);

        labels
          .attr('x', d => d.x)
          .attr('y', d => d.y);
      });

    // 初始缩放到合适大小
    setTimeout(() => {
      svg.call(zoom.transform, d3.zoomIdentity.translate(0, 0).scale(0.9));
    }, 500);
  }

  function dragStart(event, d) {
    if (!event.active) simulation.alphaTarget(0.3).restart();
    d.fx = d.x;
    d.fy = d.y;
  }
  function dragging(event, d) {
    d.fx = event.x;
    d.fy = event.y;
  }
  function dragEnd(event, d) {
    if (!event.active) simulation.alphaTarget(0);
    d.fx = null;
    d.fy = null;
  }

  function showNodeDetail(node) {
    selectedNode = node;
    const detail = document.getElementById('kg-node-detail');
    if (!detail) return;

    // 找关联边
    const related = graphData.edges.filter(
      e => e.source.id === node.id || e.target.id === node.id
    );

    let relationsHtml = '';
    if (related.length) {
      relationsHtml = '<div style="margin-top:8px"><b>关联关系：</b><ul style="margin:4px 0;padding-left:16px">';
      related.forEach(e => {
        const isSubject = e.source.id === node.id;
        const other = isSubject ? e.target : e.source;
        const arrow = isSubject ? '→' : '←';
        relationsHtml += `<li style="font-size:12px;margin:2px 0">${arrow} ${e.label} ${arrow} <b>${other.name}</b></li>`;
      });
      relationsHtml += '</ul></div>';
    }

    detail.innerHTML = `
      <div style="border-left:3px solid ${node.color};padding:8px 12px;margin-bottom:8px">
        <div style="font-size:15px;font-weight:bold">${esc(node.name)}</div>
        <div style="font-size:12px;color:#888;margin-top:2px">
          <span class="tag" style="background:${node.color};color:#fff;padding:1px 6px;border-radius:3px;font-size:11px">${node.type_label}</span>
          &nbsp; 出现 ${node.frequency} 次
        </div>
        ${node.description ? `<div style="font-size:13px;margin-top:6px;color:#555">${esc(node.description)}</div>` : ''}
      </div>
      ${relationsHtml}
    `;
  }

  // 搜索实体
  async function searchEntity() {
    const input = document.getElementById('kg-search-input');
    const keyword = input.value.trim();
    if (!keyword || !currentKbId) return;

    try {
      const data = await API.request(
        `/api/kg/${currentKbId}/search?entity=${encodeURIComponent(keyword)}&hops=1`
      );
      if (!data.nodes.length) {
        alert('未找到该实体');
        return;
      }
      renderStats({
        entity_count: graphData.stats?.entity_count || 0,
        relation_count: graphData.stats?.relation_count || 0,
        displayed_nodes: data.nodes.length,
        displayed_edges: data.edges.length,
      });
      renderGraph(data.nodes, data.edges);

      // 高亮匹配节点
      if (data.matched_entities?.length) {
        nodeGroup.selectAll('circle')
          .attr('stroke', d => data.matched_entities.includes(d.name) ? '#ff4d4f' : '#fff')
          .attr('stroke-width', d => data.matched_entities.includes(d.name) ? 3 : 2);
      }
    } catch (e) {
      alert('搜索失败: ' + e.message);
    }
  }

  // 重置视图
  function resetView() {
    if (graphData.nodes.length) {
      renderGraph(graphData.nodes, graphData.edges);
    }
  }

  // 导出图片
  function exportImage() {
    if (!svg) return;
    const svgEl = svg.node();
    const serializer = new XMLSerializer();
    const svgStr = serializer.serializeToString(svgEl);
    const blob = new Blob([svgStr], { type: 'image/svg+xml' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'knowledge-graph.svg';
    a.click();
    URL.revokeObjectURL(url);
  }

  function esc(s) {
    const d = document.createElement('div');
    d.textContent = s || '';
    return d.innerHTML;
  }

  // 构建图谱
  async function buildGraph() {
    // 兜底：尝试从全局变量获取
    if (!currentKbId) currentKbId = window.__currentKbId || '';
    console.log('[KG] buildGraph kb_id:', currentKbId);
    if (!currentKbId) return alert('请先选择知识库');
    
    const btn = document.getElementById('kg-build-btn');
    const status = document.getElementById('kg-build-status');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ 构建中...'; }
    if (status) { status.style.display = 'block'; status.textContent = '图谱构建已启动，正在从文档中抽取实体和关系，请稍候...'; }

    try {
      const data = await API.request(`/api/kg/${currentKbId}/build`, { method: 'POST' });
      status.textContent = data.message || '构建已启动';
      // 轮询等待完成
      let attempts = 0;
      const maxAttempts = 120; // 最多等 10 分钟
      const poll = setInterval(async () => {
        attempts++;
        if (attempts > maxAttempts) {
          clearInterval(poll);
          if (btn) { btn.disabled = false; btn.textContent = '🔨 构建图谱'; }
          if (status) status.textContent = '⏰ 构建超时，请刷新页面查看结果';
          return;
        }
        // 显示进度
        if (status) status.textContent = '⏳ 构建中... (' + Math.floor(attempts * 5 / 60) + '分' + (attempts * 5 % 60) + '秒)';
        try {
          const stats = await API.request(`/api/kg/${currentKbId}/stats`);
          if (stats.entity_count > 0) {
            clearInterval(poll);
            if (btn) { btn.disabled = false; btn.textContent = '⚙️ 构建图谱'; }
            if (status) { status.textContent = '✅ 构建完成！共 ' + stats.entity_count + ' 个实体，' + stats.relation_count + ' 条关系'; setTimeout(() => { status.style.display = 'none'; }, 3000); }
            // 重新加载图谱到当前容器
            loadInTab();
          }
        } catch (e) { /* keep polling */ }
      }, 5000);
    } catch (e) {
      if (btn) { btn.disabled = false; btn.textContent = '⚙️ 构建图谱'; }
      if (status) status.style.display = 'none';
      alert('构建失败: ' + e.message);
    }
  }

  // 从 KB 详情页跳转
  function openFromKB(kbId) {
    if (!kbId) {
      kbId = window.__currentKbId || '';
      try { kbId = kbId || localStorage.getItem('__currentKbId') || ''; } catch(e){}
    }
    if (!kbId) { alert('无法获取知识库ID，请从知识库列表重新进入'); return; }
    currentKbId = kbId;
    // 直接切换显示，不依赖 hash 路由
    document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
    document.getElementById('kg-graph').classList.add('active');
    // 加载数据
    loadGraph();
  }

  // 窗口/侧边栏变化时重绘
  function handleResize() {
    if (graphData.nodes.length && currentKbId) {
      clearTimeout(handleResize._timer);
      handleResize._timer = setTimeout(() => renderGraph(graphData.nodes, graphData.edges), 300);
    }
  }
  window.addEventListener('resize', handleResize);
  // 监听侧边栏变化
  const sidebar = document.getElementById('sidebar');
  if (sidebar) {
    new MutationObserver(handleResize).observe(sidebar, { attributes: true, attributeFilter: ['class'] });
  }

  function loadInTab() {
    // 重置节点详情
    var detail = document.getElementById('kg-node-detail');
    if (detail) detail.innerHTML = '';
    
    var kbId = window.__currentKbId || localStorage.getItem('__currentKbId') || '';
    if (!kbId) return;
    currentKbId = kbId;
    // 加载图谱到tab容器
    var container = document.getElementById('kg-tab-container');
    if (container) {
      loadGraphToContainer(container, kbId);
    }
    // 加载统计
    loadStatsToTab(kbId);
  }

  async function loadGraphToContainer(container, kbId) {
    try {
      var data = await API.request('/api/kg/' + kbId + '/graph?limit=150');
      if (!data.nodes || !data.nodes.length) {
        container.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#999;">暂无图谱数据，请先构建图谱</div>';
        return;
      }
      // 使用renderGraph，传入容器ID
      renderGraph(data.nodes, data.edges, 'kg-tab-container');
    } catch (e) {
      container.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#999;">加载失败: ' + e.message + '</div>';
    }
  }



  async function loadStatsToTab(kbId) {
    try {
      var stats = await API.request('/api/kg/' + kbId + '/stats');
      document.getElementById('kg-tab-entities').textContent = stats.entity_count || 0;
      document.getElementById('kg-tab-relations').textContent = stats.relation_count || 0;
    } catch (e) {}
  }

  async function searchInTab() {
    var keyword = document.getElementById('kg-tab-search').value.trim();
    if (!keyword || !currentKbId) return;
    
    try {
      var data = await API.request(
        '/api/kg/' + currentKbId + '/search?entity=' + encodeURIComponent(keyword) + '&hops=1'
      );
      if (!data.nodes || !data.nodes.length) {
        alert('未找到该实体');
        return;
      }
      // 更新统计
      document.getElementById('kg-tab-entities').textContent = data.nodes.length;
      document.getElementById('kg-tab-relations').textContent = data.edges.length;
      // 渲染到tab容器
      renderGraph(data.nodes, data.edges, 'kg-tab-container');
    } catch (e) {
      alert('搜索失败: ' + e.message);
    }
  }

  function exportGraph() {
    if (!currentKbId) return alert('请先选择知识库');
    window.open('/api/kg/' + currentKbId + '/export', '_blank');
  }

  return { init, load, searchEntity, resetView, exportImage, buildGraph, openFromKB, handleResize, loadInTab, searchInTab, exportGraph };
})();
