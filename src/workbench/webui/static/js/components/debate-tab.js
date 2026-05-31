/** Debate Agent Tab Component
 * Multi-agent AI debate with Director Mode and real-time polling.
 */

(function () {
  var activeDebateId = null;
  var pollTimer = null;

  Router.register("debate", renderDebateTab);

  function renderDebateTab(container) {
    stopPolling();

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

  function loadRoles() {
    fetch('/api/v1/agents/debate/roles', {
      headers: { 'Authorization': 'Bearer ' + API.getApiKey() },
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var roles = data.roles || [];
        var defaults = ['optimist', 'pessimist', 'pragmatist'];
        var el = document.getElementById('debate-roles');
        if (!el) return;
        el.innerHTML = roles.map(function (r) {
          return '<label class="toggle" style="background:var(--bg-card);border:1px solid var(--border-color);border-radius:var(--radius-sm);padding:8px 12px">'
            + '<input type="checkbox" class="debate-role-cb" value="' + Utils.escapeHtml(r.id) + '" ' + (defaults.indexOf(r.id) !== -1 ? 'checked' : '') + '>'
            + '<span class="toggle-switch"></span>'
            + '<span class="toggle-label" title="' + Utils.escapeHtml(r.description || '') + '">' + Utils.escapeHtml(r.name) + '</span>'
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
      headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + API.getApiKey() },
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
    activeDebateId = null;
  }

  function fetchDebateStatus() {
    if (!activeDebateId) return;
    fetch('/api/v1/agents/debate/debate/' + activeDebateId + '/status', {
      headers: { 'Authorization': 'Bearer ' + API.getApiKey() },
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        updateDebatePanel(data);
        if (data.status === 'COMPLETED' || data.status === 'PAUSED') {
          stopPolling();
          activeDebateId = data.debate_id;
          resetDebateButton();
        }
      })
      .catch(function () {
        stopPolling();
        resetDebateButton();
      });
  }

  function renderProgressPanel(topic, roundsCompleted, maxRounds, status) {
    var statusClass = status === 'COMPLETED' ? 'active' : (status === 'PAUSED' ? 'inactive' : 'active');
    var progressPct = maxRounds > 0 ? Math.round((roundsCompleted / maxRounds) * 100) : 0;
    return ''
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
      +     '<button class="btn btn-secondary btn-sm" onclick="Router.setActive(\'debate\')">New Debate</button>'
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
      + '</div>';
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
    var prevSender = null;
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
    var content = document.getElementById('inject-content').value.trim();
    if (!content) return;
    var weight = parseFloat(document.getElementById('inject-weight').value) || 0.5;
    fetch('/api/v1/agents/debate/debate/' + activeDebateId + '/inject', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + API.getApiKey() },
      body: JSON.stringify({ content: content, weight: weight }),
    })
      .then(function () { document.getElementById('inject-content').value = ''; })
      .catch(function (e) { alert('Inject failed: ' + e.message); });
  };

  window.debatePause = function () {
    if (!activeDebateId) return;
    fetch('/api/v1/agents/debate/debate/' + activeDebateId + '/pause', {
      method: 'POST',
      headers: { 'Authorization': 'Bearer ' + API.getApiKey() },
    }).then(function () {
      fetchDebateStatus();
    }).catch(function () {});
  };

  window.debateResume = function () {
    if (!activeDebateId) return;
    fetch('/api/v1/agents/debate/debate/' + activeDebateId + '/resume', {
      method: 'POST',
      headers: { 'Authorization': 'Bearer ' + API.getApiKey() },
    }).then(function () {
      startPolling();
    }).catch(function () {});
  };

  function resetDebateButton() {
    var btn = document.getElementById('btn-start-debate');
    if (btn) { btn.disabled = false; btn.textContent = 'Start Debate'; }
  }
})();
