/**
 * 评测管理页面 — 评测集 + 评测运行
 */
const PageEval = (() => {
  let _datasets = [];
  let _currentDataset = null;
  let _currentRunId = null;
  let _pollTimer = null;

  // ─── 评测集管理 ─────────────────────────────

  async function loadDatasets() {
    try {
      _datasets = await API.get('/api/eval/datasets');
      renderDatasetTable();
    } catch (e) {
      console.error('加载评测集失败', e);
    }
  }

  function renderDatasetTable() {
    const tbody = document.getElementById('eval-ds-body');
    if (!_datasets.length) {
      tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:40px;color:#999;">暂无评测集，点击上方按钮生成</td></tr>';
      return;
    }
    const statusMap = {
      'generating': '<span class="tag tag-orange">生成中</span>',
      'ready': '<span class="tag tag-green">就绪</span>',
      'error': '<span class="tag tag-red">错误</span>',
    };
    tbody.innerHTML = _datasets.map(ds => `
      <tr>
        <td>${esc(ds.name)}</td>
        <td>${esc(ds.kb_name)}</td>
        <td>${ds.question_count}</td>
        <td>${statusMap[ds.status] || ds.status}</td>
        <td>${ds.created_at ? ds.created_at.slice(0, 16) : '-'}</td>
        <td>
          ${ds.status === 'ready' ? `<button class="btn btn-sm btn-primary" onclick="PageEval.viewQuestions('${ds.id}')">查看</button> ` : ''}
          ${ds.status === 'ready' ? `<button class="btn btn-sm btn-primary" onclick="PageEval.startRun('${ds.id}')">评测</button> ` : ''}
          <button class="btn btn-sm btn-danger" onclick="PageEval.deleteDataset('${ds.id}')">删除</button>
        </td>
      </tr>
    `).join('');
  }

  async function showGenerateModal() {
    // 加载知识库列表
    try {
      const kbs = await API.get('/api/knowledge-bases');
      const container = document.getElementById('eval-kb-checkboxes');
      container.innerHTML = kbs.map(kb => `
        <label style="display:flex;align-items:center;gap:8px;padding:6px 0;font-size:13px;">
          <input type="checkbox" value="${kb.id}" class="eval-kb-cb">
          ${esc(kb.name)} <span class="text-muted">(${kb.doc_count || 0} 文档)</span>
        </label>
      `).join('');
      UI.showModal('eval-generate');
    } catch (e) {
      UI.toast('加载知识库失败', 'error');
    }
  }

  async function doGenerate() {
    const checked = document.querySelectorAll('.eval-kb-cb:checked');
    const kbIds = Array.from(checked).map(cb => cb.value);
    const count = parseInt(document.getElementById('eval-gen-count').value) || 15;

    if (!kbIds.length) {
      UI.toast('请至少选择一个知识库', 'error');
      return;
    }

    try {
      const res = await API.post('/api/eval/generate', { kb_ids: kbIds, count: count });
      UI.hideModal();
      UI.toast(res.message || '已提交生成任务', 'success');
      // 轮询刷新
      startPolling();
    } catch (e) {
      UI.toast('提交失败: ' + (e.message || ''), 'error');
    }
  }

  async function deleteDataset(id) {
    if (!confirm('确定删除该评测集？所有问题和评测结果将一并删除。')) return;
    try {
      await API.del(`/api/eval/datasets/${id}`);
      UI.toast('已删除', 'success');
      loadDatasets();
    } catch (e) {
      UI.toast('删除失败', 'error');
    }
  }

  // ─── 问题管理 ─────────────────────────────

  async function viewQuestions(datasetId) {
    _currentDataset = datasetId;
    try {
      const questions = await API.get(`/api/eval/datasets/${datasetId}/questions`);
      renderQuestionTable(questions);
      UI.showModal('eval-questions');
    } catch (e) {
      UI.toast('加载问题失败', 'error');
    }
  }

  function renderQuestionTable(questions) {
    const tbody = document.getElementById('eval-q-body');
    const catMap = {
      'factual': '<span class="tag tag-blue">事实型</span>',
      'out_of_scope': '<span class="tag tag-red">超范围</span>',
      'multi_doc': '<span class="tag tag-purple">多文档</span>',
      'ambiguous': '<span class="tag tag-orange">歧义</span>',
      'false_premise': '<span class="tag tag-gray">错误前提</span>',
    };
    if (!questions.length) {
      tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;padding:30px;color:#999;">暂无问题</td></tr>';
      return;
    }
    tbody.innerHTML = questions.map((q, i) => `
      <tr>
        <td style="width:40px;text-align:center;">${i + 1}</td>
        <td style="max-width:400px;word-break:break-all;">${esc(q.question)}</td>
        <td>${catMap[q.category] || q.category}</td>
        <td style="max-width:250px;word-break:break-all;font-size:12px;color:#666;">${esc((q.expected_answer || '').slice(0, 100))}${(q.expected_answer || '').length > 100 ? '...' : ''}</td>
        <td>
          <button class="btn btn-sm" onclick="PageEval.editQuestion('${q.id}')">编辑</button>
          <button class="btn btn-sm btn-danger" onclick="PageEval.deleteQuestion('${q.id}')">删除</button>
        </td>
      </tr>
    `).join('');
  }

  let _editingQ = null;

  async function editQuestion(qId) {
    try {
      const questions = await API.get(`/api/eval/datasets/${_currentDataset}/questions`);
      const q = questions.find(x => x.id === qId);
      if (!q) return;
      _editingQ = q;
      document.getElementById('eval-qe-question').value = q.question;
      document.getElementById('eval-qe-answer').value = q.expected_answer;
      document.getElementById('eval-qe-category').value = q.category;
      UI.showModal('eval-qe-edit');
    } catch (e) {
      UI.toast('加载失败', 'error');
    }
  }

  async function saveQuestion() {
    if (!_editingQ) return;
    try {
      await API.post(`/api/eval/datasets/${_currentDataset}/questions/${_editingQ.id}`, {
        question: document.getElementById('eval-qe-question').value,
        expected_answer: document.getElementById('eval-qe-answer').value,
        category: document.getElementById('eval-qe-category').value,
      });
      UI.hideModal();
      UI.toast('已更新', 'success');
      viewQuestions(_currentDataset);
    } catch (e) {
      UI.toast('保存失败', 'error');
    }
  }

  async function deleteQuestion(qId) {
    if (!confirm('确定删除此问题？')) return;
    try {
      await API.del(`/api/eval/datasets/${_currentDataset}/questions/${qId}`);
      UI.toast('已删除', 'success');
      viewQuestions(_currentDataset);
      loadDatasets();
    } catch (e) {
      UI.toast('删除失败', 'error');
    }
  }

  // ─── 评测运行 ─────────────────────────────

  async function startRun(datasetId) {
    if (!confirm('确定启动评测？这将对每个问题执行检索+生成+评分，可能需要较长时间。')) return;
    try {
      const res = await API.post(`/api/eval/run/${datasetId}`);
      UI.toast(res.message || '评测已启动', 'success');
      _currentRunId = res.run_id;
      startPolling();
    } catch (e) {
      UI.toast('启动失败: ' + (e.message || ''), 'error');
    }
  }

  async function loadRuns() {
    try {
      const runs = await API.get('/api/eval/runs');
      renderRunTable(runs);
    } catch (e) {
      console.error('加载评测记录失败', e);
    }
  }

  function renderRunTable(runs) {
    const tbody = document.getElementById('eval-run-body');
    if (!runs.length) {
      tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:40px;color:#999;">暂无评测记录</td></tr>';
      return;
    }
    const statusMap = {
      'running': '<span class="tag tag-orange">运行中</span>',
      'completed': '<span class="tag tag-green">完成</span>',
      'error': '<span class="tag tag-red">错误</span>',
    };
    tbody.innerHTML = runs.map(r => `
      <tr>
        <td>${r.started_at ? r.started_at.slice(0, 16) : '-'}</td>
        <td>${r.total}</td>
        <td><span class="tag tag-green">${r.passed} 通过</span></td>
        <td><span class="tag tag-red">${r.failed} 未通过</span></td>
        <td>${(r.avg_score * 100).toFixed(1)}%</td>
        <td>${statusMap[r.status] || r.status}</td>
        <td>
          ${r.status === 'completed' ? `<button class="btn btn-sm btn-primary" onclick="PageEval.viewResults('${r.id}')">查看结果</button>` : ''}
        </td>
      </tr>
    `).join('');
  }

  // ─── 评测结果 ─────────────────────────────

  async function viewResults(runId) {
    try {
      const data = await API.get(`/api/eval/runs/${runId}/results`);
      renderResults(data);
      UI.showModal('eval-results');
    } catch (e) {
      UI.toast('加载结果失败', 'error');
    }
  }

  function renderResults(data) {
    const { run, category_stats, dimension_scores, results } = data;

    // 概览
    document.getElementById('eval-res-overview').innerHTML = `
      <div class="stats-row" style="margin-bottom:16px;">
        <div class="stat-card"><div class="label">总题数</div><div class="value">${run.total}</div></div>
        <div class="stat-card"><div class="label">通过</div><div class="value" style="color:#52c41a;">${run.passed}</div></div>
        <div class="stat-card"><div class="label">未通过</div><div class="value" style="color:#ff4d4f;">${run.failed}</div></div>
        <div class="stat-card"><div class="label">平均分</div><div class="value">${(run.avg_score * 100).toFixed(1)}%</div></div>
      </div>
    `;

    // 维度分数
    const dimLabels = {
      'retrieval_precision': '检索精确率',
      'retrieval_recall': '检索召回率',
      'retrieval_ranking': '排序质量',
      'gen_groundedness': '忠实度',
      'gen_relevance': '相关性',
      'gen_completeness': '完整性',
      'refuse_accuracy': '拒答准确性',
      'currency_handling': '时效性',
      'multi_hop': '多跳推理',
    };
    let dimHtml = '<h4 class="mb-12">📊 多维度评分</h4><div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;">';
    for (const [dim, score] of Object.entries(dimension_scores)) {
      const pct = (score * 100).toFixed(1);
      const color = score >= 0.7 ? '#52c41a' : score >= 0.4 ? '#faad14' : '#ff4d4f';
      dimHtml += `
        <div style="padding:10px;background:#f8fafc;border-radius:6px;">
          <div style="font-size:12px;color:#666;">${dimLabels[dim] || dim}</div>
          <div style="font-size:18px;font-weight:600;color:${color};">${pct}%</div>
          <div style="height:4px;background:#e2e8f0;border-radius:2px;margin-top:4px;">
            <div style="height:100%;width:${pct}%;background:${color};border-radius:2px;"></div>
          </div>
        </div>
      `;
    }
    dimHtml += '</div>';
    document.getElementById('eval-res-dimensions').innerHTML = dimHtml;

    // 分类统计
    const catMap = {
      'factual': '事实型',
      'out_of_scope': '超范围',
      'multi_doc': '多文档',
      'ambiguous': '歧义',
      'false_premise': '错误前提',
    };
    let catHtml = '<h4 class="mb-12">📂 分类统计</h4><table><tr><th>类型</th><th>总数</th><th>通过</th><th>通过率</th><th>平均分</th></tr>';
    for (const [cat, stat] of Object.entries(category_stats)) {
      const rate = stat.total > 0 ? ((stat.passed / stat.total) * 100).toFixed(1) : '0.0';
      catHtml += `<tr>
        <td>${catMap[cat] || cat}</td>
        <td>${stat.total}</td>
        <td>${stat.passed}</td>
        <td>${rate}%</td>
        <td>${(stat.avg_score * 100).toFixed(1)}%</td>
      </tr>`;
    }
    catHtml += '</table>';
    document.getElementById('eval-res-categories').innerHTML = catHtml;

    // 详细结果
    let detailHtml = '<h4 class="mb-12">📝 逐题详情</h4>';
    results.forEach((r, i) => {
      const passedIcon = r.passed ? '✅' : '❌';
      const scoreColor = r.avg_score >= 0.7 ? '#52c41a' : r.avg_score >= 0.4 ? '#faad14' : '#ff4d4f';
      detailHtml += `
        <div style="border:1px solid #e2e8f0;border-radius:8px;margin-bottom:12px;overflow:hidden;">
          <div style="padding:12px 16px;background:#f8fafc;display:flex;justify-content:space-between;align-items:center;cursor:pointer;" onclick="this.nextElementSibling.style.display=this.nextElementSibling.style.display==='none'?'block':'none'">
            <div>
              ${passedIcon} <strong>Q${i + 1}</strong>
              <span class="tag tag-${{factual:'blue',out_of_scope:'red',multi_doc:'purple',ambiguous:'orange',false_premise:'gray'}[r.category] || 'blue'}">${catMap[r.category] || r.category}</span>
              ${esc(r.question.slice(0, 80))}${r.question.length > 80 ? '...' : ''}
            </div>
            <div style="font-weight:600;color:${scoreColor};">${(r.avg_score * 100).toFixed(1)}%</div>
          </div>
          <div style="display:none;padding:16px;border-top:1px solid #e2e8f0;">
            <div style="margin-bottom:12px;">
              <div style="font-size:12px;color:#999;margin-bottom:4px;">问题</div>
              <div style="font-size:14px;">${esc(r.question)}</div>
            </div>
            <div style="margin-bottom:12px;">
              <div style="font-size:12px;color:#999;margin-bottom:4px;">期望答案</div>
              <div style="font-size:13px;color:#666;">${esc(r.expected_answer || '无')}</div>
            </div>
            <div style="margin-bottom:12px;">
              <div style="font-size:12px;color:#999;margin-bottom:4px;">系统回答</div>
              <div style="font-size:13px;background:#f0f7ff;padding:10px;border-radius:4px;">${esc(r.actual_answer)}</div>
            </div>
            <div style="margin-bottom:12px;">
              <div style="font-size:12px;color:#999;margin-bottom:4px;">评测理由</div>
              <div style="font-size:13px;color:#666;">${esc(r.reasoning)}</div>
            </div>
            <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:6px;">
              ${Object.entries(r.scores).map(([dim, score]) => {
                const pct = (score * 100).toFixed(0);
                const color = score >= 0.7 ? '#52c41a' : score >= 0.4 ? '#faad14' : '#ff4d4f';
                return `<div style="padding:6px 10px;background:#f8fafc;border-radius:4px;font-size:12px;">
                  <span style="color:#999;">${dimLabels[dim] || dim}</span>
                  <span style="float:right;font-weight:600;color:${color};">${pct}%</span>
                </div>`;
              }).join('')}
            </div>
            <div style="margin-top:8px;font-size:12px;color:#999;">延迟: ${r.latency_ms}ms</div>
          </div>
        </div>
      `;
    });
    document.getElementById('eval-res-details').innerHTML = detailHtml;
  }

  // ─── 轮询刷新 ─────────────────────────────

  function startPolling() {
    if (_pollTimer) clearInterval(_pollTimer);
    let count = 0;
    _pollTimer = setInterval(async () => {
      count++;
      await loadDatasets();
      await loadRuns();
      // 检查是否还有 generating 的
      const hasGenerating = _datasets.some(d => d.status === 'generating');
      if (!hasGenerating && count > 2) {
        clearInterval(_pollTimer);
        _pollTimer = null;
      }
      if (count > 60) { // 最多轮询 2 分钟
        clearInterval(_pollTimer);
        _pollTimer = null;
      }
    }, 2000);
  }

  // ─── 工具函数 ─────────────────────────────

  function esc(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  // ─── 初始化 ─────────────────────────────

  function init() {
    loadDatasets();
    loadRuns();
  }

  // ─── 评测 Prompt 管理 ─────────────────────────────

  let _evalPrompts = {};

  async function loadEvalPrompts() {
    try {
      _evalPrompts = await API.get('/api/config/eval-prompts');
      fillEvalPromptFields();
    } catch (e) {
      console.error('加载评测 Prompt 失败', e);
    }
  }

  function fillEvalPromptFields() {
    const gen = _evalPrompts.eval_generate || {};
    document.getElementById('eval-prompt-gen-system').value = gen.system || '';
    document.getElementById('eval-prompt-gen-user').value = gen.user || '';
    const judge = _evalPrompts.eval_judge || {};
    document.getElementById('eval-prompt-judge-system').value = judge.system || '';
    document.getElementById('eval-prompt-judge-user').value = judge.user || '';
  }

  function switchEvalPrompt() {
    const val = document.getElementById('eval-prompt-selector').value;
    document.getElementById('eval-prompt-gen-panel').style.display = val === 'eval_generate' ? '' : 'none';
    document.getElementById('eval-prompt-judge-panel').style.display = val === 'eval_judge' ? '' : 'none';
  }

  async function saveEvalPrompts() {
    const data = {
      eval_generate: {
        name: '评测集生成 Prompt',
        description: '从知识库文档块生成多类型评测问题',
        system: document.getElementById('eval-prompt-gen-system').value,
        user: document.getElementById('eval-prompt-gen-user').value,
      },
      eval_judge: {
        name: '评测打分 Prompt',
        description: 'LLM-as-Judge 对问答结果多维度评分',
        system: document.getElementById('eval-prompt-judge-system').value,
        user: document.getElementById('eval-prompt-judge-user').value,
      },
    };
    try {
      await API.post('/api/config/eval-prompts', data);
      UI.toast('评测 Prompt 已保存', 'success');
    } catch (e) {
      UI.toast('保存失败', 'error');
    }
  }

  return {
    init,
    loadDatasets,
    showGenerateModal,
    doGenerate,
    deleteDataset,
    viewQuestions,
    editQuestion,
    saveQuestion,
    deleteQuestion,
    startRun,
    loadRuns,
    viewResults,
    loadEvalPrompts,
    switchEvalPrompt,
    saveEvalPrompts,
  };
})();

Router.on('evaluation', () => PageEval.init());
