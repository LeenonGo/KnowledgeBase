/**
 * 数据源管理页
 */
const PageDataSource = (() => {
  let sources = [];
  let currentKbId = '';

  function init() {
    Router.on('data-source', load);
  }

  async function load(params) {
    currentKbId = params.kb_id || window.__currentKbId || '';
    try { currentKbId = currentKbId || localStorage.getItem('__currentKbId') || ''; } catch(e){}
    if (!currentKbId) {
      document.getElementById('ds-table-body').innerHTML =
        '<tr><td colspan="6" class="empty">请从知识库详情页进入</td></tr>';
      return;
    }
    await loadSources();
  }

  async function loadSources() {
    try {
      sources = await API.request(`/api/data-sources?kb_id=${currentKbId}`);
      renderTable();
    } catch (e) {
      document.getElementById('ds-table-body').innerHTML =
        `<tr><td colspan="6" class="empty">加载失败: ${e.message}</td></tr>`;
    }
  }

  function renderTable() {
    const tbody = document.getElementById('ds-table-body');
    if (!sources.length) {
      tbody.innerHTML = '<tr><td colspan="6" class="empty">暂无数据源，点击"新增数据源"开始配置</td></tr>';
      return;
    }

    const statusMap = {
      idle: { label: '空闲', color: '#999' },
      syncing: { label: '同步中', color: '#1890ff' },
      success: { label: '成功', color: '#52c41a' },
      error: { label: '失败', color: '#ff4d4f' },
    };

    tbody.innerHTML = sources.map(s => {
      const st = statusMap[s.sync_status] || statusMap.idle;
      const syncTime = s.last_sync_at ? timeAgo(s.last_sync_at) : '从未同步';
      const result = s.last_sync_result || {};
      const resultText = s.last_sync_at
        ? `+${result.added||0} ~${result.updated||0} -${result.deleted||0}`
        : '';

      const syncing = s.sync_status === 'syncing';
      const errText = result.error ? `<br><span style="font-size:12px;color:#ff4d4f">❌ ${esc(String(result.error).slice(0,80))}</span>` : '';
      const errCount = result.errors ? `<br><span style="font-size:12px;color:#faad14">⚠ ${result.errors}个文件失败</span>` : '';

      return `<tr>
        <td><b>${esc(s.name)}</b></td>
        <td>${s.source_type_icon} ${s.source_type_label}</td>
        <td><span style="color:${st.color}">${syncing ? '⟳ ' : '● '}${st.label}</span></td>
        <td>${syncTime}<br><span style="font-size:12px;color:#888">${resultText}</span>${errText}${errCount}</td>
        <td>${s.sync_cron || '手动'}</td>
        <td>
          <a onclick="PageDataSource.syncNow('${s.id}')" style="color:${syncing ? '#ccc;pointer-events:none' : '#1890ff'};cursor:pointer;margin-right:8px">${syncing ? '同步中…' : '同步'}</a>
          <a onclick="PageDataSource.editSource('${s.id}')" style="cursor:pointer;margin-right:8px">编辑</a>
          <a onclick="PageDataSource.remove('${s.id}')" style="color:#ff4d4f;cursor:pointer">删除</a>
        </td>
      </tr>`;
    }).join('');
  }

  async function syncNow(id) {
    try {
      await API.request(`/api/data-sources/${id}/sync`, { method: 'POST' });
      // 先立即刷新一次，显示"同步中"状态
      await loadSources();
      // 轮询状态，每次刷新表格
      let attempts = 0;
      const poll = setInterval(async () => {
        attempts++;
        if (attempts > 60) { clearInterval(poll); loadSources(); return; }
        try {
          const s = await API.request(`/api/data-sources/${id}`);
          await loadSources();
          if (s.sync_status !== 'syncing') {
            clearInterval(poll);
          }
        } catch(e) { clearInterval(poll); }
      }, 2000);
    } catch (e) {
      alert('同步失败: ' + e.message);
    }
  }

  function showCreate() {
    const html = `
      <div class="form-group">
        <label>数据源名称</label>
        <input class="input" id="ds-new-name" placeholder="如：技术文档仓库">
      </div>
      <div class="form-group">
        <label>类型</label>
        <select class="select" id="ds-new-type" onchange="PageDataSource.toggleConfig()">
          <option value="git">🔀 Git 仓库</option>
          <option value="web_url">🌐 网页 URL</option>
        </select>
      </div>
      <div id="ds-config-git">
        <div class="form-group">
          <label>仓库地址</label>
          <input class="input" id="ds-git-url" placeholder="https://github.com/org/repo.git">
        </div>
        <div class="form-group">
          <label>分支</label>
          <input class="input" id="ds-git-branch" value="main" placeholder="main">
        </div>
        <div class="form-group">
          <label>文档目录（留空=整个仓库）</label>
          <input class="input" id="ds-git-path" placeholder="docs/">
        </div>
        <div class="form-group">
          <label>Token（私有仓库可选）</label>
          <input class="input" id="ds-git-token" placeholder="ghp_xxxx" type="password">
        </div>
      </div>
      <div id="ds-config-web" style="display:none">
        <div class="form-group">
          <label>URL（每行一个）</label>
          <textarea class="input" id="ds-web-urls" rows="4" placeholder="https://docs.example.com/api"></textarea>
        </div>
        <div class="form-group">
          <label>爬取模式</label>
          <select class="select" id="ds-web-mode">
            <option value="single">单页模式（只抓指定 URL）</option>
            <option value="recursive">递归爬取（自动发现同域名链接）</option>
          </select>
        </div>
      </div>
      <div class="form-group">
        <label>定时同步（cron 表达式，留空=手动）</label>
        <input class="input" id="ds-new-cron" placeholder="如：0 */2 * * *（每2小时）">
      </div>
    `;
    UI.showDynamicModal('新增数据源', html, [
      { text: '取消', onClick: () => UI.hideModal() },
      { text: '测试连接', class: 'btn btn-outline', onClick: testNew },
      { text: '保存', class: 'btn btn-primary', onClick: createSource },
    ]);
  }

  function toggleConfig() {
    const type = document.getElementById('ds-new-type').value;
    document.getElementById('ds-config-git').style.display = type === 'git' ? 'block' : 'none';
    document.getElementById('ds-config-web').style.display = type === 'web_url' ? 'block' : 'none';
  }

  function _getConfig() {
    const type = document.getElementById('ds-new-type').value;
    if (type === 'git') {
      return {
        repo_url: document.getElementById('ds-git-url').value.trim(),
        branch: document.getElementById('ds-git-branch').value.trim() || 'main',
        path: document.getElementById('ds-git-path').value.trim(),
        auth_token: document.getElementById('ds-git-token').value.trim(),
      };
    } else {
      const urls = document.getElementById('ds-web-urls').value.trim().split('\n').filter(Boolean);
      return {
        urls,
        crawl_mode: document.getElementById('ds-web-mode').value,
        max_pages: 50,
      };
    }
  }

  async function testNew() {
    const type = document.getElementById('ds-new-type').value;
    const config = _getConfig();
    try {
      const result = await API.request('/api/data-sources/test', {
        method: 'POST',
        body: { source_type: type, config },
      });
      alert(result.success ? `✅ ${result.message}` : `❌ ${result.message}`);
    } catch (e) {
      alert('测试失败: ' + e.message);
    }
  }

  async function createSource() {
    const name = document.getElementById('ds-new-name').value.trim();
    const type = document.getElementById('ds-new-type').value;
    const config = _getConfig();
    const cron = document.getElementById('ds-new-cron').value.trim();

    if (!name) { alert('请输入名称'); return; }
    if (type === 'git' && !config.repo_url) { alert('请输入仓库地址'); return; }
    if (type === 'web_url' && !config.urls.length) { alert('请输入 URL'); return; }

    try {
      await API.request('/api/data-sources', {
        method: 'POST',
        body: { kb_id: currentKbId, name, source_type: type, config, sync_cron: cron },
      });
      UI.hideModal();
      await loadSources();
    } catch (e) {
      alert('创建失败: ' + e.message);
    }
  }

  async function editSource(id) {
    const s = sources.find(x => x.id === id);
    if (!s) return;
    const config = s.config || {};
    let html = `
      <div class="form-group">
        <label>名称</label>
        <input class="input" id="ds-edit-name" value="${esc(s.name)}">
      </div>
      <div class="form-group">
        <label>定时同步</label>
        <input class="input" id="ds-edit-cron" value="${esc(s.sync_cron)}" placeholder="留空=手动">
      </div>
    `;
    if (s.source_type === 'git') {
      html += `
        <div class="form-group"><label>仓库地址</label><input class="input" id="ds-edit-git-url" value="${esc(config.repo_url||'')}"></div>
        <div class="form-group"><label>分支</label><input class="input" id="ds-edit-git-branch" value="${esc(config.branch||'main')}"></div>
        <div class="form-group"><label>目录</label><input class="input" id="ds-edit-git-path" value="${esc(config.path||'')}"></div>
      `;
    } else if (s.source_type === 'web_url') {
      html += `
        <div class="form-group"><label>URL 列表</label><textarea class="input" id="ds-edit-web-urls" rows="4">${(config.urls||[]).join('\n')}</textarea></div>
      `;
    }
    UI.showDynamicModal('编辑数据源', html, [
      { text: '取消', onClick: () => UI.hideModal() },
      { text: '保存', class: 'btn btn-primary', onClick: async () => {
        const body = { name: document.getElementById('ds-edit-name').value.trim(), sync_cron: document.getElementById('ds-edit-cron').value.trim() };
        if (s.source_type === 'git') {
          body.config = {
            ...config,
            repo_url: document.getElementById('ds-edit-git-url').value.trim(),
            branch: document.getElementById('ds-edit-git-branch').value.trim(),
            path: document.getElementById('ds-edit-git-path').value.trim(),
          };
        } else if (s.source_type === 'web_url') {
          body.config = { ...config, urls: document.getElementById('ds-edit-web-urls').value.trim().split('\n').filter(Boolean) };
        }
        try {
          await API.request(`/api/data-sources/${id}`, { method: 'PUT', body });
          UI.hideModal();
          await loadSources();
        } catch(e) { alert('保存失败: ' + e.message); }
      }},
    ]);
  }

  async function remove(id) {
    if (!confirm('确定删除该数据源？')) return;
    try {
      await API.request(`/api/data-sources/${id}`, { method: 'DELETE' });
      sources = sources.filter(s => s.id !== id);
      renderTable();
    } catch (e) {
      alert('删除失败: ' + e.message);
    }
  }

  function timeAgo(iso) {
    const d = new Date(iso);
    const diff = (Date.now() - d.getTime()) / 1000;
    if (diff < 60) return '刚刚';
    if (diff < 3600) return Math.floor(diff / 60) + '分钟前';
    if (diff < 86400) return Math.floor(diff / 3600) + '小时前';
    return Math.floor(diff / 86400) + '天前';
  }

  function esc(s) {
    const d = document.createElement('div');
    d.textContent = s || '';
    return d.innerHTML;
  }

  function openFromKB(kbId) {
    kbId = kbId || window.__currentKbId || '';
    try { kbId = kbId || localStorage.getItem('__currentKbId') || ''; } catch(e){}
    if (!kbId) { alert('无法获取知识库ID'); return; }
    currentKbId = kbId;
    document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
    document.getElementById('data-source').classList.add('active');
    loadSources();
  }

  async function loadInTab() {
    var kbId = window.__currentKbId || localStorage.getItem('__currentKbId') || '';
    if (!kbId) {
      document.getElementById('ds-tab-body').innerHTML = '<tr><td colspan="5" style="text-align:center;padding:40px;color:#999;">请先选择知识库</td></tr>';
      return;
    }
    currentKbId = kbId;
    try {
      var data = await API.request('/api/data-sources?kb_id=' + kbId);
      var items = Array.isArray(data) ? data : (data.items || []);
      var tbody = document.getElementById('ds-tab-body');
      if (!items.length) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;padding:40px;color:#999;">暂无数据源</td></tr>';
        return;
      }
      tbody.innerHTML = items.map(function(s) {
        var typeLabel = s.source_type === 'git' ? '📦 Git' : '🌐 URL';
        var statusLabel = s.sync_status === 'success' ? '<span style="color:#52c41a">✓ 同步成功</span>' :
                         s.sync_status === 'syncing' ? '<span style="color:#1890ff">⟳ 同步中</span>' :
                         s.sync_status === 'error' ? '<span style="color:#ff4d4f">✗ ' + (s.last_error || '失败') + '</span>' : '未同步';
        return '<tr>' +
          '<td><strong>' + UI.escapeHtml(s.name) + '</strong></td>' +
          '<td>' + typeLabel + '</td>' +
          '<td>' + statusLabel + '</td>' +
          '<td>' + (s.last_sync_at ? s.last_sync_at.slice(0, 16) : '-') + '</td>' +
          '<td><button class="btn btn-xs" onclick="PageDataSource.syncNow(\'' + s.id + '\')">同步</button> ' +
          '<button class="btn btn-xs" onclick="PageDataSource.remove(\'' + s.id + '\')">删除</button></td>' +
          '</tr>';
      }).join('');
    } catch (e) {
      document.getElementById('ds-tab-body').innerHTML = '<tr><td colspan="5" style="text-align:center;padding:20px;color:#ff4d4f;">加载失败: ' + e.message + '</td></tr>';
    }
  }

  return { init, load, showCreate, toggleConfig, syncNow, editSource, remove, openFromKB, loadInTab };
})();
