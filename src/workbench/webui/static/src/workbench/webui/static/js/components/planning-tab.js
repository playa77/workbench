/** Planning Agent Tab Component
 * SSE streaming for AI-powered strategic planning (9 plan types).
 * Events: started, phase, completed, error, done
 */

(function () {
  var activeRunId = null;
  var activeReader = null;
  var activeAbortController = null;

  Router.register("planning", renderPlanningTab);

  function renderPlanningTab(container) {
    cleanup();

    container.innerHTML = ''
      + '<div style="max-width:900px;margin:0 auto">'
      +   '<h2 style="margin-bottom:16px;font-size:20px;font-weight:600">Strategic Planning</h2>'
      +   '<div class="card">'
      +     '<div class="card-header">Plan Setup</div>'
      +     '<div class="form-group">'
      +       '<label>Goal or Objective</label>'
      +       '<textarea class="form-input" id="pl-goal" placeholder="Describe your goal, project, or problem..." style="min-height:80px"></textarea>'
      +     '</div>'
      +     '<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px">'
      +       '<div class="form-group">'
      +         '<label>Plan Type</label>'
      +         '<select class="form-input" id="pl-type"><option value="">Loading types...</option></select>'
      +       '</div>'
      +       '<div class="form-group">'
      +         '<label>Model</label>'
      +         '<select class="form-input" id="pl-model" disabled><option>Loading models...</option></select>'
      +       '</div>'
      +       '<div class="form-group">'
      +         '<label>Temperature</label>'
      +         '<input class="form-input" id="pl-temperature" type="number" value="0.5" min="0" max="2" step="0.1" />'
      +       '</div>'
      +     '</div>'
      +     '<div style="display:flex;gap:8px">'
      +       '<button class="btn btn-primary" id="btn-start-plan">Generate Plan</button>'
      +       '<button class="btn btn-danger" id="btn-stop-plan" style="display:none">Stop</button>'
      +     '</div>'
      +   '</div>'
      +   '<div id="planning-output" style="margin-top:24px"></div>'
      + '</div>';

    loadPlanTypes();
    loadPlanningModels();
    document.getElementById('btn-start-plan').addEventListener('click', startPlan);
    document.getElementById('btn-stop-plan').addEventListener('click', stopPlan);

    renderPlanningPastSessions();
  }

  function loadPlanTypes() {
    fetch('/api/v1/agents/planning/types', {
      headers: { 'Authorization': 'Bearer ' + API.getApiKey() },
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var types = data.plan_types || {};
        var sel = document.getElementById('pl-type');
        if (!sel) return;
        sel.innerHTML = Object.keys(types).map(function (k) {
          return '<option value="' + Utils.escapeHtml(k) + '"' + (k === 'project_plan' ? ' selected' : '') + '>'
            + Utils.escapeHtml(types[k].name || k) + '</option>';
        }).join('');
      })
      .catch(function () {
        var sel = document.getElementById('pl-type');
        if (sel) sel.innerHTML = '<option value="">Failed to load</option>';
      });
  }

  function loadPlanningModels() {
    var modelSelect = document.getElementById('pl-model');
    if (!modelSelect) return;
    fetch('/api/v1/me/inference/models')
      .then(function (resp) { return resp.json(); })
      .then(function (data) {
        var models = data.models || [];
        var defaultModel = data.default_model || (models.length > 0 ? models[0] : '');
        modelSelect.innerHTML = '';
        models.forEach(function (m) {
          var opt = document.createElement('option');
          opt.value = m;
          opt.textContent = m;
          if (m === defaultModel) opt.selected = true;
          modelSelect.appendChild(opt);
        });
        modelSelect.disabled = false;
      })
      .catch(function () {
        modelSelect.innerHTML = '<option value="">No models available</option>';
        modelSelect.disabled = false;
      });
  }

  function startPlan() {
    var goal = document.getElementById('pl-goal').value.trim();
    if (!goal) return alert('Enter a goal or objective');

    var planType = document.getElementById('pl-type').value;
    var model = document.getElementById('pl-model').value.trim();
    var temperature = parseFloat(document.getElementById('pl-temperature').value) || 0.5;

    var btnStart = document.getElementById('btn-start-plan');
    if (!btnStart) return;
    var btnStop = document.getElementById('btn-stop-plan');
    Utils.setButtonLoading(btnStart, 'Generating...');
    Utils.showToast('Generating plan...', 'info');
    btnStop.style.display = 'inline-flex';

    var output = document.getElementById('planning-output');
    output.innerHTML = ''
      + '<div class="card">'
      +   '<div class="card-header">Generating Plan</div>'
      +   '<div style="display:flex;align-items:center;gap:12px;margin-bottom:12px">'
      +     '<div class="spinner"></div>'
      +     '<span id="pl-phase-label" style="font-size:13px;color:var(--text-secondary)">Starting...</span>'
      +   '</div>'
      +   '<div id="pl-stream-box" style="background:var(--bg-code);border:1px solid var(--border-color);border-radius:var(--radius-sm);padding:16px;max-height:50vh;overflow-y:auto;font-family:var(--font-mono);font-size:12px;white-space:pre-wrap;color:var(--text-secondary)"></div>'
      + '</div>';

    cleanup();

    activeAbortController = new AbortController();

    fetch('/api/v1/agents/planning/runs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + API.getApiKey() },
      body: JSON.stringify({
        goal: goal,
        plan_type: planType || 'project_plan',
        model: model || null,
        temperature: temperature,
      }),
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
        var streamContent = '';

        function pump() {
          activeReader.read().then(function (result) {
            if (result.done) { resetPlanning(); return; }
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
                  routePlanningEvent(currentEvent || 'message', data, streamContent);
                } catch (_e) {}
                currentEvent = null;
              }
            }
            pump();
          }).catch(function () { resetPlanning(); });
        }
        pump();
      })
      .catch(function (e) {
        if (e.name === 'AbortError') return;
        output.innerHTML = '<div class="alert alert-error">' + Utils.escapeHtml(e.message) + '</div>';
        resetPlanning();
        Utils.showToast(e.message, 'error');
      });
  }

  function routePlanningEvent(eventType, data) {
    switch (eventType) {
      case 'started':
        activeRunId = data.run_id || activeRunId;
        var label = document.getElementById('pl-phase-label');
        if (label) label.textContent = 'Generating...';
        break;
      case 'phase':
        var phaseLabel = document.getElementById('pl-phase-label');
        if (phaseLabel && data.message) phaseLabel.textContent = data.message;
        break;
      case 'completed':
        setPhase('Completed');
        renderPlanResult(data.content || '');
        Utils.showToast('Plan complete', 'success');
        break;
      case 'error':
        var streamBox2 = document.getElementById('pl-stream-box');
        if (streamBox2) streamBox2.innerHTML += '<span style="color:var(--danger)">Error: ' + Utils.escapeHtml(data.message || data) + '</span>';
        resetPlanning();
        Utils.showToast(data.message || 'Error generating plan', 'error');
        break;
    }
  }

  function setPhase(phase) {
    var el = document.getElementById('pl-phase-label');
    if (el) el.textContent = phase;
  }

  function renderPlanResult(content) {
    var md = Utils.escapeHtml(content)
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.+?)\*/g, '<em>$1</em>')
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/^### (.+)$/gm, '<h3 style="margin:20px 0 8px;font-size:16px;font-weight:600">$1</h3>')
      .replace(/^## (.+)$/gm, '<h2 style="margin:24px 0 12px;font-size:18px;font-weight:700">$1</h2>')
      .replace(/^# (.+)$/gm, '<h1 style="margin:28px 0 16px;font-size:20px;font-weight:700">$1</h1>')
      .replace(/^> (.+)$/gm, '<blockquote style="border-left:3px solid var(--accent);padding:4px 12px;margin:8px 0;color:var(--text-muted);font-style:italic">$1</blockquote>')
      .replace(/^[-*] (.+)$/gm, '<li style="margin-left:20px">$1</li>')
      .replace(/\n\n/g, '</p><p style="margin-bottom:8px;line-height:1.7">')
      .replace(/\n/g, '<br>');

    var output = document.getElementById('planning-output');
    output.innerHTML = ''
      + '<div class="card">'
      +   '<div class="card-header">Plan Result</div>'
      +   '<div style="line-height:1.7;font-size:13px"><p style="margin-bottom:8px;line-height:1.7">' + md + '</p></div>'
      +   '<div style="margin-top:16px;display:flex;gap:8px;flex-wrap:wrap;align-items:center">'
      +     '<button class="btn btn-primary btn-sm" onclick="window.planningCopyResult()">Copy</button>'
      +     '<span id="planning-template-picker"></span>'
      +     '<button class="btn btn-secondary btn-sm" onclick="window.planningExportHtml()">Export HTML</button>'
      +     '<button class="btn btn-secondary btn-sm" onclick="window.planningExportPdf()">Export PDF</button>'
      +     '<button class="btn btn-secondary btn-sm" onclick="Router.setActive(\'planning\')">New Plan</button>'
      +   '</div>'
      + '</div>';
    window._planningResultContent = content;
    if (window.renderTemplateSelector) {
      window.renderTemplateSelector('planning-template-picker');
    }
  }

  window.planningCopyResult = function () {
    if (window._planningResultContent) {
      navigator.clipboard.writeText(window._planningResultContent)
        .then(function () { Utils.showToast('Copied to clipboard', 'success'); })
        .catch(function () { Utils.showToast('Failed to copy', 'error'); });
    }
  };

  window.planningExportHtml = function () {
    if (window._planningResultContent) {
      Utils.exportMarkdownAsHtml(window._planningResultContent, 'Planning Report');
      Utils.showToast('HTML exported', 'success');
    }
  };

  window.planningExportPdf = function () {
    if (window._planningResultContent) {
      var template = window.getSelectedTemplate ? window.getSelectedTemplate() : 'professional';
      Utils.exportMarkdownAsPdf(window._planningResultContent, 'Planning Report', template);
    }
  };

  function stopPlan() {
    if (activeAbortController) { activeAbortController.abort(); activeAbortController = null; }
    activeReader = null;
    if (activeRunId) {
      fetch('/api/v1/agents/planning/runs/' + activeRunId + '/stop', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + API.getApiKey() },
      }).catch(function () {});
    }
    resetPlanning();
  }

  function cleanup() {
    if (activeAbortController) { activeAbortController.abort(); activeAbortController = null; }
    activeReader = null;
    activeRunId = null;
  }

  function resetPlanning() {
    var s = document.getElementById('btn-start-plan');
    var t = document.getElementById('btn-stop-plan');
    if (s) Utils.resetButton(s);
    if (t) t.style.display = 'none';
    activeReader = null;
    activeRunId = null;
    activeAbortController = null;
  }

  // Past Planning Sessions
  var planningPastLoaded = false;

  function renderPlanningPastSessions() {
    var output = document.getElementById('planning-output');
    if (!output) return;
    output.insertAdjacentHTML('afterend', ''
      + '<div class="card" style="margin-top:24px">'
      +   '<div class="card-header" style="cursor:pointer;display:flex;justify-content:space-between;align-items:center" id="planning-past-toggle">'
      +     '<span>Past Planning Sessions</span>'
      +     '<span id="planning-past-arrow" style="font-size:12px">&#x25BC;</span>'
      +   '</div>'
      +   '<div id="planning-past-sessions" style="display:none;padding:8px 0">'
      +     '<div style="text-align:center;padding:12px;color:var(--text-muted)">Loading...</div>'
      +   '</div>'
      + '</div>'
    );

    document.getElementById('planning-past-toggle').addEventListener('click', function () {
      var body = document.getElementById('planning-past-sessions');
      var arrow = document.getElementById('planning-past-arrow');
      if (body.style.display === 'none') {
        body.style.display = 'block';
        arrow.innerHTML = '&#x25B2;';
        if (!planningPastLoaded) {
          planningPastLoaded = true;
          loadPlanningPastSessions();
        }
      } else {
        body.style.display = 'none';
        arrow.innerHTML = '&#x25BC;';
      }
    });
  }

  function loadPlanningPastSessions() {
    var body = document.getElementById('planning-past-sessions');
    API.listSessions('planning').then(function (sessions) {
      if (!sessions || sessions.length === 0) {
        body.innerHTML = '<div style="text-align:center;padding:12px;color:var(--text-muted);font-size:12px">No past planning sessions</div>';
        return;
      }
      var recent = sessions.slice(0, 10);
      body.innerHTML = recent.map(function (s) {
        var date = s.created_at ? s.created_at.split('T')[0] : '';
        var title = Utils.escapeHtml((s.title || 'Plan').length > 60 ? s.title.substring(0, 57) + '...' : s.title || 'Plan');
        return '<div style="display:flex;justify-content:space-between;align-items:center;padding:8px 12px;border-bottom:1px solid var(--border-color);cursor:pointer" data-session-id="' + s.id + '" class="planning-past-item">'
          + '<span style="font-size:12px;color:var(--text-muted);flex-shrink:0;margin-right:12px">' + date + '</span>'
          + '<span style="font-size:13px;flex:1">' + title + '</span>'
          + '<span style="font-size:11px;color:var(--text-muted);flex-shrink:0">' + (s.word_count || 0) + ' words</span>'
          + '</div>';
      }).join('');
      body.querySelectorAll('.planning-past-item').forEach(function (el) {
        el.addEventListener('click', function () {
          loadPastPlanningSession(el.dataset.sessionId);
        });
      });
    }).catch(function () {
      body.innerHTML = '<div style="text-align:center;padding:12px;color:var(--danger);font-size:12px">Failed to load sessions</div>';
    });
  }

  function loadPastPlanningSession(id) {
    var output = document.getElementById('planning-output');
    output.innerHTML = '<div style="text-align:center;padding:24px;color:var(--text-muted)">Loading session...</div>';
    API.getSession(id).then(function (session) {
      renderPlanResult(session.content || '');
      // Re-add past sessions
      planningPastLoaded = false;
      renderPlanningPastSessions();
    }).catch(function (e) {
      output.innerHTML = '<div class="alert alert-error">' + Utils.escapeHtml(e.message) + '</div>';
      renderPlanningPastSessions();
    });
  }
})();
