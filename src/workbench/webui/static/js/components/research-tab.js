/** Research Agent Tab Component
 * SSE streaming for autonomous deep research.
 * Events: thinking, status, tool_call, tool_result, error, complete, done
 */

(function () {
  var activeRunId = null;
  var activeReader = null;
  var activeAbortController = null;

  Router.register("research", renderResearchTab);

  function renderResearchTab(container) {
    cleanup();

    container.innerHTML = ''
      + '<div style="max-width:900px;margin:0 auto">'
      +   '<h2 style="margin-bottom:16px;font-size:20px;font-weight:600">Deep Research</h2>'
      +   '<div class="card">'
      +     '<div class="card-header">Research Question</div>'
      +     '<div class="form-group">'
      +       '<label>What would you like to research?</label>'
      +       '<textarea class="form-input" id="rq-question" placeholder="Enter a research question..." style="min-height:80px"></textarea>'
      +     '</div>'
      +     '<div class="form-group">'
      +       '<label>Report Title (optional)</label>'
      +       '<input class="form-input" id="rq-report-title" type="text" placeholder="Leave empty to use the question as title" maxlength="200" />'
      +     '</div>'
      +     '<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">'
      +       '<div class="form-group">'
      +         '<label>Tree Depth (levels, 1–5)</label>'
      +         '<input class="form-input" id="rq-depth" type="number" value="2" min="1" max="5" />'
      +       '</div>'
      +       '<div class="form-group">'
      +         '<label>Branching Factor (per node, 1–10)</label>'
      +         '<input class="form-input" id="rq-branching" type="number" value="5" min="1" max="10" />'
      +       '</div>'
      +     '</div>'
      +     '<div style="margin-top:4px;font-size:11px;color:var(--text-muted)" id="rq-leaf-display">'
      +       'Estimated research leaves: 25 — leaf count = branches<sup>depth</sup>'
      +     '</div>'
      +     '<div class="form-group">'
      +       '<label>Report Language</label>'
      +       '<select class="form-input" id="rq-language">'
      +         '<option value="auto" selected>Auto (detect from question)</option>'
      +         '<option value="en">English</option>'
      +         '<option value="de">Deutsch (German)</option>'
      +       '</select>'
      +     '</div>'
      +     '<div class="form-group">'
      +       '<label>Brave API Key (optional)</label>'
      +       '<input class="form-input" id="rq-brave-key" type="password" placeholder="BSA-..." />'
      +     '</div>'
      +     '<div style="display:flex;gap:8px">'
      +       '<button class="btn btn-primary" id="btn-start-research">Start Research</button>'
      +       '<button class="btn btn-danger" id="btn-stop-research" style="display:none">Stop</button>'
      +     '</div>'
      +   '</div>'
      +   '<div id="research-output" style="margin-top:24px"></div>'
      + '</div>';

    document.getElementById('btn-start-research').addEventListener('click', startResearch);
    document.getElementById('btn-stop-research').addEventListener('click', stopResearch);

    // Live leaf count display
    var depthEl = document.getElementById('rq-depth');
    var branchEl = document.getElementById('rq-branching');
    var leafDisplay = document.getElementById('rq-leaf-display');
    function updateLeafCount() {
      var d = parseInt(depthEl.value) || 2;
      var b = parseInt(branchEl.value) || 5;
      var leafCount = Math.pow(b, d);
      var color = leafCount > 512 ? 'orange' : (leafCount > 256 ? 'orange' : 'var(--text-muted)');
      if (leafCount > 1000) color = 'red';
      leafDisplay.innerHTML = 'Estimated research leaves: ' + leafCount + ' — leaf count = branches<sup>depth</sup>';
      leafDisplay.style.color = color;
    }
    depthEl.addEventListener('input', updateLeafCount);
    branchEl.addEventListener('input', updateLeafCount);

    renderResearchPastSessions();
  }

  function startResearch() {
    var question = document.getElementById('rq-question').value.trim();
    if (!question) return alert('Enter a research question');

    var depth = parseInt(document.getElementById('rq-depth').value) || 2;
    var branching = parseInt(document.getElementById('rq-branching').value) || 5;
    var leafCount = Math.pow(branching, depth);

    if (leafCount > 1000) {
      alert('Too many leaves (' + leafCount + '). Reduce depth or branching to stay under 1,000.');
      return;
    }
    if (leafCount > 512) {
      if (!confirm('This will explore ' + leafCount + ' research leaves. This is a very deep investigation and will consume significant tokens. Continue?')) {
        return;
      }
    }

    var braveKey = document.getElementById('rq-brave-key').value.trim() || undefined;
    var language = document.getElementById('rq-language').value;
    var reportTitle = document.getElementById('rq-report-title').value.trim() || undefined;
    // Capture the title for this run so the report + PDF export use it.
    window._researchReportTitle = reportTitle || question;

    var btnStart = document.getElementById('btn-start-research');
    if (!btnStart) return;
    var btnStop = document.getElementById('btn-stop-research');
    Utils.setButtonLoading(btnStart, 'Starting...');
    Utils.showToast('Research started', 'info');
    btnStop.style.display = 'inline-flex';

    var output = document.getElementById('research-output');
    // Compute approximate max iterations for status display
    var estMaxIter = Math.min(leafCount * 3, 100);
    output.innerHTML = renderStatusPanel(0, 0, estMaxIter, 0, 'starting');

    cleanup();

    var body = { question: question, tree_depth: depth, branching_factor: branching, language: language };
    if (braveKey) body.brave_api_key = braveKey;
    if (reportTitle) body.report_title = reportTitle;

    activeAbortController = new AbortController();

    fetch('/api/v1/agents/research/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + API.getApiKey() },
      body: JSON.stringify(body),
      signal: activeAbortController.signal,
    })
      .then(function (resp) {
        if (!resp.ok) {
          return resp.json().then(function (e) { throw new Error(e.detail || 'Error ' + resp.status); });
        }
        activeReader = resp.body.getReader();
        var decoder = new TextDecoder();
        var buffer = '';
        var currentEvent = null;

        function pump() {
          activeReader.read().then(function (result) {
            if (result.done) { resetButtons(); return; }
            buffer += decoder.decode(result.value, { stream: true });
            var lines = buffer.split('\n');
            buffer = lines.pop() || '';
            for (var i = 0; i < lines.length; i++) {
              var line = lines[i];
              if (!line) continue;
              if (line.startsWith('event: ')) { currentEvent = line.slice(7).trim(); continue; }
              if (line.startsWith('data: ')) {
                try {
                  var data = JSON.parse(line.slice(6));
                  routeEvent(currentEvent || 'message', data);
                } catch (_e) { /* malformed JSON */ }
                currentEvent = null;
              }
            }
            pump();
          }).catch(function () { resetButtons(); });
        }
        pump();
      })
      .catch(function (e) {
        if (e.name === 'AbortError') return;
        output.innerHTML = '<div class="alert alert-error">Failed to start: ' + Utils.escapeHtml(e.message) + '</div>';
        resetButtons();
      });
  }

  function routeEvent(eventType, data) {
    switch (eventType) {
      case 'thinking':
        appendThinking(Utils.escapeHtml(typeof data === 'string' ? data : (data.message || '')));
        break;
      case 'status':
        activeRunId = data.run_id || activeRunId;
        updateStatusPanel(
          data.status || 'running',
          data.iteration != null ? data.iteration : 0,
          data.max_iterations || 0,
          data.sources != null ? data.sources : 0,
          data.input_tokens || 0,
          data.output_tokens || 0
        );
        if (data.actions) {
          var el = document.getElementById('research-actions-list');
          if (el) {
            el.innerHTML = data.actions.map(function (a) {
              return '<div style="padding:3px 0;font-size:11px"><strong style="color:var(--accent)">' + Utils.escapeHtml(a.tool) + '</strong> ' + Utils.escapeHtml(a.result_summary || '') + '</div>';
            }).join('');
          }
        }
        break;
      case 'tool_call':
        appendThinking('<span style="color:var(--accent)">&#x2699; ' + Utils.escapeHtml(data.name) + '</span> <span style="color:var(--text-muted)">running...</span>');
        break;
      case 'tool_result':
        var resultMsg;
        if (data.error) {
          resultMsg = '<span style="color:var(--danger)">error: ' + Utils.escapeHtml(data.error) + '</span>';
        } else {
          var len = (data.result && typeof data.result === 'string') ? data.result.length : '?';
          resultMsg = '<span style="color:var(--text-muted)">done (' + len + ' chars)</span>';
        }
        appendThinking('<span style="color:var(--accent)">&#x2699; ' + Utils.escapeHtml(data.name) + '</span> ' + resultMsg);
        break;
      case 'complete':
        renderReport(typeof data === 'string' ? data : (data.report || ''));
        resetButtons();
        Utils.showToast('Research complete', 'success');
        break;
      case 'error':
        var errMsg = typeof data === 'string' ? data : (data.message || 'Unknown error');
        appendThinking('<span style="color:var(--danger)">' + Utils.escapeHtml(errMsg) + '</span>');
        resetButtons();
        Utils.showToast(errMsg, 'error');
        break;
      case 'done':
        break;
    }
  }

  function appendThinking(msg) {
    var list = document.getElementById('research-thinking-log');
    if (!list) return;
    var div = document.createElement('div');
    div.style.cssText = 'padding:2px 0;font-size:12px;color:var(--text-secondary);border-bottom:1px solid var(--border-color)';
    div.innerHTML = msg;
    list.appendChild(div);
    list.scrollTop = list.scrollHeight;
  }

  function renderStatusPanel(iteration, sources, maxIter, tokens, statusText) {
    return ''
      + '<div class="card">'
      +   '<div class="card-header">Research Progress</div>'
      +   '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:16px;margin-bottom:16px">'
      +     statBox('Iteration', String(iteration) + '/' + String(maxIter), 'var(--accent)')
      +     statBox('Sources', String(sources), 'var(--success)')
      +     statBox('Status', Utils.escapeHtml(statusText), 'var(--warning)')
      +   '</div>'
      +   '<div style="background:var(--bg-code);border:1px solid var(--border-color);border-radius:var(--radius-sm);padding:12px;max-height:260px;overflow-y:auto;font-family:var(--font-mono);font-size:12px" id="research-thinking-log">'
      +     '<div style="color:var(--text-muted);padding:2px 0">Starting research...</div>'
      +   '</div>'
      +   '<div style="margin-top:12px;font-size:12px;color:var(--text-muted)" id="research-actions-list"></div>'
      + '</div>';
  }

  function updateStatusPanel(status, iteration, maxIter, sources, inTokens, outTokens) {
    var output = document.getElementById('research-output');
    if (!output) return;
    var tokens = (inTokens || 0) + (outTokens || 0);
    output.innerHTML = renderStatusPanel(iteration, String(sources), maxIter, String(tokens), status);
  }

  function statBox(label, value, color) {
    return '<div style="text-align:center">'
      + '<div style="font-size:11px;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:4px">' + Utils.escapeHtml(label) + '</div>'
      + '<div style="font-size:18px;font-weight:700;color:' + color + '">' + Utils.escapeHtml(value) + '</div>'
      + '</div>';
  }

  function renderReport(content, title) {
    title = title || window._researchReportTitle || 'Research Report';
    window._researchReportTitle = title;
    var md = content
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.+?)\*/g, '<em>$1</em>')
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/^### (.+)$/gm, '<h3 style="margin:20px 0 8px;font-size:16px;font-weight:600">$1</h3>')
      .replace(/^## (.+)$/gm, '<h2 style="margin:24px 0 12px;font-size:18px;font-weight:700">$1</h2>')
      .replace(/^# (.+)$/gm, '<h1 style="margin:28px 0 16px;font-size:20px;font-weight:700">$1</h1>')
      .replace(/^> (.+)$/gm, '<blockquote style="border-left:3px solid var(--accent);padding:4px 12px;margin:8px 0;color:var(--text-muted);font-style:italic">$1</blockquote>')
      .replace(/^(  -|  \*) (.+)$/gm, '<li style="margin-left:40px">$2</li>')
      .replace(/^[-*] (.+)$/gm, '<li style="margin-left:20px">$1</li>')
      .replace(/\n\n/g, '</p><p style="margin-bottom:8px;line-height:1.7">')
      .replace(/\n/g, '<br>');

    var output = document.getElementById('research-output');
    output.innerHTML = ''
      + '<div class="card">'
      +   '<div class="card-header">Research Report</div>'
      +   '<div style="line-height:1.7;font-size:13px"><p style="margin-bottom:8px;line-height:1.7">' + md + '</p></div>'
      +   '<div style="margin-top:16px;display:flex;gap:8px;flex-wrap:wrap">'
      +     '<button class="btn btn-primary btn-sm" onclick="window.researchCopyReport()">Copy Markdown</button>'
      +     '<button class="btn btn-primary btn-sm" id="btn-export-pdf" onclick="window.researchExportPdf()">Export PDF</button>'
      +     '<button class="btn btn-secondary btn-sm" onclick="Router.setActive(\'research\')">New Research</button>'
      +   '</div>'
      + '</div>';
    window._researchReportContent = content;
  }

  window.researchCopyReport = function () {
    if (window._researchReportContent) {
      navigator.clipboard.writeText(window._researchReportContent).catch(function () {});
    }
  };

  window.researchExportPdf = function () {
    if (window._researchReportContent) {
      var title = window._researchReportTitle || 'Research Report';
      Utils.exportMarkdownAsPdf(window._researchReportContent, title);
    }
  };

  function stopResearch() {
    if (activeAbortController) { activeAbortController.abort(); activeAbortController = null; }
    activeReader = null;
    if (activeRunId) {
      fetch('/api/v1/agents/research/query/' + activeRunId + '/stop', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + API.getApiKey() },
      }).catch(function () {});
    }
    resetButtons();
  }

  function cleanup() {
    if (activeAbortController) { activeAbortController.abort(); activeAbortController = null; }
    activeReader = null;
    activeRunId = null;
  }

  // Past Research Sessions (collapsible)
  var researchPastLoaded = false;

  function renderResearchPastSessions() {
    var container = document.getElementById('research-output');
    if (!container) return;
    var pastHtml = ''
      + '<div class="card" style="margin-top:24px">'
      +   '<div class="card-header" style="cursor:pointer;display:flex;justify-content:space-between;align-items:center" id="research-past-toggle">'
      +     '<span>Past Research Sessions</span>'
      +     '<span id="research-past-arrow" style="font-size:12px">&#x25BC;</span>'
      +   '</div>'
      +   '<div id="research-past-sessions" style="display:none;padding:8px 0">'
      +     '<div style="text-align:center;padding:12px;color:var(--text-muted)">Loading...</div>'
      +   '</div>'
      + '</div>';
    container.insertAdjacentHTML('beforeend', pastHtml);

    document.getElementById('research-past-toggle').addEventListener('click', function () {
      var body = document.getElementById('research-past-sessions');
      var arrow = document.getElementById('research-past-arrow');
      if (body.style.display === 'none') {
        body.style.display = 'block';
        arrow.innerHTML = '&#x25B2;';
        if (!researchPastLoaded) {
          researchPastLoaded = true;
          loadResearchPastSessions();
        }
      } else {
        body.style.display = 'none';
        arrow.innerHTML = '&#x25BC;';
      }
    });
  }

  function loadResearchPastSessions() {
    var body = document.getElementById('research-past-sessions');
    API.listSessions('research').then(function (sessions) {
      if (!sessions || sessions.length === 0) {
        body.innerHTML = '<div style="text-align:center;padding:12px;color:var(--text-muted);font-size:12px">No past research sessions</div>';
        return;
      }
      var recent = sessions.slice(0, 10);
      body.innerHTML = recent.map(function (s) {
        var date = s.created_at ? s.created_at.split('T')[0] : '';
        var title = Utils.escapeHtml((s.title || 'Untitled').length > 60 ? s.title.substring(0, 57) + '...' : s.title || 'Untitled');
        return '<div style="display:flex;justify-content:space-between;align-items:center;padding:8px 12px;border-bottom:1px solid var(--border-color);cursor:pointer" data-session-id="' + s.id + '" class="research-past-item">'
          + '<span style="font-size:12px;color:var(--text-muted);flex-shrink:0;margin-right:12px">' + date + '</span>'
          + '<span style="font-size:13px;flex:1">' + title + '</span>'
          + '<span style="font-size:11px;color:var(--text-muted);flex-shrink:0">' + (s.word_count || 0) + ' words</span>'
          + '</div>';
      }).join('');
      body.querySelectorAll('.research-past-item').forEach(function (el) {
        el.addEventListener('click', function () {
          var sid = el.dataset.sessionId;
          loadPastResearchSession(sid);
        });
      });
    }).catch(function () {
      body.innerHTML = '<div style="text-align:center;padding:12px;color:var(--danger);font-size:12px">Failed to load sessions</div>';
    });
  }

  function loadPastResearchSession(id) {
    var output = document.getElementById('research-output');
    output.innerHTML = '<div style="text-align:center;padding:24px;color:var(--text-muted)">Loading session...</div>';
    API.getSession(id).then(function (session) {
      window._researchReportTitle = session.title || 'Research Report';
      renderReport(session.content || '', session.title);
      // Re-add past sessions after the report
      researchPastLoaded = false;
      renderResearchPastSessions();
    }).catch(function (e) {
      output.innerHTML = '<div class="alert alert-error">' + Utils.escapeHtml(e.message) + '</div>';
      renderResearchPastSessions();
    });
  }

  function resetButtons() {
    var s = document.getElementById('btn-start-research');
    var t = document.getElementById('btn-stop-research');
    if (s) Utils.resetButton(s);
    if (t) t.style.display = 'none';
    activeReader = null;
    activeAbortController = null;
    activeRunId = null;
  }
})();
