/**
 * 智能问答页 — 多轮对话 + 反馈
 */
const PageQA = (() => {
  let currentConvId = null;
  let lastTurnId = null;

  async function ensureConversation() {
    if (currentConvId) return currentConvId;
    try {
      const data = await API.request('/api/conversations', {
        method: 'POST', body: { title: '新对话' },
      });
      currentConvId = data.id;
      return currentConvId;
    } catch (e) {
      console.error('创建对话失败:', e);
      return null;
    }
  }

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
      // 创建对话
      const convId = await ensureConversation();

      // 保存用户消息
      if (convId) {
        await API.request(`/api/conversations/${convId}/turns`, {
          method: 'POST', body: { role: 'user', content: question },
        });
      }

      // 获取多轮上下文（最近 3 轮）
      let history = '';
      if (convId) {
        try {
          const convData = await API.request(`/api/conversations/${convId}/turns`);
          const turns = convData.turns || [];
          const recent = turns.slice(-6); // 最近 3 轮 = 6 条消息
          if (recent.length > 1) {
            history = recent.slice(0, -1).map(t =>
              `${t.role === 'user' ? '用户' : '助手'}: ${t.content}`
            ).join('\n');
          }
        } catch {}
      }

      const topK = parseInt(document.getElementById('qa-topk').value) || 5;
      const useHybrid = document.getElementById('qa-hybrid')?.checked ?? true;
      const body = { question, top_k: topK, use_hybrid: useHybrid, conv_id: convId, use_reranker: true };
      const kbId = document.getElementById('qa-kb-filter')?.value || '';
      if (kbId) body.kb_id = kbId;

      const startTime = Date.now();
      const data = await API.request('/api/query', { method: 'POST', body });
      const latency = Date.now() - startTime;

      removeMessage(loadingId);
      let answer = data.answer || '未获取到回答';
      if (data.sources && data.sources.length) {
        answer += '<div style="margin-top:8px;">' +
          data.sources.map(s => `<span class="source-tag">📎 ${s}</span>`).join(' ') + '</div>';
      }

      const msgId = addMessage('assistant', answer);

      // 保存助手回复
      if (convId) {
        try {
          const turnData = await API.request(`/api/conversations/${convId}/turns`, {
            method: 'POST',
            body: {
              role: 'assistant', content: data.answer || '',
              sources: data.sources || [], latency_ms: latency,
            },
          });
          lastTurnId = turnData.id;
          // 把 turn_id 存到消息元素上
          const msgEl = document.getElementById(msgId);
          if (msgEl) msgEl.dataset.turnId = turnData.id;
        } catch {}
      }
    } catch (e) {
      removeMessage(loadingId);
      addMessage('assistant', '❌ 请求失败：' + e.message);
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
        <button class="feedback-btn" title="👍" onclick="PageQA.feedback(this.closest('.message'),'up')">👍</button>
        <button class="feedback-btn" title="👎" onclick="PageQA.feedback(this.closest('.message'),'down')">👎</button>
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

  async function feedback(msgEl, rating) {
    const turnId = msgEl?.dataset?.turnId;
    if (!turnId) return;
    const btns = msgEl.querySelectorAll('.feedback-btn');
    btns.forEach(b => b.style.opacity = '0.4');
    event.target.style.opacity = '1';
    try {
      await API.request('/api/feedback', {
        method: 'POST',
        body: { turn_id: turnId, rating },
      });
    } catch (e) {
      console.error('反馈失败:', e);
    }
  }

  function askPreset(btn) {
    const q = btn.textContent.replace(/^📋\s*/, '');
    document.getElementById('qa-input').value = q;
    askQuestion();
  }

  async function newChat() {
    currentConvId = null;
    lastTurnId = null;
    // 刷新对话列表
    loadConversationList();
    document.getElementById('chat-messages').innerHTML =
      `<div style="text-align:center;padding:60px 20px;color:#999;" id="qa-empty-state">
        <div style="font-size:48px;margin-bottom:16px;">💬</div>
        <div style="font-size:16px;">输入问题开始对话</div>
        <div style="margin-top:24px;display:flex;flex-direction:column;gap:10px;align-items:center;">
          <button class="btn" style="max-width:500px;width:100%;justify-content:flex-start;text-align:left;font-size:13px;padding:10px 16px;" onclick="PageQA.askPreset(this)">📋 知识库系统有什么功能模块？</button>
          <button class="btn" style="max-width:500px;width:100%;justify-content:flex-start;text-align:left;font-size:13px;padding:10px 16px;" onclick="PageQA.askPreset(this)">📋 P1阶段将会更新什么模块？</button>
        </div></div>`;
  }

  async function loadConversationList() {
    // 加载知识库列表（下拉框）
    loadKBFilter();
    try {
      const convs = await API.request('/api/conversations');
      const list = document.getElementById('chat-list');
      if (!convs.length) {
        list.innerHTML = '<div class="chat-item active"><div class="title">新对话</div><div class="meta">刚刚</div></div>';
        return;
      }
      list.innerHTML = convs.map(c => {
        const isActive = c.id === currentConvId;
        const time = c.updated_at ? c.updated_at.substring(5, 16).replace('T', ' ') : '';
        return `<div class="chat-item${isActive ? ' active' : ''}">
          <div class="title" onclick="PageQA.loadConversation('${c.id}')">${c.title || '新对话'}</div>
          <div class="flex-between" style="margin-top:2px;">
            <span class="meta">${time}</span>
            <span class="delete-btn" onclick="event.stopPropagation();PageQA.deleteConversation('${c.id}')" title="删除">🗑️</span>
          </div>
        </div>`;
      }).join('');
    } catch {}
  }

  async function loadKBFilter() {
    const sel = document.getElementById('qa-kb-filter');
    if (!sel || sel.options.length > 1) return; // 已加载
    try {
      const data = await API.request('/api/knowledge-bases?page=1&page_size=100');
      (data.items || []).forEach(k => {
        const opt = document.createElement('option');
        opt.value = k.id;
        opt.textContent = k.name;
        sel.appendChild(opt);
      });
    } catch {}
  }

  async function loadConversation(convId) {
    currentConvId = convId;
    lastTurnId = null;
    try {
      const data = await API.request(`/api/conversations/${convId}/turns`);
      const div = document.getElementById('chat-messages');
      div.innerHTML = '';
      for (const t of (data.turns || [])) {
        const msgId = addMessage(t.role, t.content);
        if (t.role === 'assistant' && t.id) {
          const msgEl = document.getElementById(msgId);
          if (msgEl) msgEl.dataset.turnId = t.id;
          lastTurnId = t.id;
        }
      }
      if (!data.turns?.length) {
        div.innerHTML = '<div style="text-align:center;padding:60px 20px;color:#999;">对话为空</div>';
      }
      // 更新列表高亮
      loadConversationList();
    } catch (e) {
      console.error('加载对话失败:', e);
    }
  }

  async function deleteConversation(convId) {
    if (!confirm('确认删除该对话？所有轮次和反馈将一并删除。')) return;
    try {
      await API.request(`/api/conversations/${convId}`, { method: 'DELETE' });
      if (currentConvId === convId) {
        newChat();
      } else {
        loadConversationList();
      }
    } catch (e) {
      alert('删除失败: ' + e.message);
    }
  }

  return { askQuestion, askPreset, newChat, feedback, loadConversationList, loadConversation, deleteConversation };
})();

Router.on('qa-chat', () => PageQA.loadConversationList());
