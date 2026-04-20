/**
 * 分块查看/编辑页
 */
const PageChunks = (() => {
  let chunks = [];
  let currentChunkId = null;

  async function view(filename) {
    const kbId = PageKB.getCurrentKbId();
    document.getElementById('chunk-viewer-filename').textContent = filename;
    Router.navigate('chunk-viewer');

    try {
      let url = `/api/documents/${encodeURIComponent(filename)}/chunks`;
      if (kbId) url += `?kb_id=${kbId}`;
      const data = await API.request(url);
      chunks = data.chunks || [];
      document.getElementById('chunk-viewer-count').textContent = chunks.length + ' 块';
      render();
    } catch (e) {
      document.getElementById('chunk-list').innerHTML =
        '<div class="text-muted" style="text-align:center;padding:40px;">加载失败: ' + e.message + '</div>';
    }
  }

  function render(filtered) {
    const list = filtered || chunks;
    const container = document.getElementById('chunk-list');
    if (!list.length) {
      container.innerHTML = '<div class="text-muted" style="text-align:center;padding:40px;">暂无分块</div>';
      return;
    }
    const role = API.getUser().role;
    const canEdit = role === 'super_admin' || role === 'kb_admin';
    container.innerHTML = list.map(c => {
      let actions = '';
      if (canEdit) {
        actions = `<button class="btn btn-sm" onclick="event.stopPropagation();PageChunks.edit('${c.id}',${c.index})">✏️ 编辑</button>
            <button class="btn btn-sm btn-danger" onclick="event.stopPropagation();PageChunks.remove('${c.id}')">🗑️</button>`;
      }
      return `<div class="chunk-item" style="border:1px solid #f0f0f0;border-radius:8px;margin-bottom:12px;overflow:hidden;">
        <div class="chunk-header" style="display:flex;justify-content:space-between;align-items:center;padding:10px 16px;background:#fafafa;cursor:pointer;" onclick="this.nextElementSibling.style.display=this.nextElementSibling.style.display==='none'?'block':'none'">
          <span style="font-weight:500;">#${c.index} <span class="text-muted">(${c.char_count} 字符)</span></span>
          ${actions ? '<div class="flex gap-8">' + actions + '</div>' : ''}
        </div>
        <div class="chunk-body" style="padding:12px 16px;font-size:13px;line-height:1.8;white-space:pre-wrap;max-height:200px;overflow-y:auto;">${escapeHtml(c.text)}</div>
      </div>`;
    }).join('');
  }

  function escapeHtml(text) {
    return text.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }

  function filter() {
    const keyword = (document.getElementById('chunk-search')?.value || '').trim().toLowerCase();
    if (!keyword) { render(); return; }
    render(chunks.filter(c => c.text.toLowerCase().includes(keyword)));
  }

  function sort() {
    const mode = document.getElementById('chunk-sort').value;
    if (mode === 'length-desc') chunks.sort((a, b) => b.char_count - a.char_count);
    else if (mode === 'length-asc') chunks.sort((a, b) => a.char_count - b.char_count);
    else chunks.sort((a, b) => a.index - b.index);
    render();
  }

  function expandAll() {
    document.querySelectorAll('.chunk-body').forEach(el => el.style.display = 'block');
  }

  function collapseAll() {
    document.querySelectorAll('.chunk-body').forEach(el => el.style.display = 'none');
  }

  function edit(chunkId, index) {
    currentChunkId = chunkId;
    const chunk = chunks.find(c => c.id === chunkId);
    if (!chunk) return;
    document.getElementById('chunk-edit-index').textContent = '#' + index;
    document.getElementById('chunk-edit-text').value = chunk.text;
    document.getElementById('chunk-edit-charcount').textContent = chunk.char_count;
    document.getElementById('modal-overlay').style.display = 'flex';
    document.getElementById('modal-chunk-edit').style.display = 'block';
  }

  function hideEdit() {
    document.getElementById('modal-overlay').style.display = 'none';
    document.getElementById('modal-chunk-edit').style.display = 'none';
    currentChunkId = null;
  }

  async function saveEdit() {
    const text = document.getElementById('chunk-edit-text').value.trim();
    if (!text || !currentChunkId) return;
    try {
      const data = await API.request(`/api/chunks/${currentChunkId}`, {
        method: 'PUT', body: { text },
      });
      const chunk = chunks.find(c => c.id === currentChunkId);
      if (chunk) { chunk.text = text; chunk.char_count = data.char_count; }
      hideEdit();
      render();
    } catch (e) { alert('保存失败: ' + e.message); }
  }

  async function remove(chunkId) {
    if (!confirm('确认删除此分块？')) return;
    try {
      await API.request(`/api/chunks/${chunkId}`, { method: 'DELETE' });
      chunks = chunks.filter(c => c.id !== chunkId);
      document.getElementById('chunk-viewer-count').textContent = chunks.length + ' 块';
      render();
    } catch (e) { alert('删除失败: ' + e.message); }
  }

  function charCount() {
    document.getElementById('chunk-edit-charcount').textContent =
      document.getElementById('chunk-edit-text').value.length;
  }

  return { view, filter, sort, expandAll, collapseAll, edit, hideEdit, saveEdit, remove, charCount };
})();
