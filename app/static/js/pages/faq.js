/**
 * FAQ 管理页 — 审核/统计/生命周期管理
 */
const PageFAQ = (() => {
  let faqs = [];
  let currentStatus = '';
  let currentPage = 1;
  let total = 0;

  function init() {
    Router.on('faq-mgmt', load);
  }

  async function load() {
    await loadStats();
    await loadFaqs();
  }

  async function loadStats() {
    try {
      const stats = await API.request('/api/faq/stats');
      document.getElementById('faq-total').textContent = stats.total || 0;
      document.getElementById('faq-approved').textContent = (stats.by_status || {}).approved || 0;
      document.getElementById('faq-pending').textContent = stats.pending_review || 0;
      document.getElementById('faq-hits').textContent = stats.total_hits || 0;

    } catch (e) {
      console.error('Load FAQ stats error:', e);
    }
  }

  async function loadFaqs() {
    try {
      const params = { page: currentPage, page_size: 20 };
      if (currentStatus) params.status = currentStatus;
      const qs = new URLSearchParams(params).toString();
      const data = await API.request(`/api/faq?${qs}`);
      faqs = data.items || [];
      total = data.total || 0;
      renderTable();
      renderPagination();
    } catch (e) {
      console.error('Load FAQ error:', e);
      document.getElementById('faq-table-body').innerHTML =
        `<tr><td colspan="5" class="empty">加载失败: ${e.message}</td></tr>`;
    }
  }

  function renderTable() {
    const tbody = document.getElementById('faq-table-body');
    if (!faqs.length) {
      tbody.innerHTML = '<tr><td colspan="5" class="empty">暂无 FAQ 记录</td></tr>';
      return;
    }
    const statusLabels = { auto: '待审核', approved: '已通过', rejected: '已拒绝', archived: '已归档' };
    const statusColors = { auto: 'orange', approved: 'green', rejected: 'red', archived: 'gray' };

    tbody.innerHTML = faqs.map(f => {
      let actions = '';
      if (f.status === 'auto') {
        actions = `<button class="btn btn-sm btn-primary" onclick="PageFAQ.approve('${f.id}')">通过</button> <button class="btn btn-sm" onclick="PageFAQ.reject('${f.id}')">拒绝</button>`;
      } else {
        actions = `<button class="btn btn-sm" onclick="PageFAQ.viewDetail('${f.id}')">详情</button>`;
      }
      actions += ` <a style="color:#ff4d4f;cursor:pointer;font-size:12px;margin-left:4px" onclick="PageFAQ.remove('${f.id}')">删除</a>`;
      return `<tr>
        <td title="${esc(f.question)}">${esc(f.question.length > 35 ? f.question.slice(0, 35) + '...' : f.question)}</td>
        <td>${esc(f.answer.length > 40 ? f.answer.slice(0, 40) + '...' : f.answer)}</td>
        <td><span class="tag tag-${statusColors[f.status] || 'gray'}">${statusLabels[f.status] || f.status}</span></td>
        <td style="text-align:center">${f.hit_count}</td>
        <td style="white-space:nowrap">${actions}</td>
      </tr>`;
    }).join('');
  }

  function renderPagination() {
    const el = document.getElementById('faq-pagination');
    const totalPages = Math.ceil(total / 20);
    if (totalPages <= 1) { el.innerHTML = ''; return; }
    let html = '';
    if (currentPage > 1) html += `<button class="btn btn-sm" onclick="PageFAQ.goPage(${currentPage - 1})">上一页</button>`;
    html += ` <span>${currentPage} / ${totalPages}</span> `;
    if (currentPage < totalPages) html += `<button class="btn btn-sm" onclick="PageFAQ.goPage(${currentPage + 1})">下一页</button>`;
    el.innerHTML = html;
  }

  function filterByStatus(status) {
    currentStatus = status;
    currentPage = 1;
    // 更新按钮高亮
    document.querySelectorAll('.faq-filter-btn').forEach(b => b.classList.remove('active'));
    event.target.classList.add('active');
    loadFaqs();
  }

  function goPage(page) {
    currentPage = page;
    loadFaqs();
  }

  async function approve(id) {
    try {
      await API.request(`/api/faq/${id}/approve`, { method: 'POST' });
      await load();
    } catch (e) {
      alert('操作失败: ' + e.message);
    }
  }

  async function reject(id) {
    if (!confirm('确定拒绝这条 FAQ？')) return;
    try {
      await API.request(`/api/faq/${id}/reject`, { method: 'POST' });
      await load();
    } catch (e) {
      alert('操作失败: ' + e.message);
    }
  }

  async function remove(id) {
    if (!confirm('确定删除这条 FAQ？')) return;
    try {
      await API.request(`/api/faq/${id}`, { method: 'DELETE' });
      await load();
    } catch (e) {
      alert('删除失败: ' + e.message);
    }
  }

  function viewDetail(id) {
    const faq = faqs.find(f => f.id === id);
    if (!faq) return;
    const modal = document.createElement('div');
    modal.className = 'modal-overlay';
    modal.innerHTML = `
      <div class="modal" style="max-width:700px">
        <div class="modal-header">
          <h3>FAQ 详情</h3>
          <span class="modal-close" onclick="this.closest('.modal-overlay').remove()">✕</span>
        </div>
        <div class="modal-body">
          <p><strong>问题：</strong>${esc(faq.question)}</p>
          <p><strong>回答：</strong></p>
          <div style="background:#f5f5f5;padding:12px;border-radius:6px;white-space:pre-wrap;max-height:300px;overflow-y:auto">${esc(faq.full_answer || faq.answer)}</div>
          <p><strong>命中次数：</strong>${faq.hit_count} &nbsp; <strong>状态：</strong>${faq.status} &nbsp; <strong>置信度：</strong>${faq.confidence ? (faq.confidence * 100).toFixed(0) + '%' : '-'}</p>
          ${faq.tags && faq.tags.length ? `<p><strong>标签：</strong>${faq.tags.map(t => `<span class="tag">${esc(t)}</span>`).join(' ')}</p>` : ''}
        </div>
      </div>
    `;
    document.body.appendChild(modal);
    modal.querySelector('.modal-close').addEventListener('click', () => modal.remove());
  }

  function esc(s) {
    const d = document.createElement('div');
    d.textContent = s || '';
    return d.innerHTML;
  }

  return { init, load, loadFaqs, filterByStatus, goPage, approve, reject, remove, viewDetail };
})();
