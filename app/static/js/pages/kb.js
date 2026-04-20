/**
 * 知识库列表 & 详情页
 */
const PageKB = (() => {
  let kbList = [];
  let currentKbId = null;
  let kbPage = 1, docPage = 1;

  async function loadKBList(page) {
    kbPage = page || 1;
    try {
      const data = await API.request(`/api/knowledge-bases?page=${kbPage}&page_size=10`);
      kbList = data.items || [];
      const tbody = document.getElementById('kb-table-body');
      document.getElementById('kb-total').textContent = data.total || 0;
      if (!kbList.length) {
        tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:40px;color:#999;">暂无知识库，点击右上角创建</td></tr>';
      } else {
        const role = API.getUser().role;
        const canManage = role === 'super_admin' || role === 'kb_admin';
        tbody.innerHTML = kbList.map(k => {
          let actions = `<button class="btn btn-sm" onclick="PageKB.openDetail('${k.id}','${k.name}')">${canManage ? '管理' : '查看'}</button>`;
          if (canManage) actions += ` <button class="btn btn-sm btn-danger" onclick="PageKB.deleteKB('${k.id}')">删除</button>`;
          return `<tr>
            <td><strong>📖 ${k.name}</strong><br><span class="text-muted">${k.description || ''}</span></td>
            <td>${k.doc_count || 0}</td><td>${k.chunk_count || 0}</td>
            <td><span class="tag tag-blue">${k.embedding_model}</span></td>
            <td><span class="tag tag-green">${k.status}</span></td>
            <td>${actions}</td>
          </tr>`;
        }).join('');
      }
      UI.renderPagination('kb-pagination', data.total, kbPage, 10, 'PageKB.loadKBList');
    } catch (e) { console.error(e); }
  }

  function openDetail(kbId, kbName) {
    currentKbId = kbId;
    const user = API.getUser();
    document.getElementById('kb-detail-name').textContent = kbName;
    const canEdit = user.role === 'super_admin' || user.role === 'kb_admin';
    document.querySelectorAll('.kb-edit-only').forEach(el => el.style.display = canEdit ? '' : 'none');
    document.querySelectorAll('.kb-admin-only').forEach(el => el.style.display = user.role === 'super_admin' ? '' : 'none');
    // 重置 tab
    const tabs = document.querySelectorAll('#kb-detail-tabs .tab');
    tabs.forEach((t, i) => t.classList.toggle('active', i === 0));
    document.getElementById('kb-tab-docs').style.display = 'block';
    document.getElementById('kb-tab-settings').style.display = 'none';
    Router.navigate('kb-detail');
    loadKBDocs();
  }

  async function loadKBDocs(page) {
    docPage = page || 1;
    if (!currentKbId) return;
    try {
      const data = await API.request(`/api/documents?kb_id=${currentKbId}&page=${docPage}&page_size=20`);
      const docs = data.items || [];
      const tbody = document.getElementById('doc-table-body');
      if (!docs.length) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;padding:40px;color:#999;">暂无文档，请上传</td></tr>';
      } else {
        const role = API.getUser().role;
        const canEdit = role === 'super_admin' || role === 'kb_admin';
        tbody.innerHTML = docs.map(d => {
          let actions = `<button class="btn btn-sm" onclick="PageChunks.view('${d.filename}')">查看分块</button>`;
          if (canEdit) actions += ` <button class="btn btn-sm btn-danger" onclick="PageKB.deleteDoc('${d.filename}')">删除</button>`;
          return `<tr><td>📎 ${d.filename}</td><td>${d.size || '-'}</td><td>${d.chunks}</td>
            <td><span class="tag tag-green">已索引</span></td>
            <td class="flex gap-8">${actions}</td></tr>`;
        }).join('');
      }
      document.getElementById('kb-stat-docs').textContent = data.total || docs.length;
      UI.renderPagination('doc-pagination', data.total || 0, docPage, 20, 'PageKB.loadKBDocs');
      document.getElementById('kb-stat-chunks').textContent = docs.reduce((a, d) => a + (d.chunks || 0), 0);
    } catch (e) { console.error(e); }
    try {
      const acc = await API.request(`/api/kb-access?kb_id=${currentKbId}`);
      document.getElementById('kb-stat-depts').textContent = acc.length;
    } catch {}
    const kb = kbList.find(k => k.id === currentKbId);
    if (kb) document.getElementById('kb-stat-created').textContent = (kb.created_at || '').substring(0, 10);
  }

  async function loadKBSettings() {
    if (!currentKbId) return;
    const kb = kbList.find(k => k.id === currentKbId);
    if (!kb) return;
    document.getElementById('kb-set-name').value = kb.name || '';
    document.getElementById('kb-set-desc').value = kb.description || '';
    document.getElementById('kb-set-status').value = kb.status || 'active';
    document.getElementById('kb-set-emb-model').value = kb.embedding_model || '';
    document.getElementById('kb-set-llm-model').value = kb.llm_model || '';
    // 加载部门授权
    loadDeptAccess();
  }

  async function saveKBSettings() {
    if (!currentKbId) return;
    try {
      await API.request(`/api/knowledge-bases/${currentKbId}`, {
        method: 'PUT',
        body: {
          name: document.getElementById('kb-set-name').value.trim(),
          description: document.getElementById('kb-set-desc').value.trim(),
          status: document.getElementById('kb-set-status').value,
          embedding_model: document.getElementById('kb-set-emb-model').value.trim(),
          llm_model: document.getElementById('kb-set-llm-model').value.trim(),
        },
      });
      const d = await API.request('/api/knowledge-bases?page=1&page_size=100');
      kbList = d.items || [];
      document.getElementById('kb-detail-name').textContent = document.getElementById('kb-set-name').value.trim();
      alert('保存成功');
    } catch (e) { alert('保存失败: ' + e.message); }
  }

  async function createKB() {
    const name = document.getElementById('new-kb-name').value.trim();
    if (!name) { alert('请输入知识库名称'); return; }
    try {
      await API.request('/api/knowledge-bases', {
        method: 'POST',
        body: {
          name,
          description: document.getElementById('new-kb-desc').value.trim(),
        },
      });
      UI.hideModal();
      loadKBList();
    } catch { alert('创建失败'); }
  }

  async function deleteKB(kbId) {
    if (!confirm('确认删除该知识库？')) return;
    try {
      await API.request(`/api/knowledge-bases/${kbId}`, { method: 'DELETE' });
      loadKBList(kbPage);
    } catch { alert('删除失败'); }
  }

  async function deleteDoc(filename) {
    if (!confirm(`确认删除 "${filename}"？`)) return;
    try {
      await API.request(`/api/documents/${encodeURIComponent(filename)}?kb_id=${currentKbId}`, { method: 'DELETE' });
      loadKBDocs();
    } catch (e) { console.error(e); }
  }

  // ─── 部门授权管理 ──────────────────────────────

  async function loadDeptAccess() {
    if (!currentKbId) return;
    try {
      const [access, depts] = await Promise.all([
        API.request(`/api/kb-access?kb_id=${currentKbId}`),
        UI.loadDepts(),
      ]);
      const tbody = document.getElementById('kb-dept-access-body');
      if (!access.length) {
        tbody.innerHTML = '<tr><td colspan="3" style="text-align:center;padding:20px;color:#999;">暂无授权部门</td></tr>';
        return;
      }
      const deptMap = Object.fromEntries(UI.getDeptList().map(d => [d.id, d.name]));
      tbody.innerHTML = access.map(a => {
        const roleTag = a.role === 'admin' ? 'tag-purple' : a.role === 'editor' ? 'tag-blue' : 'tag-green';
        return `<tr>
          <td>🏢 ${deptMap[a.department_id] || a.department_id}</td>
          <td><span class="tag ${roleTag}">${a.role}</span></td>
          <td><button class="btn btn-sm btn-danger" onclick="PageKB.removeDeptAccess('${a.department_id}')">移除</button></td>
        </tr>`;
      }).join('');
    } catch (e) { console.error(e); }
  }

  async function showAddDeptAccess() {
    const [depts, existing] = await Promise.all([
      UI.loadDepts(),
      API.request(`/api/kb-access?kb_id=${currentKbId}`),
    ]);
    const existingIds = new Set(existing.map(a => a.department_id));
    const available = depts.filter(d => !existingIds.has(d.id));
    const sel = document.getElementById('dept-access-dept');
    sel.innerHTML = available.map(d => `<option value="${d.id}">${d.name}</option>`).join('');
    if (!available.length) { alert('所有部门都已授权'); return; }
    UI.showModal('add-dept-access');
  }

  async function addDeptAccess() {
    const deptId = document.getElementById('dept-access-dept').value;
    const role = document.getElementById('dept-access-role').value;
    if (!deptId) return;
    try {
      await API.request('/api/kb-access', {
        method: 'POST',
        body: { kb_id: currentKbId, department_id: deptId, role },
      });
      UI.hideModal();
      loadDeptAccess();
    } catch (e) { alert('添加失败: ' + e.message); }
  }

  async function removeDeptAccess(deptId) {
    if (!confirm('确认移除该部门授权？')) return;
    try {
      await API.request(`/api/kb-access?kb_id=${currentKbId}&department_id=${deptId}`, { method: 'DELETE' });
      loadDeptAccess();
    } catch (e) { alert('移除失败'); }
  }

  return {
    loadKBList, openDetail, loadKBDocs, loadKBSettings, saveKBSettings,
    createKB, deleteKB, deleteDoc,
    loadDeptAccess, showAddDeptAccess, addDeptAccess, removeDeptAccess,
    getCurrentKbId: () => currentKbId,
    getKbList: () => kbList,
  };
})();

Router.on('kb-list', () => PageKB.loadKBList());
Router.on('kb-detail', () => PageKB.loadKBDocs());
