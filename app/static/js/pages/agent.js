/**
 * Agent 工作台 — 自主推理 + 工具调用
 */
const PageAgent = (() => {
  let currentConvId = null;

  async function ensureConversation() {
    if (currentConvId) return currentConvId;
    try {
      const data = await API.request('/api/conversations', {
        method: 'POST', body: { title: '新对话', type: 'agent' },
      });
      currentConvId = data.id;
      return currentConvId;
    } catch (e) {
      console.error('创建对话失败:', e);
      return null;
    }
  }

  async function askQuestion() {
    const input = document.getElementById('agent-input');
    const question = input.value.trim();
    if (!question) return;
    input.disabled = true;
    const sendBtn = document.getElementById('agent-send-btn');
    sendBtn.disabled = true;
    sendBtn.textContent = '推理中...';
    addMessage('user', question);
    input.value = '';
    const loadingId = addMessage('loading', 'Agent 正在分析任务并调用工具，请稍候...');

    try {
      const convId = await ensureConversation();

      if (convId) {
        await API.request(`/api/conversations/${convId}/turns`, {
          method: 'POST', body: { role: 'user', content: question },
        });
      }

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

      const body = {
        question, top_k: 10, use_hybrid: true, conv_id: convId,
        use_reranker: false, use_agent: true,
        use_rewrite: false, use_polish: false,
        use_web_search: document.getElementById('agent-web-search')?.checked ?? true,
      };

      removeMessage(loadingId);

      // ── 创建消息结构：推理链 和 回答 分开 ──
      const msgId = addMessage('assistant', '');
      const msgEl = document.getElementById(msgId);
      const bubble = msgEl?.querySelector('.bubble');

      // 推理链容器
      const chainWrap = document.createElement('div');
      chainWrap.className = 'agent-chain';
      chainWrap.id = 'agent-chain-live';
      chainWrap.innerHTML = `<div class="agent-chain-header" onclick="this.parentElement.classList.toggle('collapsed')">🧠 推理过程 <span class="chain-toggle">▼</span></div><div class="agent-chain-body"></div>`;
      bubble.appendChild(chainWrap);

      // 回答容器（独立于推理链）
      const answerWrap = document.createElement('div');
      answerWrap.className = 'agent-answer';
      answerWrap.innerHTML = '<div class="agent-answer-text"></div>';
      bubble.appendChild(answerWrap);
      const answerText = answerWrap.querySelector('.agent-answer-text');

      // 来源标签行
      const sourcesEl = document.createElement('div');
      sourcesEl.className = 'source-tags-row';
      bubble.appendChild(sourcesEl);

      const startTime = Date.now();
      const traceData = [];
      const showTrace = document.getElementById('agent-show-trace')?.checked ?? false;
      const detectedSources = new Set();

      try {
        const resp = await fetch('/api/query/agent/stream', {
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
        let stepCount = 0;

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

            if (eventType === 'plan') {
              // 显示规划结果
              const planEl = document.createElement('div');
              planEl.className = 'agent-plan';
              if (data.need_plan && data.tasks?.length) {
                const taskList = data.tasks.map(t =>
                  `<div class="plan-task" id="plan-task-${t.id}"><span class="plan-task-status">⏳</span><span class="plan-task-desc">子任务 ${t.id}: ${UI.escapeHtml(t.description)}</span></div>`
                ).join('');
                planEl.innerHTML = `<div class="plan-header">📋 任务规划 <span class="plan-reason">${UI.escapeHtml(data.reason)}</span></div><div class="plan-tasks">${taskList}</div>`;
              } else {
                planEl.innerHTML = `<div class="plan-header">📋 问题较简单，直接执行检索问答</div>`;
              }
              chainWrap.querySelector('.agent-chain-body').appendChild(planEl);
              traceData.push({ type: 'plan', data, time: Date.now() - startTime });
            } else if (eventType === 'subtask_start') {
              // 子任务开始标记
              const taskEl = document.getElementById(`plan-task-${data.task_id}`);
              if (taskEl) {
                taskEl.querySelector('.plan-task-status').textContent = '🔄';
                taskEl.classList.add('active');
              }
              // 在推理链中插入子任务分隔
              const sepEl = document.createElement('div');
              sepEl.className = 'chain-subtask-sep';
              sepEl.innerHTML = `<span>▶ 子任务 ${data.task_id}: ${UI.escapeHtml(data.description)}</span>`;
              chainWrap.querySelector('.agent-chain-body').appendChild(sepEl);
            } else if (eventType === 'subtask_done') {
              // 子任务完成标记
              const taskEl = document.getElementById(`plan-task-${data.task_id}`);
              if (taskEl) {
                taskEl.querySelector('.plan-task-status').textContent = '✅';
                taskEl.classList.remove('active');
                taskEl.classList.add('done');
              }
              traceData.push({ type: 'subtask_done', task_id: data.task_id, time: Date.now() - startTime });
            } else if (eventType === 'thought') {
              stepCount++;
              const chainBody = chainWrap.querySelector('.agent-chain-body');
              const stepEl = document.createElement('div');
              stepEl.className = 'chain-step chain-thought';
              stepEl.innerHTML = `<span class="chain-icon">💭</span><span class="chain-label">思考 Step ${data.step}</span><div class="chain-content">${data.content}</div>`;
              chainBody.appendChild(stepEl);
              traceData.push({ type: 'thought', step: data.step, content: data.content, time: Date.now() - startTime });
            } else if (eventType === 'action') {
              const chainBody = chainWrap.querySelector('.agent-chain-body');
              const stepEl = document.createElement('div');
              stepEl.className = 'chain-step chain-action';
              const toolName = data.tool || 'unknown';
              const toolIcon = { search_kb: '🔍', list_kb: '📂', get_doc_content: '📄', list_docs: '📋', web_search: '🌐' }[toolName] || '⚡';
              stepEl.innerHTML = `<span class="chain-icon">${toolIcon}</span><span class="chain-label">调用 ${toolName}</span><div class="chain-content"><code>${UI.escapeHtml(JSON.stringify(data.arguments, null, 2))}</code></div>`;
              chainBody.appendChild(stepEl);
              traceData.push({ type: 'action', tool: toolName, arguments: data.arguments, time: Date.now() - startTime });
            } else if (eventType === 'observe') {
              const chainBody = chainWrap.querySelector('.agent-chain-body');
              const stepEl = document.createElement('div');
              stepEl.className = 'chain-step chain-observe';
              const obsContent = (data.content || '').substring(0, 500);
              stepEl.innerHTML = `<span class="chain-icon">👁️</span><span class="chain-label">观察</span><div class="chain-content">${UI.escapeHtml(obsContent)}</div>`;
              chainBody.appendChild(stepEl);
              traceData.push({ type: 'observe', content: data.content, time: Date.now() - startTime });
            } else if (eventType === 'answer') {
              assistantContent = data.content || '';
              finalSources = data.sources || [];
              if (data.citations) finalCitations = data.citations;
              // 渲染回答（Markdown），不碰推理链
              const _chartData = UI.extractCharts(assistantContent); answerText.innerHTML = UI.md2html(_chartData.text); UI.renderCharts(answerText, _chartData.charts);
              if (finalSources.length) {
                finalSources.forEach(s => {
                  if (!detectedSources.has(s)) {
                    detectedSources.add(s);
                    const tag = document.createElement('span');
                    tag.className = 'source-tag';
                    tag.textContent = '📎 ' + s;
                    sourcesEl.appendChild(tag);
                  }
                });
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
              answerText.textContent = assistantContent;
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
          if (assistantContent) { const _chartData = UI.extractCharts(assistantContent); answerText.innerHTML = UI.md2html(_chartData.text); UI.renderCharts(answerText, _chartData.charts); }
        }

        const latency = Date.now() - startTime;
        const latencySec = (latency / 1000).toFixed(1);

        // 渲染引用标注 [C1][C2]
        if (finalCitations.length && answerText) {
          const citeMap = {};
          finalCitations.forEach(c => { citeMap[c.index] = c; });
          let html = answerText.innerHTML;
          html = html.replace(/\[C(\d+)\]/g, (match, num) => {
            const cite = citeMap[parseInt(num)];
            if (!cite) return match;
            const preview = (cite.text_preview || cite.text || '').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/\n/g, ' ');
            const source = (cite.source || '').replace(/"/g, '&quot;');
            return `<sup class="cite-ref" data-cite-source="${source}" data-cite-preview="${preview}" onmouseenter="PageAgent.showCiteHover(this, event)" onmouseleave="PageAgent.hideCiteHover()">[${num}]</sup>`;
          });
          answerText.innerHTML = html;
        }

        // 结束时补充来源
        if (!detectedSources.size && finalSources.length) {
          finalSources.forEach(s => {
            const tag = document.createElement('span');
            tag.className = 'source-tag';
            tag.textContent = '📎 ' + s;
            sourcesEl.appendChild(tag);
          });
        }

        // 追加耗时 + 步数
        const metaEl = document.createElement('div');
        metaEl.style.cssText = 'font-size:11px;color:#bbb;margin-top:4px;display:flex;gap:12px;';
        metaEl.innerHTML = `<span>⏱ ${latencySec}s</span><span>🔄 ${stepCount} 步推理</span>`;
        answerWrap.appendChild(metaEl);

        // Trace 展示
        if (showTrace && traceData.length) {
          const traceEl = document.createElement('div');
          traceEl.className = 'agent-trace-panel';
          traceEl.innerHTML = `<div class="agent-trace-header" onclick="this.parentElement.classList.toggle('collapsed')">🔍 全链路 Trace <span class="chain-toggle">▼</span></div><div class="agent-trace-body">${traceData.map(t => {
            const ts = (t.time / 1000).toFixed(2) + 's';
            if (t.type === 'thought') return `<div class="trace-span"><span class="trace-time">${ts}</span><span class="trace-type trace-thought">💭 Thought</span><span class="trace-detail">${UI.escapeHtml(t.content.substring(0, 80))}...</span></div>`;
            if (t.type === 'action') return `<div class="trace-span"><span class="trace-time">${ts}</span><span class="trace-type trace-action">⚡ ${t.tool}</span><span class="trace-detail">${UI.escapeHtml(JSON.stringify(t.arguments).substring(0, 80))}</span></div>`;
            return `<div class="trace-span"><span class="trace-time">${ts}</span><span class="trace-type trace-observe">👁 Observe</span><span class="trace-detail">${UI.escapeHtml((t.content || '').substring(0, 80))}...</span></div>`;
          }).join('')}</div>`;
          answerWrap.appendChild(traceEl);
        }

        // 无内容提示
        if (!assistantContent) {
          assistantContent = 'Agent 未返回回答内容';
          answerText.textContent = assistantContent;
        }

        // 推理链自动折叠（回答出来后）
        if (stepCount > 0) {
          chainWrap.classList.add('collapsed');
        }

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
        answerText.textContent = '❌ 请求失败：' + e.message;
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
    const id = 'agent-msg-' + Date.now();
    const div = document.getElementById('agent-messages');
    const empty = div.querySelector('div[style*="text-align:center"]');
    if (empty) empty.remove();
    const el = document.createElement('div');
    el.className = 'message ' + role;
    el.id = id;
    const avatar = role === 'user' ? '你' : 'AI';
    const bg = role === 'user' ? '#1890ff' : '#f5f5f5';
    const color = role === 'user' ? '#fff' : '#333';
    let html = role === 'loading'
      ? '<div style="color:#999;">⏳ Agent 正在推理...</div>'
      : (role === 'assistant' ? UI.md2html(content) : content);
    if (role !== 'user' && role !== 'loading') {
      html += `<div class="chat-actions">
        <button class="feedback-btn" title="👍" onclick="PageAgent.feedback(this.closest('.message'),'up')">👍</button>
        <button class="feedback-btn" title="👎" onclick="PageAgent.feedback(this.closest('.message'),'down')">👎</button>
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
    document.getElementById('agent-input').value = q;
    askQuestion();
  }

  async function newChat() {
    currentConvId = null;
    loadConversationList();
    document.getElementById('agent-messages').innerHTML =
      `<div style="text-align:center;padding:60px 20px;color:#999;" id="agent-empty-state">
        <div style="font-size:48px;margin-bottom:16px;">🧠</div>
        <div style="font-size:16px;">输入任务开始推理</div>
        <div style="font-size:13px;margin-top:8px;">Agent 会自主调用工具、检索知识库、联网搜索来完成任务</div>
        <div style="margin-top:24px;display:flex;flex-direction:column;gap:10px;align-items:center;">
          <button class="btn" style="max-width:500px;width:100%;justify-content:flex-start;text-align:left;font-size:13px;padding:10px 16px;" onclick="PageAgent.askPreset(this)">📋 对比各知识库的核心功能模块</button>
          <button class="btn" style="max-width:500px;width:100%;justify-content:flex-start;text-align:left;font-size:13px;padding:10px 16px;" onclick="PageAgent.askPreset(this)">📋 总结所有文档中关于部署的关键信息</button>
          <button class="btn" style="max-width:500px;width:100%;justify-content:flex-start;text-align:left;font-size:13px;padding:10px 16px;" onclick="PageAgent.askPreset(this)">📋 根据知识库内容帮我写一份技术方案</button>
        </div></div>`;
  }

  async function loadConversationList() {
    try {
      const convs = await API.request('/api/conversations?conv_type=agent');
      const list = document.getElementById('agent-chat-list');
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
          <div class="title" onclick="PageAgent.loadConversation('${c.id}')">${pinIcon} ${c.title || '新对话'}</div>
          ${tags ? `<div class="conv-tags-row">${tags}</div>` : ''}
          <div class="flex-between" style="margin-top:2px;">
            <span class="meta">${time}</span>
            <div class="conv-actions">
              <span class="conv-action-btn" onclick="event.stopPropagation();PageAgent.togglePin('${c.id}')" title="${c.is_pinned ? '取消置顶' : '置顶'}">${c.is_pinned ? '📍' : '📌'}</span>
              <span class="conv-action-btn" onclick="event.stopPropagation();PageAgent.editTags('${c.id}')" title="标签">🏷️</span>
              <span class="conv-action-btn" onclick="event.stopPropagation();PageAgent.exportConv('${c.id}')" title="导出">📥</span>
              <span class="conv-action-btn" onclick="event.stopPropagation();PageAgent.deleteConversation('${c.id}')" title="删除">🗑️</span>
            </div>
          </div>
        </div>`;
      }).join('');
    } catch {}
  }

  async function loadConversation(convId) {
    currentConvId = convId;
    try {
      const data = await API.request(`/api/conversations/${convId}/turns`);
      const div = document.getElementById('agent-messages');
      div.innerHTML = '';
      for (const t of (data.turns || [])) {
        const msgId = addMessage(t.role, t.content);
        if (t.role === 'assistant' && t.id) {
          const msgEl = document.getElementById(msgId);
          if (msgEl) msgEl.dataset.turnId = t.id;
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
    if (!confirm('确认删除该对话？')) return;
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

  let _citeHoverCard = null;

  function showCiteHover(el, e) {
    hideCiteHover();
    const source = el.getAttribute('data-cite-source') || '';
    const preview = el.getAttribute('data-cite-preview') || '';
    if (!source && !preview) return;
    const card = document.createElement('div');
    card.id = 'cite-hover-card';
    card.style.cssText = 'position:fixed;z-index:9999;background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:14px 16px;box-shadow:0 4px 20px rgba(0,0,0,.18);max-width:400px;min-width:240px;font-size:13px;pointer-events:none;';
    card.innerHTML = `<div style="font-weight:600;margin-bottom:6px;color:#1890ff;">📄 ${UI.escapeHtml(source)}</div><div style="color:#555;line-height:1.6;max-height:160px;overflow-y:auto;">${UI.escapeHtml(preview)}</div>`;
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

  return { askQuestion, askPreset, newChat, feedback, loadConversationList, loadConversation, deleteConversation, showCiteHover, hideCiteHover, togglePin, editTags, exportConv };
})();

Router.on('agent-ws', () => PageAgent.loadConversationList());
