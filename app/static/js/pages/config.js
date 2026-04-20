/**
 * 系统配置页
 */
const PageConfig = (() => {

  function onTabChange(tabId) {
    if (tabId === 'config-tab-model') loadModelConfig();
  }

  async function loadModelConfig() {
    try {
      const cfg = await API.request('/api/config/models');
      if (cfg.llm) {
        const url = cfg.llm.base_url || '';
        let prov = 'custom';
        if (url.includes('dashscope')) prov = 'dashscope';
        else if (url.includes('localhost:11434') || url.includes('ollama')) prov = 'ollama';
        else if (url.includes('api.openai.com')) prov = 'openai';
        document.getElementById('llm-provider').value = prov;
        document.getElementById('llm-model').value = cfg.llm.model || '';
        document.getElementById('llm-base-url').value = url;
        document.getElementById('llm-api-key').value = cfg.llm.api_key || '';
        document.getElementById('llm-max-tokens').value = cfg.llm.max_tokens || 2048;
        document.getElementById('llm-temperature').value = cfg.llm.temperature || 0.7;
      }
      if (cfg.embedding) {
        const url = cfg.embedding.base_url || '';
        let prov = 'custom';
        if (url.includes('dashscope')) prov = 'dashscope';
        else if (url.includes('localhost:11434') || url.includes('ollama')) prov = 'ollama';
        else if (url.includes('api.openai.com')) prov = 'openai';
        document.getElementById('emb-provider').value = prov;
        document.getElementById('emb-model').value = cfg.embedding.model || '';
        document.getElementById('emb-base-url').value = url;
        document.getElementById('emb-api-key').value = cfg.embedding.api_key || '';
        document.getElementById('emb-dimensions').value = cfg.embedding.dimensions || '';
      }
    } catch (e) { console.error('Load config error:', e); }
  }

  async function saveModelConfig() {
    const cfg = {
      llm: {
        provider: document.getElementById('llm-provider').value,
        base_url: document.getElementById('llm-base-url').value,
        api_key: document.getElementById('llm-api-key').value,
        model: document.getElementById('llm-model').value,
        max_tokens: parseInt(document.getElementById('llm-max-tokens').value) || 2048,
        temperature: parseFloat(document.getElementById('llm-temperature').value) || 0.7,
      },
      embedding: {
        provider: document.getElementById('emb-provider').value,
        base_url: document.getElementById('emb-base-url').value,
        api_key: document.getElementById('emb-api-key').value,
        model: document.getElementById('emb-model').value,
        dimensions: parseInt(document.getElementById('emb-dimensions').value) || null,
      }
    };
    try {
      await API.request('/api/config/models', { method: 'POST', body: cfg });
      alert('✅ 配置已保存！更换 Embedding 模型后请重建索引。');
    } catch (e) { alert('保存失败: ' + e.message); }
  }

  async function loadPrompts() {
    try {
      const prompts = await API.request('/api/config/prompts');
      if (prompts.qa) {
        document.getElementById('prompt-qa-system').value = prompts.qa.system || '';
        document.getElementById('prompt-qa-user').value = prompts.qa.user || '';
      }
      if (prompts.rewrite) {
        document.getElementById('prompt-rewrite-system').value = prompts.rewrite.system || '';
        document.getElementById('prompt-rewrite-user').value = prompts.rewrite.user || '';
      }
      if (prompts.refuse) {
        document.getElementById('prompt-refuse-answer').value = prompts.refuse.answer || '';
      }
    } catch (e) { console.error('Load prompts error:', e); }
  }

  function loadPromptEditor() {
    const type = document.getElementById('prompt-selector').value;
    document.getElementById('prompt-qa-panel').style.display = type === 'qa' ? 'block' : 'none';
    document.getElementById('prompt-rewrite-panel').style.display = type === 'rewrite' ? 'block' : 'none';
    document.getElementById('prompt-refuse-panel').style.display = type === 'refuse' ? 'block' : 'none';
  }

  async function savePrompts() {
    const data = {
      qa: {
        system: document.getElementById('prompt-qa-system').value,
        user: document.getElementById('prompt-qa-user').value,
      },
      rewrite: {
        system: document.getElementById('prompt-rewrite-system').value,
        user: document.getElementById('prompt-rewrite-user').value,
      },
      refuse: { answer: document.getElementById('prompt-refuse-answer').value },
    };
    try {
      await API.request('/api/config/prompts', { method: 'POST', body: data });
      alert('✅ Prompt 已保存');
    } catch (e) { alert('保存失败: ' + e.message); }
  }

  async function reindexAll() {
    const el = document.getElementById('reindex-status');
    el.style.display = 'block';
    el.innerHTML = '<span class="tag tag-blue">重建中...</span>';
    try {
      const data = await API.request('/api/reindex', { method: 'POST' });
      el.innerHTML = `<span class="tag tag-green">✅ ${data.message}（${data.count} 个文档块）</span>`;
    } catch (e) {
      el.innerHTML = `<span class="tag tag-red">❌ 失败: ${e.message}</span>`;
    }
  }

  async function reindexCurrentKB() {
    const kbId = PageKB.getCurrentKbId();
    if (!kbId) { alert('请先选择一个知识库'); return; }
    const el = document.getElementById('reindex-status');
    el.style.display = 'block';
    el.innerHTML = '<span class="tag tag-blue">重建中...</span>';
    try {
      const data = await API.request(`/api/reindex?kb_id=${kbId}`, { method: 'POST' });
      el.innerHTML = `<span class="tag tag-green">✅ ${data.message}（${data.count} 个文档块）</span>`;
    } catch (e) {
      el.innerHTML = `<span class="tag tag-red">❌ 失败: ${e.message}</span>`;
    }
  }

  return {
    onTabChange, loadModelConfig, saveModelConfig,
    loadPrompts, loadPromptEditor, savePrompts,
    reindexAll, reindexCurrentKB,
  };
})();

Router.on('sys-config', () => {
  PageConfig.loadPrompts();
});
