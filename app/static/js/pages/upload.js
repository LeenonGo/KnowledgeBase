/**
 * 文档上传页
 */
const PageUpload = (() => {
  let selectedFile = null;
  let lastUploadedFile = null;

  function init() {
    const zone = document.getElementById('upload-zone');
    if (!zone) return;
    zone.onclick = () => document.getElementById('file-input').click();
    zone.ondragover = e => { e.preventDefault(); zone.style.borderColor = '#1890ff'; };
    zone.ondragleave = () => zone.style.borderColor = '#d9d9d9';
    zone.ondrop = e => {
      e.preventDefault(); zone.style.borderColor = '#d9d9d9';
      if (e.dataTransfer.files[0]) handleFile(e.dataTransfer.files[0]);
    };
    document.getElementById('file-input').onchange = e => {
      if (e.target.files[0]) handleFile(e.target.files[0]);
    };
  }

  function handleFile(file) {
    selectedFile = file;
    document.getElementById('selected-files').innerHTML =
      `<div style="padding:12px;background:#e6f7ff;border-radius:6px;display:flex;justify-content:space-between;align-items:center;">
        <span>📎 ${file.name}</span><span class="text-muted">${(file.size/1024/1024).toFixed(2)} MB</span></div>`;
    document.getElementById('step1-next').disabled = false;
  }

  function toggleChunkConfig(type) {
    document.getElementById('chunk-config-size').style.display = type !== 'structural' ? 'block' : 'none';
    document.getElementById('chunk-config-structural').style.display = type === 'structural' ? 'block' : 'none';
    const hint = document.getElementById('chunk-config-hint');
    if (type === 'fixed') hint.textContent = '按固定字符数硬切，支持重叠';
    else if (type === 'semantic') hint.textContent = '按句子边界拆分，保证语义完整，块间按完整句子重叠';
  }

  function goStep(step) {
    ['upload-step-1','upload-step-2','upload-step-3'].forEach(id =>
      document.getElementById(id).style.display = 'none');
    for (let i = 1; i <= 3; i++) {
      const el = document.getElementById('step-' + i);
      el.classList.remove('active', 'done');
      if (i < step) el.classList.add('done');
      if (i === step) el.classList.add('active');
    }
    document.getElementById('upload-step-' + step).style.display = 'block';
    if (step === 2 && selectedFile) {
      document.getElementById('step2-file-info').innerHTML =
        `<strong>📎 ${selectedFile.name}</strong> <span class="text-muted">${(selectedFile.size/1024/1024).toFixed(2)} MB</span>`;
    }
  }

  async function doUpload() {
    if (!selectedFile) return;

    const kbId = PageKB.getCurrentKbId();
    if (!kbId) {
      alert('请先选择一个知识库');
      return;
    }

    // 检查同名文件是否已存在
    try {
      const docs = await API.request(`/api/documents?kb_id=${kbId}&page=1&page_size=100`);
      const existing = (docs.items || []).find(d => d.filename === selectedFile.name);
      if (existing) {
        if (!confirm(`知识库中已存在同名文件「${selectedFile.name}」（${existing.chunks} 块）。

确定要用新文件替换旧版本吗？旧版本的分块数据将被删除。`)) {
          return;
        }
      }
    } catch (e) {
      console.error('检查同名文件失败:', e);
    }

    goStep(3);
    document.getElementById('upload-progress').style.display = 'block';
    document.getElementById('upload-result').style.display = 'none';
    document.getElementById('upload-actions').style.display = 'none';
    document.getElementById('upload-spinner').style.display = 'inline-block';
    document.getElementById('upload-status-text').textContent = '正在上传并处理...';
    document.getElementById('upload-progress-bar').style.width = '0%';
    document.getElementById('upload-progress-text').textContent = '0%';

    lastUploadedFile = selectedFile.name;
    const fd = new FormData();
    fd.append('file', selectedFile);
    fd.append('kb_id', kbId);
    const strategy = document.getElementById('chunk-strategy').value || 'semantic';
    fd.append('chunk_strategy', strategy);
    if (strategy === 'structural') {
      fd.append('chunk_size', document.getElementById('structural-chunk-size').value || '1024');
      fd.append('heading_level', document.getElementById('structural-heading-level').value || '2');
    } else {
      fd.append('chunk_size', document.getElementById('chunk-size').value || '512');
      fd.append('chunk_overlap', document.getElementById('chunk-overlap').value || '64');
    }

    try {
      const data = await API.upload(fd, pct => {
        const displayPct = Math.min(pct, 100);
        document.getElementById('upload-progress-bar').style.width = displayPct + '%';
        document.getElementById('upload-progress-text').textContent = displayPct + '%';
      });

      // PDF 文件：异步处理，轮询进度
      if (data.task_id) {
        document.getElementById('upload-status-text').textContent =
          `⏳ OCR 处理中: 0/${data.total_pages} 页 (0%)`;
        await _pollProgress(data.task_id, data.total_pages);
      } else {
        // 非 PDF：直接完成
        _showUploadResult(data);
      }
    } catch (e) {
      document.getElementById('upload-spinner').style.display = 'none';
      document.getElementById('upload-status-text').textContent = '❌ 上传失败';
      document.getElementById('upload-result').innerHTML =
        `<div style="padding:16px;background:#fff1f0;border-radius:8px;color:#cf1322;">${e.message}</div>`;
      document.getElementById('upload-result').style.display = 'block';
    }
  }

  async function _pollProgress(taskId, totalPages) {
    const bar = document.getElementById('upload-progress-bar');
    const text = document.getElementById('upload-progress-text');
    const status = document.getElementById('upload-status-text');

    while (true) {
      await new Promise(r => setTimeout(r, 1000));
      try {
        const resp = await fetch(`/api/upload/progress/${taskId}`, {
          headers: { 'Authorization': 'Bearer ' + API.getToken() },
        });
        if (!resp.ok) throw new Error('进度查询失败');
        const task = await resp.json();

        const pct = task.percent || 0;
        bar.style.width = pct + '%';
        text.textContent = pct + '%';

        if (task.stage === 'processing' && task.current_page) {
          status.textContent = `⏳ OCR 处理中: 第 ${task.current_page}/${task.total_pages} 页 (${pct}%)`;
        } else if (task.stage === 'indexing') {
          status.textContent = '⏳ 写入向量库...';
        } else {
          status.textContent = task.message || '处理中...';
        }

        if (task.done) {
          if (task.error) {
            document.getElementById('upload-spinner').style.display = 'none';
            status.textContent = '❌ 处理失败';
            document.getElementById('upload-result').innerHTML =
              `<div style="padding:16px;background:#fff1f0;border-radius:8px;color:#cf1322;">${task.error}</div>`;
            document.getElementById('upload-result').style.display = 'block';
          } else {
            _showUploadResult(task.result);
          }
          return;
        }
      } catch (e) {
        // 轮询出错，继续重试
        console.error('进度轮询错误:', e);
      }
    }
  }

  function _showUploadResult(data) {
    document.getElementById('upload-spinner').style.display = 'none';
    document.getElementById('upload-status-text').textContent = data.warnings ? '⚠️ 上传完成（有警告）' : '✅ 上传完成';
    document.getElementById('upload-progress-bar').style.width = '100%';
    document.getElementById('upload-progress-text').textContent = '100%';

    let resultHtml = `<div style="padding:16px;border-radius:8px;font-size:15px;${data.warnings ? 'background:#fff7ed;color:#9a3412;' : 'background:#ecfdf5;color:#065f46;'}">`
      + `<div style="font-weight:600;margin-bottom:8px;">${data.warnings ? '⚠️' : '✅'} ${data.filename}</div>`
      + `<div>${data.message}</div>`;
    if (data.warnings && data.warnings.length) {
      resultHtml += '<ul style="margin:8px 0 0;padding-left:20px;">'
        + data.warnings.map(w => `<li>${w}</li>`).join('')
        + '</ul>';
    }
    resultHtml += '</div>';

    document.getElementById('upload-result').innerHTML = resultHtml;
    document.getElementById('upload-result').style.display = 'block';
    document.getElementById('upload-actions').style.display = 'flex';
    selectedFile = null;
    PageKB.loadKBDocs();
  }

  function reset() {
    selectedFile = null;
    lastUploadedFile = null;
    document.getElementById('selected-files').innerHTML = '';
    document.getElementById('step1-next').disabled = true;
    document.getElementById('file-input').value = '';
    document.getElementById('upload-result').innerHTML = '';
    document.getElementById('upload-result').style.display = 'none';
    document.getElementById('upload-actions').style.display = 'none';
    document.getElementById('upload-progress-bar').style.width = '0%';
    document.getElementById('upload-progress-text').textContent = '0%';
    goStep(1);
  }

  function viewLastChunks() {
    if (lastUploadedFile) PageChunks.view(lastUploadedFile);
  }

  return { init, toggleChunkConfig, goStep, doUpload, reset, viewLastChunks };
})();
