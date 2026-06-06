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
      +       '<input class="form-input" id="debate-topic" placeholder="Enter a topic to debate..." />'
      +     '</div>'
      +     '<div class="form-group">'
      +       '<label>Max Rounds</label>'
      +       '<input class="form-input" id="debate-rounds" type="number" value="3" min="1" max="10" />'
      +     '</div>'
      +     '<div class="form-group">'
      +       '<label>Panel (select 2-8 roles)</label>'
      +       '<div id="debate-roles" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:8px">Loading roles...</div>'
      +     '</div>'
      +     '<button class="btn btn-primary" id="btn-start-debate">Start Debate</button>'
      +   '</div>'
      +   '<div id="debate-output" style="margin-top:24px"></div>'
      + '</div>';

    loadRoles();
    document.getElementById('btn-start-debate').addEventListener('click', startDebate);
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
          return '<label style="display:flex;align-items:center;gap:8px;background:var(--bg-card);border:1px solid var(--border-color);border-radius:var(--radius-sm);padding:8px 12px;cursor:pointer" title="' + Utils.escapeHtml(r.description || '') + '">'
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
    btn.disabled = true;
    btn.textContent = 'Starting...';

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
        startPolling();
      })
      .catch(function (e) {
        output.innerHTML = '<div class="alert alert-error">' + Utils.escapeHtml(e.message) + '</div>';
        btn.disabled = false;
        btn.textContent = 'Start Debate';
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
          resetDebateButton();
        }
      })
      .catch(function () {
        stopPolling();
        resetDebateButton();
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
      +     '<button class="btn btn-warning btn-sm" id="btn-pause-debate" onclick="window.debatePause()">Pause</button>'
      +     '<button class="btn btn-success btn-sm" id="btn-resume-debate" onclick="window.debateResume()" disabled>Resume</button>'
      +     '<button class="btn btn-danger btn-sm" id="btn-end-debate" onclick="window.debateEnd()">End Debate</button>'
      +   '</div>'
      +   '<div id="debate-director-panel" style="margin-top:16px;padding-top:12px;border-top:1px solid var(--border-color)">'
      +     '<div style="font-size:12px;font-weight:600;margin-bottom:8px;color:var(--text-secondary)">Director Mode</div>'
      +     '<div style="display:flex;gap:8px;align-items:flex-end">'
      +       '<input class="form-input" id="inject-content" placeholder="Inject a message..." style="flex:1" />'
      +       '<div style="min-width:120px">'
      +         '<label style="font-size:10px;color:var(--text-muted)">Weight</label>'
      +         '<input class="form-input" id="inject-weight" type="number" value="0.5" min="0" max="1" step="0.1" style="padding:4px 8px" />'
      +       '</div>'
      +       '<button class="btn btn-primary btn-sm" onclick="window.debateInject()">Inject</button>'
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
    if (btnPause) btnPause.disabled = data.status !== 'RUNNING';
    if (btnResume) btnResume.disabled = data.status !== 'PAUSED';

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

  window.debateInject = function () {
    if (!activeDebateId) return;
    var content = document.getElementById('inject-content');
    if (!content) return;
    content = content.value.trim();
    if (!content) return;
    var weight = parseFloat(document.getElementById('inject-weight').value) || 0.5;
    fetch('/api/v1/agents/debate/debate/' + activeDebateId + '/inject', {
      method: 'POST',
      headers: Object.assign({ 'Content-Type': 'application/json' }, authHeaders()),
      body: JSON.stringify({ content: content, weight: weight }),
    })
      .then(function () { document.getElementById('inject-content').value = ''; })
      .catch(function (e) { alert('Inject failed: ' + e.message); });
  };

  window.debatePause = function () {
    if (!activeDebateId) return;
    fetch('/api/v1/agents/debate/debate/' + activeDebateId + '/pause', {
      method: 'POST',
      headers: authHeaders(),
    }).then(function () {
      fetchDebateStatus();
    }).catch(function () {});
  };

  window.debateResume = function () {
    if (!activeDebateId) return;
    fetch('/api/v1/agents/debate/debate/' + activeDebateId + '/resume', {
      method: 'POST',
      headers: authHeaders(),
    }).then(function () {
      startPolling();
    }).catch(function () {});
  };

  window.debateEnd = function () {
    stopPolling();
    activeDebateId = null;
    Router.setActive('debate');
  };

  function resetDebateButton() {
    var btn = document.getElementById('btn-start-debate');
    if (btn) { btn.disabled = false; btn.textContent = 'Start Debate'; }
  }
})();
