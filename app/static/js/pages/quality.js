/**
 * 质量监控页 — 用户反馈列表
 */
const PageQuality = (() => {
  let feedbackPage = 1;

  async function load(page) {
    feedbackPage = page || 1;
    const rating = document.getElementById('feedback-filter')?.value || '';
    let url = `/api/feedback?page=${feedbackPage}&page_size=20`;
    if (rating) url += `&rating=${rating}`;

    try {
      const data = await API.request(url);
      const items = data.items || [];
      const tbody = document.getElementById('feedback-body');
      document.getElementById('feedback-count').textContent = `共 ${data.total} 条反馈`;
      UI.renderPagination('feedback-pagination', data.total, feedbackPage, 20, 'PageQuality.load');

      if (!items.length) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;padding:40px;color:#999;">暂无反馈</td></tr>';
        return;
      }

      tbody.innerHTML = items.map(f => {
        const time = f.created_at ? f.created_at.replace('T', ' ').substring(0, 16) : '';
        const icon = f.rating === 'up' ? '👍' : '👎';
        const tag = f.rating === 'up'
          ? '<span class="tag tag-green">点赞</span>'
          : '<span class="tag tag-red">点踩</span>';
        return `<tr>
          <td>${time}</td>
          <td>${f.user_id || '-'}</td>
          <td style="max-width:250px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${f.question || ''}">${f.question || '-'}</td>
          <td style="max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${f.answer || ''}">${f.answer || '-'}</td>
          <td>${icon} ${tag}</td>
        </tr>`;
      }).join('');
    } catch (e) {
      console.error('加载反馈失败:', e);
    }
  }

  return { load };
})();

Router.on('quality', () => PageQuality.load());
