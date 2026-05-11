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
      const convId = await ensureConversation();

      // 保存用户消息
      if (convId) {
        await API.request(`/api/conversations/${convId}/turns`, {
          method: 'POST', body: { role: 'user', content: question },
        });
      }

      // 多轮上下文
      let history = '';
      if (convId) {
        try {
          const convData = await API.request(`/api/conversations/${convId}/turns`);
          const turns = convData.turns || [];
          const recent = turns.slice(-6);
          if (recent.length > 1) {
            history = recent.slice(0, -1).map(t =>
              `${t.role === 'user' ? '用户' : '助手'}: ${t.content}`
            ).join('\n');
          }
        } catch {}
      }

      const topK = parseInt(document.getElementById('qa-topk').value) || 10;
      const useHybrid = document.getElementById('qa-hybrid')?.checked ?? true;
      const body = { question, top_k: topK, use_hybrid: useHybrid, conv_id: convId, use_reranker: false };
      body.use_rewrite = document.getElementById('qa-rewrite')?.checked ?? false;
      body.use_polish = document.getElementById('qa-polish')?.checked ?? false;
      body.use_agent = document.getElementById('qa-agent')?.checked ?? false;
      body.use_web_search = document.getElementById('qa-web-search')?.checked ?? false;
      const kbId = document.getElementById('qa-kb-filter')?.value || '';
      if (kbId) body.kb_id = kbId;

      // ── 流式请求 ──
      removeMessage(loadingId);
      const msgId = addMessage('assistant', '<span id="streaming-text"></span>');
      const msgEl = document.getElementById(msgId);
      const bubble = msgEl?.querySelector('.bubble');
      const textEl = document.getElementById('streaming-text');
      const startTime = Date.now();

      // 收集的来源
      const detectedSources = new Set();
      const sourcesEl = document.createElement('div');
      sourcesEl.className = 'source-tags-row';

      try {
        const resp = await fetch('/api/query/stream', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'Authorization': API.getToken() ? `Bearer ${API.getToken()}` : '' },
          body: JSON.stringify(body),
        });

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let finalSources = [];
        let finalCitations = [];
        let assistantContent = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || ''; // 保留不完整的行

          for (let i = 0; i < lines.length; i++) {
            const line = lines[i];
            if (!line.startsWith('event:')) continue;
            const eventType = line.slice(6).trim();
            const dataLine = (i + 1 < lines.length) ? lines[i + 1] : '';
            if (!dataLine.startsWith('data:')) continue;
            i++; // 跳过 data 行
            const dataStr = dataLine.slice(5).trim();
            let data;
            try { data = JSON.parse(dataStr); } catch { continue; }

            if (eventType === 'token') {
              assistantContent += data;
              textEl.textContent = assistantContent;
              // 流式渲染 Markdown
              if (bubble) {
                bubble.innerHTML = UI.md2html(assistantContent);
                bubble.appendChild(sourcesEl);
              }
            } else if (eventType === 'thought' && chainContainer) {
              const chainBody = chainContainer.querySelector('.agent-chain-body');
              const stepEl = document.createElement('div');
              stepEl.className = 'chain-step chain-thought';
              stepEl.innerHTML = `<span class="chain-icon">💭</span><span class="chain-label">思考 Step ${data.step}</span><div class="chain-content">${data.content}</div>`;
              chainBody.appendChild(stepEl);
            } else if (eventType === 'action' && chainContainer) {
              const chainBody = chainContainer.querySelector('.agent-chain-body');
              const stepEl = document.createElement('div');
              stepEl.className = 'chain-step chain-action';
              stepEl.innerHTML = `<span class="chain-icon">⚡</span><span class="chain-label">调用 ${data.tool}</span><div class="chain-content"><code>${JSON.stringify(data.arguments)}</code></div>`;
              chainBody.appendChild(stepEl);
            } else if (eventType === 'observe' && chainContainer) {
              const chainBody = chainContainer.querySelector('.agent-chain-body');
              const stepEl = document.createElement('div');
              stepEl.className = 'chain-step chain-observe';
              stepEl.innerHTML = `<span class="chain-icon">👁️</span><span class="chain-label">观察</span><div class="chain-content">${data.content.substring(0, 300)}</div>`;
              chainBody.appendChild(stepEl);
            } else if (eventType === 'answer' && isAgentMode) {
              assistantContent = data.content || '';
              finalSources = data.sources || [];
              textEl.textContent = assistantContent;
              if (bubble) {
                bubble.innerHTML = UI.md2html(assistantContent);
                bubble.appendChild(sourcesEl);
              }
            } else if (eventType === 'source') {
              if (!detectedSources.has(data.source)) {
                detectedSources.add(data.source);
                const tag = document.createElement('span');
                tag.className = 'source-tag';
                tag.textContent = '📎 ' + data.source;
                tag.style.cursor = 'pointer';
                tag.title = '点击查看来源';
                sourcesEl.appendChild(tag);
              }
            } else if (eventType === 'done') {
              finalSources = data.sources || [];
              finalCitations = data.citations || [];
            }
          }
        }

        const latency = Date.now() - startTime;
        const latencySec = (latency / 1000).toFixed(1);

        // 补充末尾残留 buffer
        if (buffer.startsWith('data:')) {
          try { assistantContent += JSON.parse(buffer.slice(5)); } catch {}
        }

        // 渲染引用标注 [1][2][3] 可点击 + hover 显示原文
        if (finalCitations.length && bubble) {
          let html = bubble.innerHTML;
          // 将 [数字] 替换为可点击的引用标签
          html = html.replace(/\[(\d+)\]/g, (match, num) => {
            const cite = finalCitations.find(c => c.index === parseInt(num));
            if (!cite) return match;
            const preview = (cite.text_preview || '').replace(/"/g, '&quot;').replace(/</g, '&lt;');
            return `<sup class="cite-ref" data-cite-id="${cite.citation_id}" data-source="${cite.source}" data-preview="${preview}" title="来源: ${cite.source}\n${preview.substring(0,100)}..." onclick="showCiteDetail(this)">[${num}]</sup>`;
          });
          bubble.innerHTML = html;
          bubble.appendChild(sourcesEl);
        }

        // 结束时：未检测到来源时用检索到的 sources
        if (!detectedSources.size && finalSources.length) {
          finalSources.forEach(s => {
            const tag = document.createElement('span');
            tag.className = 'source-tag';
            tag.textContent = '📎 ' + s;
            tag.style.cursor = 'pointer';
            sourcesEl.appendChild(tag);
          });
        }

        // 追加耗时标签
        const metaEl = document.createElement('div');
        metaEl.style.cssText = 'font-size:11px;color:#bbb;margin-top:4px;';
        metaEl.textContent = `⏱ ${latencySec}s`;
        bubble?.appendChild(metaEl);

        // 记录到数据库
        if (convId) {
          try {
            const turnData = await API.request(`/api/conversations/${convId}/turns`, {
              method: 'POST',
              body: { role: 'assistant', content: assistantContent,
                      sources: [...detectedSources],
                      latency_ms: latency },
            });
            if (msgEl) msgEl.dataset.turnId = turnData.id;
          } catch {}
        }

      } catch (e) {
        textEl.textContent = '❌ 请求失败：' + e.message;
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

  function reset() {
    currentConvId = null;
    lastTurnId = null;
    const msgs = document.getElementById('qa-messages');
    if (msgs) msgs.innerHTML = '';
  }

  function showCiteDetail(el) {
    const source = el.dataset.source || '';
    const preview = el.dataset.preview || '';
    const citeId = el.dataset.citeId || '';
    // 创建浮动引用详情卡片
    let card = document.getElementById('cite-detail-card');
    if (card) card.remove();
    card = document.createElement('div');
    card.id = 'cite-detail-card';
    card.style.cssText = 'position:fixed;z-index:9999;background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:16px;box-shadow:0 4px 20px rgba(0,0,0,.15);max-width:420px;min-width:280px;font-size:13px;';
    card.innerHTML = `<div style="font-weight:600;margin-bottom:8px;color:#1890ff;">📄 ${source}</div><div style="color:#666;line-height:1.6;max-height:150px;overflow-y:auto;">${preview}</div><div style="margin-top:8px;font-size:11px;color:#bbb;">ID: ${citeId}</div>`;
    document.body.appendChild(card);
    // 定位
    const rect = el.getBoundingClientRect();
    card.style.left = Math.min(rect.left, window.innerWidth - 440) + 'px';
    card.style.top = (rect.bottom + 8) + 'px';
    // 点击其他地方关闭
    const closeHandler = (e) => { if (!card.contains(e.target) && e.target !== el) { card.remove(); document.removeEventListener('click', closeHandler); }};
    setTimeout(() => document.addEventListener('click', closeHandler), 10);
  }

  window.showCiteDetail = showCiteDetail;

  return { askQuestion, askPreset, newChat, feedback, loadConversationList, loadConversation, deleteConversation, reset, showCiteDetail };
})();

Router.on('qa-chat', () => PageQA.loadConversationList());
