/**
 * 用户记忆管理页
 */
const PageMemory = (() => {
  let memories = [];

  function init() {
    Router.on('user-memory', load);
  }

  async function load() {
    try {
      const data = await API.request('/api/memory');
      memories = data.memories || [];
      renderStats(data.stats || {});
      renderTable();
    } catch (e) {
      console.error('Load memory error:', e);
      document.getElementById('memory-table-body').innerHTML =
        `<tr><td colspan="5" class="empty">加载失败: ${e.message}</td></tr>`;
    }
  }

  function renderStats(stats) {
    document.getElementById('memory-total').textContent = stats.total || 0;
    const byType = stats.by_type || {};
    document.getElementById('memory-pref').textContent = byType.preference || 0;
    document.getElementById('memory-context').textContent = byType.context || 0;
    document.getElementById('memory-corr').textContent = byType.correction || 0;
  }

  function renderTable() {
    const tbody = document.getElementById('memory-table-body');
    if (!memories.length) {
      tbody.innerHTML = '<tr><td colspan="4" class="empty">暂无记忆记录</td></tr>';
      return;
    }
    const typeLabels = { preference: '偏好', context: '背景', correction: '纠正' };
    const typeColors = { preference: 'blue', context: 'green', correction: 'orange' };

    tbody.innerHTML = memories.map(m => `
      <tr>
        <td><span class="tag tag-${typeColors[m.memory_type] || 'gray'}">${typeLabels[m.memory_type] || m.memory_type}</span></td>
        <td>${esc(m.content)}</td>
        <td style="text-align:center">${m.hit_count}</td>
        <td><a style="color:#ff4d4f;cursor:pointer;font-size:12px" onclick="PageMemory.remove('${m.id}')">删除</a></td>
      </tr>
    `).join('');
  }

  async function remove(id) {
    if (!confirm('确定删除这条记忆？')) return;
    try {
      await API.request(`/api/memory/${id}`, { method: 'DELETE' });
      memories = memories.filter(m => m.id !== id);
      renderTable();
    } catch (e) {
      alert('删除失败: ' + e.message);
    }
  }

  function esc(s) {
    const d = document.createElement('div');
    d.textContent = s || '';
    return d.innerHTML;
  }

  return { init, load, remove };
})();
