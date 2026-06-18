/** Consigliere Agent Tab Component
 * SSE streaming multi-frame deliberation with critique and synthesis.
 * Events: started, phase, frame_start, frame_done, critique_start, critique_done,
 *   rhetoric_start, rhetoric_done, surface, completed, error, done
 */

(function () {
  var activeDeliberationId = null;
  var activeReader = null;
  var activeAbortController = null;

  Router.register("deliberation", renderDeliberationTab);

  function renderDeliberationTab(container) {
    cleanup();

    container.innerHTML = ''
      + '<div style="max-width:900px;margin:0 auto">'
      +   '<h2 style="margin-bottom:16px;font-size:20px;font-weight:600">Consigliere</h2>'
      +   '<div class="card">'
      +     '<div class="card-header">Consigliere Setup</div>'
      +     '<div class="form-group">'
      +       '<label>Question or Topic</label>'
      +       '<textarea class="form-input" id="dl-question" placeholder="Enter an idea to stress-test..." style="min-height:80px"></textarea>'
      +     '</div>'
      +     '<div class="form-group">'
      +       '<label>Reasoning Frames (select 2-6)</label>'
      +       '<div id="dl-frames" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:8px">Loading frames...</div>'
      +     '</div>'
      +     '<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px">'
      +       '<div class="form-group">'
      +         '<label>Critique Rounds</label>'
      +         '<input class="form-input" id="dl-rounds" type="number" value="2" min="0" max="5" />'
      +       '</div>'
      +       '<div class="form-group">'
      +         '<label>Temperature</label>'
      +         '<input class="form-input" id="dl-temperature" type="number" value="0.7" min="0" max="2" step="0.1" />'
      +       '</div>'
      +     '</div>'
      +     '<div style="display:flex;gap:16px;margin-bottom:12px">'
      +       '<label class="toggle"><input type="checkbox" id="dl-rhetoric" checked><span class="toggle-switch"></span><span class="toggle-label">Rhetoric Analysis</span></label>'
      +       '<label class="toggle"><input type="checkbox" id="dl-synthesis" checked><span class="toggle-switch"></span><span class="toggle-label">Synthesis</span></label>'
      +     '</div>'
      +     '<button class="btn btn-primary" id="btn-start-deliberation">Stress-Test Idea</button>'
      +   '</div>'
      +   '<div id="deliberation-output" style="margin-top:24px"></div>'
      + '</div>';

    loadFrames();
    document.getElementById('btn-start-deliberation').addEventListener('click', startDeliberation);

    renderDeliberationPastSessions();
  }

  function authHeaders() {
    var key = typeof API.getApiKey === 'function' ? API.getApiKey() : '';
    return key ? { 'Authorization': 'Bearer ' + key } : {};
  }

  function loadFrames() {
    fetch('/api/v1/agents/deliberation/frames', {
      headers: authHeaders(),
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var frames = data.frames || [];
        var defaults = ['pro_con', 'swot'];
        var el = document.getElementById('dl-frames');
        if (!el) return;
        el.innerHTML = frames.map(function (f) {
          return '<label style="display:flex;align-items:center;gap:8px;background:var(--bg-card);border:1px solid var(--border-color);border-radius:var(--radius-sm);padding:8px 12px;cursor:pointer" title="' + Utils.escapeHtml(f.description || '') + '">'
            + '<input type="checkbox" class="dl-frame-cb" value="' + Utils.escapeHtml(f.frame_id) + '" ' + (defaults.indexOf(f.frame_id) !== -1 ? 'checked' : '') + ' style="flex-shrink:0;accent-color:var(--accent)">'
            + '<span style="font-size:13px;color:var(--text-primary)">' + Utils.escapeHtml(f.label) + '</span>'
            + '</label>';
        }).join('');
      })
      .catch(function () {
        var el = document.getElementById('dl-frames');
        if (el) el.innerHTML = '<span style="color:var(--text-muted);font-size:12px">Failed to load frames</span>';
      });
  }

  function startDeliberation() {
    var question = document.getElementById('dl-question').value.trim();
    if (!question) return alert('Enter a question');

    var selected = Array.from(document.querySelectorAll('.dl-frame-cb:checked')).map(function (cb) { return cb.value; });
    if (selected.length < 2) return alert('Select at least 2 frames');
    if (selected.length > 6) return alert('Maximum 6 frames');

    var rounds = parseInt(document.getElementById('dl-rounds').value) || 2;
    var temperature = parseFloat(document.getElementById('dl-temperature').value) || 0.7;
    var includeRhetoric = document.getElementById('dl-rhetoric').checked;
    var includeSynthesis = document.getElementById('dl-synthesis').checked;

    var btn = document.getElementById('btn-start-deliberation');
    Utils.setButtonLoading(btn, 'Running...');
    Utils.showToast('Consigliere engaged', 'info');

    var output = document.getElementById('deliberation-output');
    output.innerHTML = ''
      + '<div class="card">'
      +   '<div class="card-header">Progress</div>'
      +   '<div style="margin-bottom:12px">'
      +     '<span class="status-dot active" style="width:10px;height:10px"></span>'
      +     '<span id="dl-phase-label" style="margin-left:8px;font-size:13px;color:var(--text-secondary)">Starting...</span>'
      +   '</div>'
      +   '<div id="dl-event-log" style="background:var(--bg-code);border:1px solid var(--border-color);border-radius:var(--radius-sm);padding:12px;max-height:260px;overflow-y:auto;font-family:var(--font-mono);font-size:12px"></div>'
      + '</div>';

    cleanup();

    activeAbortController = new AbortController();

    fetch('/api/v1/agents/deliberation/run', {
      method: 'POST',
      headers: Object.assign({ 'Content-Type': 'application/json' }, authHeaders()),
      body: JSON.stringify({
        question: question,
        frames: selected,
        rounds: rounds,
        temperature: temperature,
        include_rhetoric_analysis: includeRhetoric,
        include_synthesis: includeSynthesis,
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

        function pump() {
          activeReader.read().then(function (result) {
            if (result.done) { resetDeliberation(btn); return; }
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
                  routeDeliberationEvent(currentEvent || 'message', data);
                } catch (_e) {}
                currentEvent = null;
              }
            }
            pump();
          }).catch(function () { resetDeliberation(btn); });
        }
        pump();
      })
      .catch(function (e) {
        if (e.name === 'AbortError') return;
        output.innerHTML = '<div class="alert alert-error">' + Utils.escapeHtml(e.message) + '</div>';
        resetDeliberation(btn);
        Utils.showToast(e.message, 'error');
      });
  }

  function routeDeliberationEvent(eventType, data) {
    switch (eventType) {
      case 'started':
        activeDeliberationId = data.deliberation_id || activeDeliberationId;
        setPhase('Initializing');
        logEvent('Started session: ' + Utils.escapeHtml((data.question || '').substring(0, 80)));
        break;
      case 'phase':
        setPhase(data.phase || data.message || '');
        if (data.message) logEvent(Utils.escapeHtml(data.message));
        break;
      case 'frame_start':
        logEvent('[' + Utils.escapeHtml(data.label || data.frame_id) + '] Generating position (' + data.index + '/' + data.total + ')...');
        break;
      case 'frame_done':
        logEvent('[' + Utils.escapeHtml(data.label || data.frame_id) + '] Position complete');
        break;
      case 'critique_start':
        logEvent('Critique round ' + (data.round || '') + ': ' + Utils.escapeHtml(data.critic || '') + ' reviewing ' + Utils.escapeHtml(data.target || ''));
        break;
      case 'critique_done':
        logEvent('Critique complete: ' + Utils.escapeHtml(data.critic || '') + ' -> ' + Utils.escapeHtml(data.target || ''));
        break;
      case 'rhetoric_start':
        setPhase('Rhetoric Analysis');
        logEvent('Analyzing rhetorical patterns...');
        break;
      case 'rhetoric_done':
        logEvent('Rhetoric analysis complete');
        break;
      case 'completed':
        setPhase('Complete');
        logEvent('Analysis finished. Loading results...');
        loadDeliberationResults(activeDeliberationId);
        Utils.showToast('Consigliere complete', 'success');
        break;
      case 'error':
        logEvent('<span style="color:var(--danger)">Error: ' + Utils.escapeHtml(data.message || data) + '</span>');
        Utils.showToast(data.message || 'Error during analysis', 'error');
        break;
      case 'done':
        break;
    }
  }

  function setPhase(phase) {
    var el = document.getElementById('dl-phase-label');
    if (el) el.textContent = phase;
  }

  function logEvent(msg) {
    var log = document.getElementById('dl-event-log');
    if (!log) return;
    var div = document.createElement('div');
    div.style.cssText = 'padding:2px 0;font-size:12px;color:var(--text-secondary);border-bottom:1px solid var(--border-color)';
    div.innerHTML = msg;
    log.appendChild(div);
    log.scrollTop = log.scrollHeight;
  }

  function loadDeliberationResults(did) {
    if (!did) return;
    fetch('/api/v1/agents/deliberation/' + did, {
      headers: authHeaders(),
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        renderDeliberationResults(data);
      })
      .catch(function (e) {
        logEvent('<span style="color:var(--danger)">Failed to load results: ' + Utils.escapeHtml(e.message) + '</span>');
      });
  }

  function renderDeliberationResults(data) {
    var output = document.getElementById('deliberation-output');
    if (!output) return;

    var framesHtml = '';
    if (data.frames) {
      framesHtml = data.frames.map(function (f) {
        return '<div class="card"><strong style="color:var(--accent)">' + Utils.escapeHtml(f.label || f.frame_id) + '</strong>'
          + '<p style="margin-top:8px;font-size:13px;white-space:pre-wrap">' + Utils.escapeHtml(f.position || '') + '</p>'
          + (f.critique_count ? '<div style="margin-top:8px;font-size:11px;color:var(--text-muted)">Critiques: ' + f.critique_count + '</div>' : '')
          + '</div>';
      }).join('');
    }

    var rhetoricHtml = '';
    if (data.rhetoric_summary) {
      rhetoricHtml = '<div class="card"><div class="card-header">Rhetoric Analysis</div>'
        + '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:8px;font-size:13px">'
        +   '<div>Devices: <strong>' + data.rhetoric_summary.devices + '</strong></div>'
        +   '<div>Biases: <strong>' + data.rhetoric_summary.biases + '</strong></div>'
        +   '<div>Inconsistencies: <strong>' + data.rhetoric_summary.inconsistencies + '</strong></div>'
        +   '<div>Contradictions: <strong>' + data.rhetoric_summary.cross_frame_contradictions + '</strong></div>'
        + '</div></div>';
    }

    var surfaceHtml = '';
    if (data.surface_summary) {
      surfaceHtml = '<div class="card"><div class="card-header">Disagreement Surface</div>'
        + '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:8px;font-size:13px">'
        +   '<div>Agreements: <strong>' + data.surface_summary.agreements + '</strong></div>'
        +   '<div>Disagreements: <strong>' + data.surface_summary.disagreements + '</strong></div>'
        +   '<div>Open Questions: <strong>' + data.surface_summary.open_questions + '</strong></div>'
        + '</div></div>';
    }

    var elapsed = data.elapsed_seconds ? (data.elapsed_seconds.toFixed(1) + 's') : '';

    output.innerHTML = ''
      + '<div class="card"><div class="card-header">Question</div>'
      +   '<p style="font-size:14px">' + Utils.escapeHtml(data.question || '') + '</p>'
      +   (elapsed ? '<div style="margin-top:8px;font-size:11px;color:var(--text-muted)">Completed in ' + elapsed + '</div>' : '')
      + '</div>'
      + framesHtml
      + rhetoricHtml
      + surfaceHtml
      + (data.synthesis_available ? '<div class="card"><div class="card-header">Synthesis</div><p style="font-size:12px;color:var(--text-muted)">Synthesis available — use Export for full details.</p>'
        +   '<button class="btn btn-secondary btn-sm" style="margin-top:8px" data-action="deliberation-export" data-deliberation-id="' + Utils.escapeHtml(activeDeliberationId || '') + '">Export JSON</button></div>' : '')
      + '<button class="btn btn-secondary btn-sm" style="margin-top:8px" data-action="deliberation-new">New Session</button>';

    var exportBtn = output.querySelector('[data-action="deliberation-export"]');
    if (exportBtn) {
      exportBtn.addEventListener('click', function () {
        window.deliberationExport(exportBtn.dataset.deliberationId);
      });
    }
    var newBtn = output.querySelector('[data-action="deliberation-new"]');
    if (newBtn) {
      newBtn.addEventListener('click', function () {
        Router.setActive('deliberation');
      });
    }

    var btn = document.getElementById('btn-start-deliberation');
    if (btn) resetDeliberation(btn);
  }

  window.deliberationExport = function (did) {
    if (!did) return;
    fetch('/api/v1/agents/deliberation/' + did + '/export', {
      headers: authHeaders(),
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        var a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = 'consigliere-' + did + '.json';
        a.click();
      });
  };

  function cleanup() {
    if (activeAbortController) { activeAbortController.abort(); activeAbortController = null; }
    activeReader = null;
    activeDeliberationId = null;
  }

  function resetDeliberation(btn) {
    if (btn) Utils.resetButton(btn);
    activeReader = null;
    activeAbortController = null;
  }

  // Past Sessions
  var deliberationPastLoaded = false;

  function renderDeliberationPastSessions() {
    var output = document.getElementById('deliberation-output');
    if (!output) return;
    output.insertAdjacentHTML('afterend', ''
      + '<div class="card" style="margin-top:24px">'
      +   '<div class="card-header" style="cursor:pointer;display:flex;justify-content:space-between;align-items:center" id="deliberation-past-toggle">'
      +     '<span>Past Sessions</span>'
      +     '<span id="deliberation-past-arrow" style="font-size:12px">&#x25BC;</span>'
      +   '</div>'
      +   '<div id="deliberation-past-sessions" style="display:none;padding:8px 0">'
      +     '<div style="text-align:center;padding:12px;color:var(--text-muted)">Loading...</div>'
      +   '</div>'
      + '</div>'
    );

    document.getElementById('deliberation-past-toggle').addEventListener('click', function () {
      var body = document.getElementById('deliberation-past-sessions');
      var arrow = document.getElementById('deliberation-past-arrow');
      if (body.style.display === 'none') {
        body.style.display = 'block';
        arrow.innerHTML = '&#x25B2;';
        if (!deliberationPastLoaded) {
          deliberationPastLoaded = true;
          loadDeliberationPastSessions();
        }
      } else {
        body.style.display = 'none';
        arrow.innerHTML = '&#x25BC;';
      }
    });
  }

  function loadDeliberationPastSessions() {
    var body = document.getElementById('deliberation-past-sessions');
    API.listSessions('deliberation').then(function (sessions) {
      if (!sessions || sessions.length === 0) {
        body.innerHTML = '<div style="text-align:center;padding:12px;color:var(--text-muted);font-size:12px">No past sessions</div>';
        return;
      }
      var recent = sessions.slice(0, 10);
      body.innerHTML = recent.map(function (s) {
        var date = s.created_at ? s.created_at.split('T')[0] : '';
        var title = Utils.escapeHtml((s.title || 'Consigliere session').length > 60 ? s.title.substring(0, 57) + '...' : s.title || 'Consigliere session');
        return '<div style="display:flex;justify-content:space-between;align-items:center;padding:8px 12px;border-bottom:1px solid var(--border-color);cursor:pointer" data-session-id="' + s.id + '" class="deliberation-past-item">'
          + '<span style="font-size:12px;color:var(--text-muted);flex-shrink:0;margin-right:12px">' + date + '</span>'
          + '<span style="font-size:13px;flex:1">' + title + '</span>'
          + '<span style="font-size:11px;color:var(--text-muted);flex-shrink:0">' + (s.word_count || 0) + ' words</span>'
          + '</div>';
      }).join('');
      body.querySelectorAll('.deliberation-past-item').forEach(function (el) {
        el.addEventListener('click', function () {
          loadPastDeliberationSession(el.dataset.sessionId);
        });
      });
    }).catch(function () {
      body.innerHTML = '<div style="text-align:center;padding:12px;color:var(--danger);font-size:12px">Failed to load sessions</div>';
    });
  }

  function loadPastDeliberationSession(id) {
    var output = document.getElementById('deliberation-output');
    output.innerHTML = '<div style="text-align:center;padding:24px;color:var(--text-muted)">Loading session...</div>';
    API.getSession(id).then(function (session) {
      var content = session.content || '{}';
      var data;
      try { data = JSON.parse(content); } catch (_e) { data = { question: session.title || 'Consigliere session' }; }
      data.question = data.question || session.title || 'Consigliere session';
      renderDeliberationResults(data);
    }).catch(function (e) {
      output.innerHTML = '<div class="alert alert-error">' + Utils.escapeHtml(e.message) + '</div>';
    });
  }
})();
