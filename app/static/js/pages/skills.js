/**
 * v6.0 Skills 管理页
 */
const PageSkills = (() => {
  let skills = [];
  let categories = [];
  let currentCategory = '';
  let editingSkill = null;

  function init() {
    Router.on('skills', load);
  }

  async function load() {
    await Promise.all([loadSkills(), loadCategories(), loadStats()]);
  }

  async function loadSkills() {
    try {
      const params = currentCategory ? `?category=${currentCategory}` : '';
      skills = await API.request(`/api/skills${params}`);
      renderTable();
    } catch (e) {
      document.getElementById('skills-table-body').innerHTML =
        `<tr><td colspan="7" class="empty">加载失败: ${e.message}</td></tr>`;
    }
  }

  async function loadCategories() {
    try {
      categories = await API.request('/api/skills/meta/categories');
      renderCategoryFilter();
    } catch (e) {}
  }

  async function loadStats() {
    try {
      const stats = await API.request('/api/skills/stats/overview');
      renderStats(stats);
    } catch (e) {}
  }

  function renderStats(stats) {
    const el = document.getElementById('skills-stats');
    if (!el) return;
    el.innerHTML = `
      <div class="stat-card"><div class="stat-num">${stats.total}</div><div class="stat-label">总 Skill</div></div>
      <div class="stat-card"><div class="stat-num">${stats.enabled}</div><div class="stat-label">已启用</div></div>
      <div class="stat-card"><div class="stat-num">${stats.custom}</div><div class="stat-label">自定义</div></div>
      <div class="stat-card"><div class="stat-num">${stats.top_skills?.[0]?.usage_count || 0}</div><div class="stat-label">最高调用</div></div>
    `;
  }

  function renderCategoryFilter() {
    const el = document.getElementById('skills-category-filter');
    if (!el) return;
    const categoryLabels = {
      retrieval: '🔍 检索', analysis: '📊 分析', generation: '✨ 生成',
      utility: '🔧 工具', memory: '🧠 记忆', general: '📁 其他'
    };
    el.innerHTML = `<span class="filter-tag ${!currentCategory ? 'active' : ''}" onclick="PageSkills.filterCategory('')">全部</span>` +
      categories.map(c => `<span class="filter-tag ${currentCategory === c.name ? 'active' : ''}" onclick="PageSkills.filterCategory('${c.name}')">${categoryLabels[c.name] || c.name} (${c.count})</span>`).join('');
  }

  function renderTable() {
    const tbody = document.getElementById('skills-table-body');
    if (!skills.length) {
      tbody.innerHTML = '<tr><td colspan="7" class="empty">暂无 Skill</td></tr>';
      return;
    }

    const categoryColors = {
      retrieval: '#1890ff', analysis: '#52c41a', generation: '#722ed1',
      utility: '#fa8c16', memory: '#eb2f96', general: '#999'
    };

    tbody.innerHTML = skills.map(s => {
      const color = categoryColors[s.category] || '#999';
      return `<tr>
        <td><span style="font-size:20px;margin-right:6px">${s.icon}</span><b>${esc(s.display_name)}</b></td>
        <td><span class="badge" style="background:${color}20;color:${color}">${s.category}</span></td>
        <td>${esc(s.description).slice(0, 60)}${s.description.length > 60 ? '...' : ''}</td>
        <td><code style="font-size:11px">${s.handler_type}</code></td>
        <td style="text-align:center">
          <label class="switch">
            <input type="checkbox" ${s.is_enabled ? 'checked' : ''} onchange="PageSkills.toggleSkill('${s.id}')" ${s.is_builtin && s.is_enabled ? 'disabled' : ''}>
            <span class="slider"></span>
          </label>
        </td>
        <td style="text-align:center">${s.usage_count}</td>
        <td>
          <a onclick="PageSkills.testSkill('${s.id}')" style="color:#1890ff;cursor:pointer;margin-right:8px">测试</a>
          ${s.is_builtin ? '<span style="color:#ccc">内置</span>' : `<a onclick="PageSkills.editSkill('${s.id}')" style="cursor:pointer;margin-right:8px">编辑</a><a onclick="PageSkills.deleteSkill('${s.id}')" style="color:#ff4d4f;cursor:pointer">删除</a>`}
        </td>
      </tr>`;
    }).join('');
  }

  function filterCategory(cat) {
    currentCategory = cat;
    loadCategories();
    loadSkills();
  }

  async function toggleSkill(id) {
    try {
      await API.request(`/api/skills/${id}/toggle`, { method: 'POST' });
      await loadSkills();
    } catch (e) {
      alert('操作失败: ' + e.message);
    }
  }

  function showCreate() {
    editingSkill = null;
    const html = `
      <div class="form-row">
        <div class="form-group" style="flex:1">
          <label>唯一标识 *</label>
          <input class="input" id="skill-name" placeholder="如: my_custom_skill">
        </div>
        <div class="form-group" style="flex:1">
          <label>显示名称 *</label>
          <input class="input" id="skill-display-name" placeholder="如: 我的自定义技能">
        </div>
      </div>
      <div class="form-row">
        <div class="form-group" style="flex:1">
          <label>分类</label>
          <select class="select" id="skill-category">
            <option value="retrieval">🔍 检索</option>
            <option value="analysis">📊 分析</option>
            <option value="generation">✨ 生成</option>
            <option value="utility">🔧 工具</option>
            <option value="memory">🧠 记忆</option>
          </select>
        </div>
        <div class="form-group" style="flex:1">
          <label>图标 (Emoji)</label>
          <input class="input" id="skill-icon" value="⚡" style="width:60px">
        </div>
      </div>
      <div class="form-group">
        <label>描述</label>
        <textarea class="input" id="skill-desc" rows="2" placeholder="这个 Skill 做什么？"></textarea>
      </div>
      <div class="form-group">
        <label>类型</label>
        <select class="select" id="skill-handler-type">
          <option value="prompt">🤖 Prompt（LLM + 工具链）</option>
          <option value="http">🌐 HTTP API</option>
          <option value="python">🐍 Python 函数</option>
        </select>
      </div>
      <div id="skill-config-prompt">
        <div class="form-group">
          <label>System Prompt</label>
          <textarea class="input" id="skill-prompt-system" rows="3" placeholder="你是一个..."></textarea>
        </div>
        <div class="form-group">
          <label>用户模板</label>
          <input class="input" id="skill-prompt-template" placeholder="{input}">
        </div>
        <div class="form-group">
          <label>可用工具（逗号分隔）</label>
          <input class="input" id="skill-prompt-tools" placeholder="sql_query,chart_generator">
        </div>
      </div>
      <div class="form-group">
        <label>参数 Schema (JSON)</label>
        <textarea class="input" id="skill-params" rows="4" style="font-family:monospace;font-size:12px">{"type":"object","properties":{"input":{"type":"string","description":"输入内容"}},"required":["input"]}</textarea>
      </div>
    `;
    UI.showDynamicModal('创建 Skill', html, [
      { text: '取消', onClick: () => UI.hideModal() },
      { text: '保存', class: 'btn btn-primary', onClick: createSkill },
    ]);
  }

  async function createSkill() {
    const name = document.getElementById('skill-name').value.trim();
    const display_name = document.getElementById('skill-display-name').value.trim();
    if (!name || !display_name) { alert('请填写必填项'); return; }

    const handler_type = document.getElementById('skill-handler-type').value;
    let handler_config = '{}';

    if (handler_type === 'prompt') {
      handler_config = JSON.stringify({
        system: document.getElementById('skill-prompt-system').value,
        template: document.getElementById('skill-prompt-template').value || '{input}',
        tools: (document.getElementById('skill-prompt-tools').value || '').split(',').filter(Boolean),
      });
    }

    try {
      await API.request('/api/skills', {
        method: 'POST',
        body: {
          name,
          display_name,
          description: document.getElementById('skill-desc').value,
          category: document.getElementById('skill-category').value,
          icon: document.getElementById('skill-icon').value || '⚡',
          handler_type,
          handler_config,
          parameters_schema: document.getElementById('skill-params').value,
        },
      });
      UI.hideModal();
      await loadSkills();
      await loadCategories();
    } catch (e) {
      alert('创建失败: ' + e.message);
    }
  }

  async function testSkill(id) {
    const skill = skills.find(s => s.id === id);
    if (!skill) return;

    const html = `
      <div class="form-group">
        <label>参数 (JSON)</label>
        <textarea class="input" id="test-args" rows="4" style="font-family:monospace;font-size:12px">{}</textarea>
      </div>
      <div id="test-result" style="margin-top:12px;display:none">
        <label>执行结果</label>
        <pre style="background:#f5f5f5;padding:12px;border-radius:6px;max-height:300px;overflow:auto;font-size:12px"></pre>
      </div>
    `;
    UI.showDynamicModal(`测试: ${skill.display_name}`, html, [
      { text: '关闭', onClick: () => UI.hideModal() },
      { text: '执行', class: 'btn btn-primary', onClick: async () => {
        try {
          const args = JSON.parse(document.getElementById('test-args').value || '{}');
          const result = await API.request(`/api/skills/${id}/test`, {
            method: 'POST',
            body: { arguments: args },
          });
          const resultEl = document.getElementById('test-result');
          resultEl.style.display = 'block';
          resultEl.querySelector('pre').textContent = result.result;
        } catch (e) {
          alert('执行失败: ' + e.message);
        }
      }},
    ]);
  }

  async function editSkill(id) {
    const skill = skills.find(s => s.id === id);
    if (!skill) return;

    const html = `
      <div class="form-group">
        <label>显示名称</label>
        <input class="input" id="edit-display-name" value="${esc(skill.display_name)}">
      </div>
      <div class="form-group">
        <label>描述</label>
        <textarea class="input" id="edit-desc" rows="2">${esc(skill.description)}</textarea>
      </div>
      <div class="form-group">
        <label>图标 (Emoji)</label>
        <input class="input" id="edit-icon" value="${esc(skill.icon)}" style="width:60px">
      </div>
    `;
    UI.showDynamicModal(`编辑: ${skill.display_name}`, html, [
      { text: '取消', onClick: () => UI.hideModal() },
      { text: '保存', class: 'btn btn-primary', onClick: async () => {
        try {
          await API.request(`/api/skills/${id}`, {
            method: 'PUT',
            body: {
              display_name: document.getElementById('edit-display-name').value,
              description: document.getElementById('edit-desc').value,
              icon: document.getElementById('edit-icon').value,
            },
          });
          UI.hideModal();
          await loadSkills();
        } catch (e) {
          alert('保存失败: ' + e.message);
        }
      }},
    ]);
  }

  async function deleteSkill(id) {
    if (!confirm('确定删除该 Skill？')) return;
    try {
      await API.request(`/api/skills/${id}`, { method: 'DELETE' });
      await loadSkills();
      await loadCategories();
    } catch (e) {
      alert('删除失败: ' + e.message);
    }
  }

  function esc(s) {
    const d = document.createElement('div');
    d.textContent = s || '';
    return d.innerHTML;
  }

  return {
    init, load, showCreate, filterCategory, toggleSkill,
    testSkill, editSkill, deleteSkill
  };
})();
