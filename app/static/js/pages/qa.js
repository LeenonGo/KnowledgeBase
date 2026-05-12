/**
 * 智能问答页 — RAG 模式（检索增强生成）
 */
const PageQA = (() => {
  let currentConvId = null;
  let lastTurnId = null;

  async function ensureConversation() {
    if (currentConvId) return currentConvId;
    try {
      const data = await API.request('/api/conversations', {
        method: 'POST', body: { title: '新对话', type: 'rag' },
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
      const body = { question, top_k: topK, use_hybrid: useHybrid, conv_id: convId, use_reranker: false, use_agent: false };
      body.use_rewrite = document.getElementById('qa-rewrite')?.checked ?? false;
      body.use_polish = document.getElementById('qa-polish')?.checked ?? false;
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
          const events = buffer.split('\n\n');
          buffer = events.pop() || '';

          for (const evt of events) {
            const lines = evt.split('\n');
            let eventType = null;
            let dataStr = '';
            for (const line of lines) {
              if (line.startsWith('event: ')) eventType = line.slice(7).trim();
              else if (line.startsWith('data: ')) dataStr = line.slice(6).trim();
            }
            if (!eventType || !dataStr) continue;
            let data;
            try { data = JSON.parse(dataStr); } catch { continue; }

            if (eventType === 'token') {
              if (typeof data === 'string') assistantContent += data;
              else assistantContent += JSON.stringify(data);
              if (textEl) textEl.textContent = assistantContent;
              if (bubble) {
                const _cd = UI.extractCharts(assistantContent); bubble.innerHTML = UI.md2html(_cd.text); UI.renderCharts(bubble, _cd.charts);
                bubble.appendChild(sourcesEl);
              }
            } else if (eventType === 'answer') {
              assistantContent = data.content || '';
              finalSources = data.sources || [];
              if (data.citations) finalCitations = data.citations;
              if (textEl) textEl.textContent = assistantContent;
              if (bubble) {
                const _cd = UI.extractCharts(assistantContent); bubble.innerHTML = UI.md2html(_cd.text); UI.renderCharts(bubble, _cd.charts);
                bubble.appendChild(sourcesEl);
              }
            } else if (eventType === 'source') {
              if (!detectedSources.has(data.source)) {
                detectedSources.add(data.source);
                const tag = document.createElement('span');
                tag.className = 'source-tag';
                tag.textContent = '📎 ' + data.source;
                sourcesEl.appendChild(tag);
              }
            } else if (eventType === 'done') {
              finalSources = data.sources || [];
              finalCitations = data.citations || [];
            } else if (eventType === 'error') {
              const errMsg = typeof data === 'string' ? data : (data.content || JSON.stringify(data));
              assistantContent = '❌ ' + errMsg;
              if (textEl) textEl.textContent = assistantContent;
            }
          }
        }

        // 处理残留 buffer
        if (buffer.trim()) {
          for (const line of buffer.split('\n')) {
            if (line.startsWith('data: ')) {
              try { const d = JSON.parse(line.slice(6)); if (typeof d === 'string') assistantContent += d; } catch {}
            }
          }
        }

        const latency = Date.now() - startTime;
        const latencySec = (latency / 1000).toFixed(1);

        // 渲染引用标注 [C1][C2] → 可点击的 hover 弹出原文卡片
        if (finalCitations.length && bubble) {
          const citeMap = {};
          finalCitations.forEach(c => { citeMap[c.index] = c; });
          let html = bubble.innerHTML;
          html = html.replace(/\[C(\d+)\]/g, (match, num) => {
            const cite = citeMap[parseInt(num)];
            if (!cite) return match;
            const preview = (cite.text_preview || cite.text || '').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/\n/g, ' ');
            const source = (cite.source || '').replace(/"/g, '&quot;');
            return `<sup class="cite-ref" data-cite-source="${source}" data-cite-preview="${preview}" onmouseenter="PageQA.showCiteHover(this, event)" onmouseleave="PageQA.hideCiteHover()">[${num}]</sup>`;
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
        if (textEl) textEl.textContent = '❌ 请求失败：' + e.message;
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
    loadKBFilter();
    try {
      const convs = await API.request('/api/conversations?conv_type=rag');
      const list = document.getElementById('chat-list');
      if (!convs.length) {
        list.innerHTML = '<div class="chat-item active"><div class="title">新对话</div><div class="meta">刚刚</div></div>';
        return;
      }
      list.innerHTML = convs.map(c => {
        const isActive = c.id === currentConvId;
        const time = c.updated_at ? c.updated_at.substring(5, 16).replace('T', ' ') : '';
        const pinIcon = c.is_pinned ? '📌' : '';
        const tags = (c.tags || []).map(t => `<span class="conv-tag">${t}</span>`).join('');
        return `<div class="chat-item${isActive ? ' active' : ''}${c.is_pinned ? ' pinned' : ''}">
          <div class="title" onclick="PageQA.loadConversation('${c.id}')">${pinIcon} ${c.title || '新对话'}</div>
          ${tags ? `<div class="conv-tags-row">${tags}</div>` : ''}
          <div class="flex-between" style="margin-top:2px;">
            <span class="meta">${time}</span>
            <div class="conv-actions">
              <span class="conv-action-btn" onclick="event.stopPropagation();PageQA.togglePin('${c.id}')" title="${c.is_pinned ? '取消置顶' : '置顶'}">${c.is_pinned ? '📍' : '📌'}</span>
              <span class="conv-action-btn" onclick="event.stopPropagation();PageQA.editTags('${c.id}')" title="标签">🏷️</span>
              <span class="conv-action-btn" onclick="event.stopPropagation();PageQA.exportConv('${c.id}')" title="导出">📥</span>
              <span class="conv-action-btn" onclick="event.stopPropagation();PageQA.deleteConversation('${c.id}')" title="删除">🗑️</span>
            </div>
          </div>
        </div>`;
      }).join('');
    } catch {}
  }

  async function loadKBFilter() {
    const sel = document.getElementById('qa-kb-filter');
    if (!sel || sel.options.length > 1) return;
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
  }

  let _citeHoverCard = null;
  let _citeHoverTimer = null;

  function showCiteHover(el, e) {
    clearTimeout(_citeHoverTimer);
    hideCiteHover();
    const source = el.getAttribute('data-cite-source') || '';
    const preview = el.getAttribute('data-cite-preview') || '';
    if (!source && !preview) return;
    const card = document.createElement('div');
    card.id = 'cite-hover-card';
    card.style.cssText = 'position:fixed;z-index:9999;background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:14px 16px;box-shadow:0 4px 20px rgba(0,0,0,.18);max-width:400px;min-width:240px;font-size:13px;pointer-events:none;';
    card.innerHTML = `<div style="font-weight:600;margin-bottom:6px;color:#1890ff;">📄 ${source}</div><div style="color:#555;line-height:1.6;max-height:160px;overflow-y:auto;">${preview}</div>`;
    document.body.appendChild(card);
    _citeHoverCard = card;
    const rect = el.getBoundingClientRect();
    let left = rect.left;
    if (left + 420 > window.innerWidth) left = window.innerWidth - 420;
    if (left < 8) left = 8;
    card.style.left = left + 'px';
    card.style.top = (rect.bottom + 8) + 'px';
  }

  function hideCiteHover() {
    if (_citeHoverCard) { _citeHoverCard.remove(); _citeHoverCard = null; }
  }

  async function togglePin(convId) {
    try {
      await API.request(`/api/conversations/${convId}/pin`, { method: 'PUT' });
      loadConversationList();
    } catch (e) { console.error('置顶失败:', e); }
  }

  async function editTags(convId) {
    const input = prompt('输入标签（多个用逗号分隔）：');
    if (input === null) return;
    const tags = input.split(/[,，]/).map(t => t.trim()).filter(Boolean);
    try {
      await API.request(`/api/conversations/${convId}/tags`, { method: 'PUT', body: { tags } });
      loadConversationList();
    } catch (e) { console.error('标签失败:', e); }
  }

  async function exportConv(convId) {
    try {
      const token = API.getToken();
      const resp = await fetch(`/api/conversations/${convId}/export`, {
        headers: { 'Authorization': `Bearer ${token}` },
      });
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = '对话导出.md'; a.click();
      URL.revokeObjectURL(url);
    } catch (e) { console.error('导出失败:', e); }
  }

  return { askQuestion, askPreset, newChat, feedback, loadConversationList, loadConversation, deleteConversation, reset, showCiteHover, hideCiteHover, togglePin, editTags, exportConv };
})();

Router.on('qa-chat', () => PageQA.loadConversationList());
