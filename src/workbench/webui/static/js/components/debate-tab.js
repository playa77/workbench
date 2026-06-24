/** Debate Agent Tab Component
 * Multi-agent AI debate with Director Mode and real-time polling.
 * State persists across tab switches via persistent tab panels.
 */

(function () {
  var activeDebateId = null;
  var pollTimer = null;

  Router.register("debate", renderDebateTab);

  function renderDebateTab(container) {
    if (activeDebateId) {
      var savedId = activeDebateId;
      container.innerHTML = '<div style="max-width:900px;margin:0 auto" id="debate-restored"><div class="spinner" style="margin:40px auto"></div></div>';
      fetchDebateStatusOnce(savedId).then(function (data) {
        var out = document.getElementById('debate-restored');
        if (out && data) {
          out.outerHTML = renderDebatePanel(data);
          if (data.status === 'RUNNING') startPolling();
          bindDebateButtons(data.debate_id);
        }
      });
      return;
    }

    container.innerHTML = ''
      + '<div style="max-width:900px;margin:0 auto">'
      +   '<h2 style="margin-bottom:16px;font-size:20px;font-weight:600">Debate Arena</h2>'
      +   '<div class="card">'
      +     '<div class="card-header">Debate Setup</div>'
      +     '<div class="form-group">'
      +       '<label>Topic</label>'
      +       '<input class="form-input" id="debate-topic" placeholder="Enter a topic to debate..." data-tooltip="Enter the topic or question to debate. Be specific — quality depends on a well-formed prompt." data-help-page="/static/help/debate.html#topic" />'
      +     '</div>'
      +     '<div class="form-group">'
      +       '<label>Max Rounds</label>'
      +       '<input class="form-input" id="debate-rounds" type="number" value="3" min="1" max="10" data-tooltip="Number of debate rounds (1–10). More rounds produce deeper analysis but take longer. Default: 3." data-help-page="/static/help/debate.html#max-rounds" />'
      +     '</div>'
      +     '<div class="form-group">'
      +       '<label>Panel (select 2-8 roles)</label>'
      +       '<div id="debate-roles" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:8px">Loading roles...</div>'
      +     '</div>'
      +     '<button class="btn btn-primary" id="btn-start-debate" data-tooltip="Begin the debate. The button shows loading state while agents initialize. Progress updates every few seconds." data-help-page="/static/help/debate.html#start-debate">Start Debate</button>'
      +   '</div>'
      +   '<div id="debate-output" style="margin-top:24px"></div>'
      + '</div>';

    loadRoles();
    document.getElementById('btn-start-debate').addEventListener('click', startDebate);

    renderDebatePastSessions();
  }

  function authHeaders() {
    var key = typeof API.getApiKey === 'function' ? API.getApiKey() : '';
    return key ? { 'Authorization': 'Bearer ' + key } : {};
  }

  function loadRoles() {
    fetch('/api/v1/agents/debate/roles', {
      headers: authHeaders(),
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var roles = data.roles || [];
        var defaults = ['optimist', 'pessimist', 'pragmatist'];
        var el = document.getElementById('debate-roles');
        if (!el) return;
        el.innerHTML = roles.map(function (r) {
          return '<label style="display:flex;align-items:center;gap:8px;background:var(--bg-card);border:1px solid var(--border-color);border-radius:var(--radius-sm);padding:8px 12px;cursor:pointer" title="' + Utils.escapeHtml(r.description || '') + '" data-tooltip="Select this role for the debate panel. Each role argues from a distinct perspective.">'
            + '<input type="checkbox" class="debate-role-cb" value="' + Utils.escapeHtml(r.id) + '" ' + (defaults.indexOf(r.id) !== -1 ? 'checked' : '') + ' style="flex-shrink:0;accent-color:var(--accent)">'
            + '<span style="font-size:13px;color:var(--text-primary)">' + Utils.escapeHtml(r.name) + '</span>'
            + '</label>';
        }).join('');
      })
      .catch(function () {
        var el = document.getElementById('debate-roles');
        if (el) el.innerHTML = '<span style="color:var(--text-muted);font-size:12px">Failed to load roles</span>';
      });
  }

  function startDebate() {
    var topic = document.getElementById('debate-topic').value.trim();
    if (!topic) return alert('Enter a topic');

    var selected = Array.from(document.querySelectorAll('.debate-role-cb:checked')).map(function (cb) { return cb.value; });
    if (selected.length < 2) return alert('Select at least 2 roles');
    if (selected.length > 8) return alert('Maximum 8 roles');

    var maxRounds = parseInt(document.getElementById('debate-rounds').value) || 3;

    var btn = document.getElementById('btn-start-debate');
    Utils.setButtonLoading(btn, 'Starting...');
    Utils.showToast('Debate started', 'info');

    var output = document.getElementById('debate-output');
    output.innerHTML = renderProgressPanel(topic, 0, maxRounds, 'RUNNING');

    fetch('/api/v1/agents/debate/start', {
      method: 'POST',
      headers: Object.assign({ 'Content-Type': 'application/json' }, authHeaders()),
      body: JSON.stringify({ topic: topic, roles: selected, max_rounds: maxRounds }),
    })
      .then(function (resp) { return resp.json(); })
      .then(function (data) {
        if (!data.debate_id) throw new Error(data.detail || 'Failed to start debate');
        activeDebateId = data.debate_id;
        btn.textContent = 'Debating...';
        btn.classList.add('btn-pulse');
        startPolling();
      })
      .catch(function (e) {
        output.innerHTML = '<div class="alert alert-error">' + Utils.escapeHtml(e.message) + '</div>';
        Utils.resetButton(btn);
        Utils.showToast(e.message, 'error');
      });
  }

  function startPolling() {
    stopPolling();
    pollTimer = setInterval(fetchDebateStatus, 1500);
    fetchDebateStatus();
  }

  function stopPolling() {
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
  }

  function fetchDebateStatus() {
    if (!activeDebateId) return;
    fetch('/api/v1/agents/debate/debate/' + activeDebateId + '/status', {
      headers: authHeaders(),
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        updateDebatePanel(data);
        if (data.status === 'COMPLETED' || data.status === 'PAUSED') {
          stopPolling();
          var btn = document.getElementById('btn-start-debate');
          if (data.status === 'COMPLETED') {
            if (btn) { btn.classList.remove('btn-pulse'); btn.textContent = 'Start Debate'; btn.disabled = false; }
            Utils.showToast('Debate complete', 'success');
          } else {
            resetDebateButton();
          }
        }
      })
      .catch(function () {
        stopPolling();
        resetDebateButton();
        Utils.showToast('Lost connection to debate', 'error');
      });
  }

  function fetchDebateStatusOnce(debateId) {
    return fetch('/api/v1/agents/debate/debate/' + debateId + '/status', {
      headers: authHeaders(),
    })
      .then(function (r) { return r.json(); })
      .catch(function () { return null; });
  }

  function renderDebatePanel(data) {
    var topic = data.topic || '';
    var maxRounds = data.max_rounds || 0;
    var roundsCompleted = data.rounds_completed || 0;
    var status = data.status || 'IDLE';
    return renderProgressPanel(topic, roundsCompleted, maxRounds, status);
  }

  function renderProgressPanel(topic, roundsCompleted, maxRounds, status) {
    var statusClass = status === 'COMPLETED' ? 'active' : (status === 'PAUSED' ? 'inactive' : 'active');
    var progressPct = maxRounds > 0 ? Math.round((roundsCompleted / maxRounds) * 100) : 0;
    return ''
      + '<div style="max-width:900px;margin:0 auto" id="debate-active-panel">'
      + '<h2 style="margin-bottom:16px;font-size:20px;font-weight:600">Debate Arena</h2>'
      + '<div class="card">'
      +   '<div class="card-header" style="display:flex;justify-content:space-between;align-items:center">'
      +     '<span>' + Utils.escapeHtml(topic) + '</span>'
      +     '<span class="status-dot ' + statusClass + '" style="width:10px;height:10px" title="' + Utils.escapeHtml(status) + '"></span>'
      +   '</div>'
      +   '<div style="display:flex;gap:16px;margin-bottom:12px;font-size:12px;color:var(--text-secondary)">'
      +     '<span>Rounds: <strong>' + roundsCompleted + '/' + maxRounds + '</strong></span>'
      +     '<span>Status: <strong id="debate-status-label">' + Utils.escapeHtml(status) + '</strong></span>'
      +     '<span id="debate-speaker-label" style="color:var(--text-muted)"></span>'
      +   '</div>'
      +   '<div style="height:4px;background:var(--border-color);border-radius:2px;margin-bottom:16px">'
      +     '<div id="debate-progress-bar" style="height:100%;width:' + progressPct + '%;background:var(--accent);border-radius:2px;transition:width 0.3s"></div>'
      +   '</div>'
      +   '<div id="debate-transcript" style="max-height:50vh;overflow-y:auto">'
      +     '<p style="color:var(--text-muted);font-size:12px">Waiting for debate to begin...</p>'
      +   '</div>'
      +   '<div style="margin-top:12px;display:flex;gap:8px;flex-wrap:wrap">'
      +     '<button class="btn btn-warning btn-sm" id="btn-pause-debate" onclick="window.debatePause(this)" data-tooltip="Temporarily halt the debate mid-round. Agents stop responding until resumed." data-help-page="/static/help/debate.html#debate-controls">Pause</button>'
      +     '<button class="btn btn-success btn-sm" id="btn-resume-debate" onclick="window.debateResume(this)" disabled data-tooltip="Continue a paused debate from where it left off. Agents continue from the current round." data-help-page="/static/help/debate.html#debate-controls">Resume</button>'
      +     '<button class="btn btn-danger btn-sm" id="btn-end-debate" onclick="window.debateEnd()" data-tooltip="Terminate the debate early and finalize results. Becomes 'Back to Setup' after completion." data-help-page="/static/help/debate.html#debate-controls">End Debate</button>'
      +   '</div>'
      +   '<div id="debate-director-panel" style="margin-top:16px;padding-top:12px;border-top:1px solid var(--border-color)">'
      +     '<div style="font-size:12px;font-weight:600;margin-bottom:8px;color:var(--text-secondary)">Director Mode</div>'
      +     '<div style="display:flex;gap:8px;align-items:flex-end">'
      +       '<input class="form-input" id="inject-content" placeholder="Inject a message..." style="flex:1" data-tooltip="Enter content to inject into the debate. This text will be included in the next round's responses." data-help-page="/static/help/debate.html#director-mode" />'
      +       '<div style="min-width:120px">'
      +         '<label style="font-size:10px;color:var(--text-muted)">Weight</label>'
      +         '<input class="form-input" id="inject-weight" type="number" value="0.5" min="0" max="1" step="0.1" style="padding:4px 8px" data-tooltip="Weight of injected content (1–10). Higher values make the injected content more influential." data-help-page="/static/help/debate.html#director-mode" />'
      +       '</div>'
      +       '<button class="btn btn-primary btn-sm" onclick="window.debateInject(this)" data-tooltip="Insert the Director Mode content into the active debate at the specified weight." data-help-page="/static/help/debate.html#director-mode">Inject</button>'
      +     '</div>'
      +   '</div>'
      + '</div>'
      + '</div>';
  }

  function bindDebateButtons(debateId) {
    activeDebateId = debateId;
  }

  function updateDebatePanel(data) {
    var el = document.getElementById('debate-status-label');
    if (el) el.textContent = data.status;

    var spk = document.getElementById('debate-speaker-label');
    if (spk && data.current_speaker) spk.textContent = 'Speaking: ' + data.current_speaker;
    if (spk && !data.current_speaker) spk.textContent = '';

    var bar = document.getElementById('debate-progress-bar');
    if (bar) {
      var pct = data.max_rounds > 0 ? Math.round((data.rounds_completed / data.max_rounds) * 100) : 0;
      bar.style.width = pct + '%';
    }

    var btnPause = document.getElementById('btn-pause-debate');
    var btnResume = document.getElementById('btn-resume-debate');
    var btnEnd = document.getElementById('btn-end-debate');
    if (btnPause) btnPause.disabled = data.status !== 'RUNNING';
    if (btnResume) btnResume.disabled = data.status !== 'PAUSED';
    if (btnEnd) {
      if (data.status === 'COMPLETED') {
        btnEnd.textContent = 'Back to Setup';
        btnEnd.className = 'btn btn-secondary btn-sm';
        btnEnd.onclick = function () { window.debateEnd(); };
      }
    }

    var transcript = document.getElementById('debate-transcript');
    if (!transcript || !data.history) return;

    var html = '';
    data.history.forEach(function (msg) {
      if (msg.is_injection) {
        html += '<div style="padding:8px 12px;margin-bottom:8px;background:var(--warning-bg);border-left:3px solid var(--warning);border-radius:var(--radius-sm)">'
          + '<div style="font-size:10px;text-transform:uppercase;color:var(--warning);font-weight:600;margin-bottom:4px">Director</div>'
          + '<div style="font-size:12px;white-space:pre-wrap;color:var(--text-primary)">' + Utils.escapeHtml(msg.content) + '</div>'
          + '</div>';
      } else {
        html += '<div style="padding:6px 0;border-bottom:1px solid var(--border-color)">'
          + '<strong style="color:var(--accent);font-size:12px">' + Utils.escapeHtml(msg.sender) + '</strong>'
          + '<p style="margin-top:4px;font-size:12px;white-space:pre-wrap">' + Utils.escapeHtml(msg.content) + '</p>'
          + '</div>';
      }
    });

    var wasAtBottom = transcript.scrollHeight - transcript.scrollTop - transcript.clientHeight < 60;
    transcript.innerHTML = html || '<p style="color:var(--text-muted);font-size:12px">Waiting...</p>';
    if (wasAtBottom) transcript.scrollTop = transcript.scrollHeight;
  }

  window.debateInject = function (btn) {
    if (!activeDebateId) return;
    var content = document.getElementById('inject-content');
    if (!content) return;
    content = content.value.trim();
    if (!content) return;
    var weight = parseFloat(document.getElementById('inject-weight').value) || 0.5;
    Utils.setButtonLoading(btn, 'Sending...');
    fetch('/api/v1/agents/debate/debate/' + activeDebateId + '/inject', {
      method: 'POST',
      headers: Object.assign({ 'Content-Type': 'application/json' }, authHeaders()),
      body: JSON.stringify({ content: content, weight: weight }),
    })
      .then(function () { document.getElementById('inject-content').value = ''; Utils.resetButton(btn); })
      .catch(function (e) { Utils.showToast('Inject failed: ' + e.message, 'error'); });
  };

  window.debatePause = function (btn) {
    if (!activeDebateId) return;
    Utils.setButtonLoading(btn, 'Pausing...');
    fetch('/api/v1/agents/debate/debate/' + activeDebateId + '/pause', {
      method: 'POST',
      headers: authHeaders(),
    }).then(function () {
      fetchDebateStatus();
    }).catch(function () {
      Utils.resetButton(btn);
    });
  };

  window.debateResume = function (btn) {
    if (!activeDebateId) return;
    Utils.setButtonLoading(btn, 'Resuming...');
    fetch('/api/v1/agents/debate/debate/' + activeDebateId + '/resume', {
      method: 'POST',
      headers: authHeaders(),
    }).then(function () {
      startPolling();
    }).catch(function () {
      Utils.resetButton(btn);
    });
  };

  window.debateEnd = function () {
    stopPolling();
    activeDebateId = null;
    Router.setActive('debate');
  };

  function resetDebateButton() {
    var btn = document.getElementById('btn-start-debate');
    if (btn) { btn.classList.remove('btn-pulse'); Utils.resetButton(btn); }
  }

  // Past Debate Sessions
  var debatePastLoaded = false;

  function renderDebatePastSessions() {
    var output = document.getElementById('debate-output');
    if (!output) return;
    output.insertAdjacentHTML('afterend', ''
      + '<div class="card" style="margin-top:24px">'
      +   '<div class="card-header" style="cursor:pointer;display:flex;justify-content:space-between;align-items:center" id="debate-past-toggle" data-tooltip="Click to expand or collapse the list of previous debate sessions. Click a session to reload." data-help-page="/static/help/debate.html#past-debates">'
      +     '<span>Past Debate Sessions</span>'
      +     '<span id="debate-past-arrow" style="font-size:12px">&#x25BC;</span>'
      +   '</div>'
      +   '<div id="debate-past-sessions" style="display:none;padding:8px 0">'
      +     '<div style="text-align:center;padding:12px;color:var(--text-muted)">Loading...</div>'
      +   '</div>'
      + '</div>'
    );

    document.getElementById('debate-past-toggle').addEventListener('click', function () {
      var body = document.getElementById('debate-past-sessions');
      var arrow = document.getElementById('debate-past-arrow');
      if (body.style.display === 'none') {
        body.style.display = 'block';
        arrow.innerHTML = '&#x25B2;';
        if (!debatePastLoaded) {
          debatePastLoaded = true;
          loadDebatePastSessions();
        }
      } else {
        body.style.display = 'none';
        arrow.innerHTML = '&#x25BC;';
      }
    });
  }

  function loadDebatePastSessions() {
    var body = document.getElementById('debate-past-sessions');
    API.listSessions('debate').then(function (sessions) {
      if (!sessions || sessions.length === 0) {
        body.innerHTML = '<div style="text-align:center;padding:12px;color:var(--text-muted);font-size:12px">No past debate sessions</div>';
        return;
      }
      var recent = sessions.slice(0, 10);
      body.innerHTML = recent.map(function (s) {
        var date = s.created_at ? s.created_at.split('T')[0] : '';
        var title = Utils.escapeHtml((s.title || 'Debate').length > 60 ? s.title.substring(0, 57) + '...' : s.title || 'Debate');
        return '<div style="display:flex;justify-content:space-between;align-items:center;padding:8px 12px;border-bottom:1px solid var(--border-color);cursor:pointer" data-session-id="' + s.id + '" class="debate-past-item">'
          + '<span style="font-size:12px;color:var(--text-muted);flex-shrink:0;margin-right:12px">' + date + '</span>'
          + '<span style="font-size:13px;flex:1">' + title + '</span>'
          + '<span style="font-size:11px;color:var(--text-muted);flex-shrink:0">' + (s.word_count || 0) + ' words</span>'
          + '</div>';
      }).join('');
      body.querySelectorAll('.debate-past-item').forEach(function (el) {
        el.addEventListener('click', function () {
          loadPastDebateSession(el.dataset.sessionId);
        });
      });
    }).catch(function () {
      body.innerHTML = '<div style="text-align:center;padding:12px;color:var(--danger);font-size:12px">Failed to load sessions</div>';
    });
  }

  function loadPastDebateSession(id) {
    stopPolling();
    activeDebateId = null;
    var container = document.getElementById('active-tab-content');
    if (!container) return;
    container.innerHTML = '<div style="max-width:900px;margin:0 auto"><div style="text-align:center;padding:40px;color:var(--text-muted)">Loading debate session...</div></div>';
    API.getSession(id).then(function (session) {
      var content = session.content || '{}';
      var data;
      try { data = JSON.parse(content); } catch (_e) { data = { topic: session.title || 'Debate', history: [] }; }
      data.topic = data.topic || session.title || 'Debate';
      data.max_rounds = data.max_rounds || 0;
      data.rounds_completed = data.rounds_completed || 0;
      data.status = 'COMPLETED';
      var panel = renderProgressPanel(data.topic, data.rounds_completed, data.max_rounds, 'COMPLETED');
      container.innerHTML = panel;
      if (data.history) {
        var transcript = document.getElementById('debate-transcript');
        if (transcript) {
          transcript.innerHTML = data.history.map(function (msg) {
            if (msg.is_injection) {
              return '<div style="padding:8px 12px;margin-bottom:8px;background:var(--warning-bg);border-left:3px solid var(--warning);border-radius:var(--radius-sm)">'
                + '<div style="font-size:10px;text-transform:uppercase;color:var(--warning);font-weight:600;margin-bottom:4px">Director</div>'
                + '<div style="font-size:12px;white-space:pre-wrap;color:var(--text-primary)">' + Utils.escapeHtml(msg.content) + '</div></div>';
            }
            return '<div style="padding:6px 0;border-bottom:1px solid var(--border-color)">'
              + '<strong style="color:var(--accent);font-size:12px">' + Utils.escapeHtml(msg.sender) + '</strong>'
              + '<p style="margin-top:4px;font-size:12px;white-space:pre-wrap">' + Utils.escapeHtml(msg.content) + '</p></div>';
          }).join('');
        }
      }
      var pauseBtn = document.getElementById('btn-pause-debate');
      var resumeBtn = document.getElementById('btn-resume-debate');
      var endBtn = document.getElementById('btn-end-debate');
      if (pauseBtn) pauseBtn.style.display = 'none';
      if (resumeBtn) resumeBtn.style.display = 'none';
      if (endBtn) endBtn.style.display = 'none';
    }).catch(function (e) {
      container.innerHTML = '<div class="alert alert-error">' + Utils.escapeHtml(e.message) + '</div>';
    });
  }
})();
