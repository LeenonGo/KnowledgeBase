/**
 * 智能问答页
 */
const PageQA = (() => {

  async function askQuestion() {
    const input = document.getElementById('qa-input');
    const question = input.value.trim();
    if (!question) return;
    input.disabled = true;
    const sendBtn = document.getElementById('qa-send-btn');
    sendBtn.disabled = true;
    sendBtn.textContent = '思考中...';
    addMessage('user', question);
    input.value = '';
    const loadingId = addMessage('loading', '正在检索知识库并生成回答，请稍候...');

    try {
      const topK = parseInt(document.getElementById('qa-topk').value) || 5;
      const body = { question, top_k: topK };
      const kbId = PageKB.getCurrentKbId();
      if (kbId) body.kb_id = kbId;

      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 60000);

      const data = await API.request('/api/query', {
        method: 'POST',
        body,
        signal: controller.signal,
      });
      clearTimeout(timeout);

      removeMessage(loadingId);
      let answer = data.answer || '未获取到回答';
      if (data.sources && data.sources.length) {
        answer += '<div style="margin-top:8px;">' +
          data.sources.map(s => `<span class="source-tag">📎 ${s}</span>`).join(' ') + '</div>';
      }
      addMessage('assistant', answer);
    } catch (e) {
      removeMessage(loadingId);
      if (e.name === 'AbortError') {
        addMessage('assistant', '❌ 请求超时（60秒），请检查网络或稍后重试。');
      } else {
        addMessage('assistant', '❌ 请求失败：' + e.message);
      }
    } finally {
      input.disabled = false;
      sendBtn.disabled = false;
      sendBtn.textContent = '发送';
      input.focus();
    }
  }

  function addMessage(role, content) {
    const id = 'msg-' + Date.now();
    const div = document.getElementById('chat-messages');
    const empty = div.querySelector('div[style*="text-align:center"]');
    if (empty) empty.remove();
    const el = document.createElement('div');
    el.className = 'message ' + role;
    el.id = id;
    const avatar = role === 'user' ? '你' : 'AI';
    const bg = role === 'user' ? '#1890ff' : '#f5f5f5';
    const color = role === 'user' ? '#fff' : '#333';
    let html = role === 'loading'
      ? '<div style="color:#999;">⏳ 思考中...</div>'
      : (role === 'assistant' ? UI.md2html(content) : content);
    if (role !== 'user' && role !== 'loading') {
      html += `<div class="chat-actions">
        <button class="feedback-btn" title="👍" onclick="PageQA.feedback(this,'up')">👍</button>
        <button class="feedback-btn" title="👎" onclick="PageQA.feedback(this,'down')">👎</button>
      </div>`;
    }
    el.innerHTML = `<div class="avatar" style="background:${bg};color:${color}">${avatar}</div><div class="bubble">${html}</div>`;
    div.appendChild(el);
    div.scrollTop = div.scrollHeight;
    return id;
  }

  function removeMessage(id) {
    const el = document.getElementById(id);
    if (el) el.remove();
  }

  async function feedback(btn, rating) {
    btn.style.opacity = '1';
    btn.parentElement.querySelectorAll('.feedback-btn').forEach(b => {
      if (b !== btn) b.style.opacity = '0.4';
    });
    // TODO: 调用 /api/feedback 需要 turn_id，需要对话历史接入后实现
  }

  function askPreset(btn) {
    const q = btn.textContent.replace(/^📋\s*/, '');
    document.getElementById('qa-input').value = q;
    askQuestion();
  }

  function newChat() {
    document.getElementById('chat-list').innerHTML =
      '<div class="chat-item active"><div class="title">新对话</div><div class="meta">刚刚</div></div>';
    document.getElementById('chat-messages').innerHTML =
      `<div style="text-align:center;padding:60px 20px;color:#999;" id="qa-empty-state">
        <div style="font-size:48px;margin-bottom:16px;">💬</div>
        <div style="font-size:16px;">输入问题开始对话</div>
        <div style="margin-top:24px;display:flex;flex-direction:column;gap:10px;align-items:center;">
          <button class="btn" style="max-width:500px;width:100%;justify-content:flex-start;text-align:left;font-size:13px;padding:10px 16px;" onclick="PageQA.askPreset(this)">📋 知识库系统有什么功能模块？</button>
          <button class="btn" style="max-width:500px;width:100%;justify-content:flex-start;text-align:left;font-size:13px;padding:10px 16px;" onclick="PageQA.askPreset(this)">📋 P1阶段将会更新什么模块？</button>
        </div></div>`;
  }

  return { askQuestion, askPreset, newChat, feedback };
})();

Router.on('qa-chat', () => {});
