/**
 * SQL 分析助手 — 自然语言查询电商数据库
 */
const PageSQL = (() => {
  let queryHistory = [];
  let queryCount = 0;

  const QUICK_QUESTIONS = [
    '本月各品类销售额是多少？',
    '消费金额 Top10 客户是谁？',
    '各城市的订单量排名',
    'VIP客户 vs 普通客户的平均客单价',
    '最近7天每日GMV趋势',
    '退货率最高的品类',
  ];

  function init() {
    var quickWrap = document.getElementById('sql-quick-questions');
    if (quickWrap) {
      quickWrap.innerHTML = QUICK_QUESTIONS.map(function(q) {
        var label = q.length > 14 ? q.slice(0, 14) + '\u2026' : q;
        return '<button class="btn btn-sm btn-outline" onclick="PageSQL.askQuick(\'' + q.replace(/'/g, "\\'") + '\')">' + UI.escapeHtml(label) + '</button>';
      }).join('');
    }
    var input = document.getElementById('sql-input');
    if (input) {
      input.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); askQuestion(); }
      });
    }
  }

  function askQuick(question) {
    document.getElementById('sql-input').value = question;
    askQuestion();
  }

  async function askQuestion() {
    var input = document.getElementById('sql-input');
    var question = input.value.trim();
    if (!question) return;

    input.disabled = true;
    var sendBtn = document.getElementById('sql-send-btn');
    if (sendBtn) { sendBtn.disabled = true; sendBtn.textContent = '\u67e5\u8be2\u4e2d...'; }

    queryCount++;
    var blockId = 'sql-block-' + queryCount;

    var container = document.getElementById('sql-results');
    var block = document.createElement('div');
    block.className = 'sql-query-block';
    block.id = blockId;
    block.innerHTML =
      '<div class="sql-query-header">' +
        '<span class="sql-query-num">\u67e5\u8be2 #' + queryCount + '</span>' +
        '<span class="sql-query-text">' + UI.escapeHtml(question) + '</span>' +
        '<span class="sql-query-time" id="' + blockId + '-time"></span>' +
      '</div>' +
      '<div class="sql-sql-section" id="' + blockId + '-sql" style="display:none">' +
        '<div class="sql-section-header"><span>\ud83d\udcdd \u751f\u6210\u7684 SQL</span>' +
          '<div>' +
            '<button class="btn btn-xs" onclick="PageSQL.copySQL(\'' + blockId + '\')">\ud83d\udccb \u590d\u5236</button> ' +
            '<button class="btn btn-xs" onclick="PageSQL.toggleEdit(\'' + blockId + '\')">\u270f\ufe0f \u7f16\u8f91</button> ' +
            '<button class="btn btn-xs btn-primary" onclick="PageSQL.reExecute(\'' + blockId + '\')" id="' + blockId + '-reexec" style="display:none">\u25b6 \u6267\u884c</button>' +
          '</div>' +
        '</div>' +
        '<div class="sql-thinking" id="' + blockId + '-thinking" style="display:none"></div>' +
        '<pre class="sql-code" id="' + blockId + '-sql-code"></pre>' +
        '<div class="sql-edit-area" id="' + blockId + '-edit-area" style="display:none">' +
          '<textarea id="' + blockId + '-edit-sql" rows="6" class="sql-edit-textarea"></textarea>' +
        '</div>' +
      '</div>' +
      '<div class="sql-result-section" id="' + blockId + '-result" style="display:none">' +
        '<div class="sql-result-meta" id="' + blockId + '-meta"></div>' +
        '<div class="sql-result-table-wrap"><table class="sql-result-table" id="' + blockId + '-table"></table></div>' +
        '<button class="btn btn-sm btn-outline" onclick="PageSQL.exportExcel(\'' + blockId + '\')">\ud83d\udce5 \u5bfc\u51fa Excel</button>' +
      '</div>' +
      '<div class="sql-chart-section" id="' + blockId + '-chart" style="display:none">' +
        '<div class="sql-section-header"><span>\ud83d\udcc8 \u56fe\u8868</span></div>' +
        '<div id="' + blockId + '-chart-container" style="height:320px"></div>' +
      '</div>' +
      '<div class="sql-analysis-section" id="' + blockId + '-analysis" style="display:none">' +
        '<div class="sql-section-header"><span>\ud83d\udca1 \u5206\u6790\u603b\u7ed3</span></div>' +
        '<div class="sql-analysis-content" id="' + blockId + '-analysis-content"></div>' +
      '</div>';

    container.prepend(block);
    input.value = '';
    var startTime = Date.now();

    try {
      var token = API.getToken();
      var resp = await fetch('/api/sql/query', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': token ? 'Bearer ' + token : '',
        },
        body: JSON.stringify({ question: question, history: queryHistory.slice(-6) }),
      });

      if (!resp.ok) {
        var err = await resp.json().catch(function() { return {}; });
        throw new Error(err.detail || 'HTTP ' + resp.status);
      }

      var reader = resp.body.getReader();
      var decoder = new TextDecoder();
      var buffer = '';

      while (true) {
        var r = await reader.read();
        if (r.done) break;
        buffer += decoder.decode(r.value, { stream: true });
        var events = buffer.split('\n\n');
        buffer = events.pop() || '';
        for (var i = 0; i < events.length; i++) {
          var lines = events[i].split('\n');
          var eventType = null, dataStr = '';
          for (var j = 0; j < lines.length; j++) {
            if (lines[j].startsWith('event: ')) eventType = lines[j].slice(7).trim();
            else if (lines[j].startsWith('data: ')) dataStr = lines[j].slice(6).trim();
          }
          if (!eventType || !dataStr) continue;
          var data;
          try { data = JSON.parse(dataStr); } catch(e2) { continue; }
          handleEvent(blockId, eventType, data, startTime);
        }
      }
      queryHistory.push({ role: 'user', content: question });
    } catch (e) {
      var errEl = document.getElementById(blockId + '-analysis');
      errEl.style.display = 'block';
      document.getElementById(blockId + '-analysis-content').innerHTML =
        '<div class="sql-error">\u274c ' + UI.escapeHtml(e.message) + '</div>';
    } finally {
      input.disabled = false;
      input.focus();
      if (sendBtn) { sendBtn.disabled = false; sendBtn.textContent = '\u67e5\u8be2'; }
    }
  }

  function handleEvent(blockId, type, data, startTime) {
    if (type === 'sql') {
      var sqlSection = document.getElementById(blockId + '-sql');
      sqlSection.style.display = 'block';
      document.getElementById(blockId + '-sql-code').textContent = data.sql;
      if (data.thinking) {
        var thinkEl = document.getElementById(blockId + '-thinking');
        thinkEl.style.display = 'block';
        thinkEl.innerHTML = '<span class="sql-thinking-label">\ud83d\udcad</span> ' + UI.escapeHtml(data.thinking);
      }
      sqlSection.dataset.sql = data.sql;
    } else if (type === 'result') {
      var resultSection = document.getElementById(blockId + '-result');
      resultSection.style.display = 'block';
      if (data.error) {
        resultSection.innerHTML = '<div class="sql-error">\u274c ' + UI.escapeHtml(data.error) + '</div>';
        return;
      }
      document.getElementById(blockId + '-meta').textContent =
        '\u26a1 \u8017\u65f6 ' + data.elapsed_ms + 'ms \u00b7 \u8fd4\u56de ' + data.row_count + ' \u884c';
      var table = document.getElementById(blockId + '-table');
      var html = '<thead><tr>';
      data.columns.forEach(function(c) { html += '<th>' + UI.escapeHtml(String(c)) + '</th>'; });
      html += '</tr></thead><tbody>';
      data.rows.forEach(function(row) {
        html += '<tr>';
        row.forEach(function(v) { html += '<td>' + UI.escapeHtml(String(v == null ? '' : v)) + '</td>'; });
        html += '</tr>';
      });
      html += '</tbody>';
      table.innerHTML = html;
      document.getElementById(blockId + '-time').textContent =
        ((Date.now() - startTime) / 1000).toFixed(1) + 's';
      resultSection.dataset.columns = JSON.stringify(data.columns);
      resultSection.dataset.rows = JSON.stringify(data.rows);
    } else if (type === 'analysis') {
      if (data.chart) renderChart(blockId, data);
      var analysisSection = document.getElementById(blockId + '-analysis');
      analysisSection.style.display = 'block';
      var html2 = '';
      if (data.summary) html2 += '<p>' + UI.escapeHtml(data.summary) + '</p>';
      if (data.highlights && data.highlights.length) {
        html2 += '<div class="sql-highlights">';
        data.highlights.forEach(function(h) { html2 += '<div class="sql-highlight-item">\ud83d\udd0d ' + UI.escapeHtml(h) + '</div>'; });
        html2 += '</div>';
      }
      document.getElementById(blockId + '-analysis-content').innerHTML = html2;
      queryHistory.push({ role: 'assistant', content: data.summary || '\u67e5\u8be2\u5b8c\u6210' });
    } else if (type === 'error') {
      var errEl2 = document.getElementById(blockId + '-analysis');
      errEl2.style.display = 'block';
      document.getElementById(blockId + '-analysis-content').innerHTML =
        '<div class="sql-error">\u274c ' + UI.escapeHtml(data.error || JSON.stringify(data)) + '</div>';
    }
  }

  function renderChart(blockId, data) {
    var chartSection = document.getElementById(blockId + '-chart');
    chartSection.style.display = 'block';
    var chartEl = document.getElementById(blockId + '-chart-container');
    var chart = echarts.init(chartEl);
    var columns = JSON.parse(document.getElementById(blockId + '-result').dataset.columns || '[]');
    var rows = JSON.parse(document.getElementById(blockId + '-result').dataset.rows || '[]');
    var chartCfg = data.chart;
    var xIdx = columns.indexOf(chartCfg.x_col);
    var yIdx = columns.indexOf(chartCfg.y_col);
    if (xIdx === -1 || yIdx === -1) return;
    var xData = rows.map(function(r) { return String(r[xIdx]); });
    var yData = rows.map(function(r) { return Number(r[yIdx]) || 0; });
    var option;
    if (chartCfg.type === 'pie') {
      option = {
        title: { text: chartCfg.title, left: 'center' },
        tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
        series: [{ type: 'pie', radius: '60%', data: xData.map(function(x, i) { return { name: x, value: yData[i] }; }), label: { formatter: '{b}\n{d}%' } }],
      };
    } else if (chartCfg.type === 'line') {
      option = {
        title: { text: chartCfg.title, left: 'center' },
        tooltip: { trigger: 'axis' },
        xAxis: { type: 'category', data: xData, axisLabel: { rotate: xData.length > 8 ? 30 : 0 } },
        yAxis: { type: 'value' },
        series: [{ type: 'line', data: yData, smooth: true, areaStyle: { opacity: 0.3 } }],
      };
    } else {
      option = {
        title: { text: chartCfg.title, left: 'center' },
        tooltip: { trigger: 'axis' },
        xAxis: { type: 'category', data: xData, axisLabel: { rotate: xData.length > 8 ? 30 : 0 } },
        yAxis: { type: 'value' },
        series: [{ type: 'bar', data: yData, itemStyle: { color: '#5470c6' } }],
      };
    }
    chart.setOption(option);
    window.addEventListener('resize', function() { chart.resize(); });
  }

  function copySQL(blockId) {
    var sql = document.getElementById(blockId + '-sql').dataset.sql || '';
    navigator.clipboard.writeText(sql).then(function() { UI.toast('SQL \u5df2\u590d\u5236', 'success'); });
  }

  function toggleEdit(blockId) {
    var editArea = document.getElementById(blockId + '-edit-area');
    var sqlCode = document.getElementById(blockId + '-sql-code');
    var reexecBtn = document.getElementById(blockId + '-reexec');
    var sqlSection = document.getElementById(blockId + '-sql');
    if (editArea.style.display === 'none') {
      editArea.style.display = 'block';
      sqlCode.style.display = 'none';
      reexecBtn.style.display = 'inline-block';
      document.getElementById(blockId + '-edit-sql').value = sqlSection.dataset.sql || '';
    } else {
      editArea.style.display = 'none';
      sqlCode.style.display = 'block';
      reexecBtn.style.display = 'none';
    }
  }

  async function reExecute(blockId) {
    var sql = document.getElementById(blockId + '-edit-sql').value.trim();
    if (!sql) return;
    var resultSection = document.getElementById(blockId + '-result');
    resultSection.style.display = 'block';
    resultSection.innerHTML = '<div class="sql-loading">\u6267\u884c\u4e2d...</div>';
    try {
      var token = API.getToken();
      var resp = await fetch('/api/sql/execute', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': token ? 'Bearer ' + token : '' },
        body: JSON.stringify({ sql: sql }),
      });
      var data = await resp.json();
      if (data.error) {
        resultSection.innerHTML = '<div class="sql-error">\u274c ' + UI.escapeHtml(data.error) + '</div>';
        return;
      }
      document.getElementById(blockId + '-sql').dataset.sql = sql;
      document.getElementById(blockId + '-sql-code').textContent = sql;
      resultSection.innerHTML =
        '<div class="sql-result-meta">\u26a1 \u8017\u65f6 ' + data.elapsed_ms + 'ms \u00b7 \u8fd4\u56de ' + data.row_count + ' \u884c</div>' +
        '<div class="sql-result-table-wrap"><table class="sql-result-table" id="' + blockId + '-table2"></table></div>' +
        '<button class="btn btn-sm btn-outline" onclick="PageSQL.exportExcel(\'' + blockId + '\')">\ud83d\udce5 \u5bfc\u51fa Excel</button>';
      var table = document.getElementById(blockId + '-table2');
      var html = '<thead><tr>';
      data.columns.forEach(function(c) { html += '<th>' + UI.escapeHtml(String(c)) + '</th>'; });
      html += '</tr></thead><tbody>';
      data.rows.forEach(function(row) {
        html += '<tr>';
        row.forEach(function(v) { html += '<td>' + UI.escapeHtml(String(v == null ? '' : v)) + '</td>'; });
        html += '</tr>';
      });
      html += '</tbody>';
      table.innerHTML = html;
      resultSection.dataset.columns = JSON.stringify(data.columns);
      resultSection.dataset.rows = JSON.stringify(data.rows);
      toggleEdit(blockId);
    } catch (e) {
      resultSection.innerHTML = '<div class="sql-error">\u274c ' + UI.escapeHtml(e.message) + '</div>';
    }
  }

  function exportExcel(blockId) {
    var columns = JSON.parse(document.getElementById(blockId + '-result')?.dataset.columns || '[]');
    var rows = JSON.parse(document.getElementById(blockId + '-result')?.dataset.rows || '[]');
    if (!columns.length) { UI.toast('\u6ca1\u6709\u6570\u636e\u53ef\u5bfc\u51fa', 'warning'); return; }
    var csv = columns.join(',') + '\n';
    rows.forEach(function(row) {
      csv += row.map(function(v) {
        var s = String(v == null ? '' : v);
        return s.indexOf(',') !== -1 || s.indexOf('"') !== -1 ? '"' + s.replace(/"/g, '""') + '"' : s;
      }).join(',') + '\n';
    });
    var blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8;' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = 'sql_export_' + new Date().toISOString().slice(0, 10) + '.csv';
    a.click();
    URL.revokeObjectURL(url);
    UI.toast('\u5df2\u5bfc\u51fa CSV \u6587\u4ef6', 'success');
  }

  async function showSchema() {
    var panel = document.getElementById('sql-schema-panel');
    // 如果已加载，切换显示
    if (panel.dataset.loaded === '1') {
      panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
      return;
    }
    try {
      panel.style.display = 'block';
      panel.innerHTML = '<div class="sql-loading">\u52a0\u8f7d\u8868\u7ed3\u6784...</div>';
      var token = API.getToken();
      var resp = await fetch('/api/sql/schema', {
        headers: { 'Authorization': token ? 'Bearer ' + token : '' },
      });
      var data = await resp.json();
      var html = '<div class="sql-schema-header"><strong>\ud83d\udccb \u6570\u636e\u5e93\u8868\u7ed3\u6784</strong> ' +
        '<button class="btn btn-xs" onclick="document.getElementById(\'sql-schema-panel\').style.display=\'none\'">\u2715 \u6536\u8d77</button></div>';
      if (data.tables) {
        data.tables.forEach(function(t) {
          html += '<div class="sql-schema-table">' +
            '<div class="sql-schema-table-name">\ud83d\udcca ' + UI.escapeHtml(t.name) +
            ' <span class="sql-schema-comment">' + UI.escapeHtml(t.comment) + '</span>' +
            ' <span class="sql-schema-count">' + t.row_count + ' \u884c</span></div>' +
            '<table class="sql-schema-columns"><thead><tr><th>\u5217\u540d</th><th>\u7c7b\u578b</th><th>\u8bf4\u660e</th></tr></thead><tbody>';
          t.columns.forEach(function(c) {
            html += '<tr><td><code>' + UI.escapeHtml(c.name) + '</code></td>' +
              '<td>' + UI.escapeHtml(c.type) + '</td>' +
              '<td>' + UI.escapeHtml(c.comment) + '</td></tr>';
          });
          html += '</tbody></table></div>';
        });
      }
      if (data.relations && data.relations.length) {
        html += '<div class="sql-schema-relations"><strong>\u5173\u8054\u5173\u7cfb\uff1a</strong><br>';
        data.relations.forEach(function(r) {
          html += '<code>' + UI.escapeHtml(r.from) + '</code> \u2192 <code>' + UI.escapeHtml(r.to) + '</code><br>';
        });
        html += '</div>';
      }
      panel.innerHTML = html;
      panel.dataset.loaded = '1';
    } catch (e) {
      panel.innerHTML = '<div class="sql-error">\u274c \u83b7\u53d6\u8868\u7ed3\u6784\u5931\u8d25: ' + UI.escapeHtml(e.message) + '</div>';
    }
  }

  return { init: init, askQuestion: askQuestion, askQuick: askQuick, copySQL: copySQL, toggleEdit: toggleEdit, reExecute: reExecute, exportExcel: exportExcel, showSchema: showSchema };
})();
