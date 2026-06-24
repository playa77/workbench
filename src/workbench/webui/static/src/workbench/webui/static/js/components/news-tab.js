/* News Agent Tab Component */

(function () {
  Router.register("news", renderNewsTab);

  async function renderNewsTab(container) {
    container.innerHTML = `
      <h2 style="margin-bottom:24px;font-size:20px;font-weight:600">News Pipeline</h2>
      <div id="news-content">
        <div class="spinner" style="margin:40px auto"></div>
      </div>`;

    await loadInterests();

    renderNewsPastSessions();
  }

  // Past News Sessions
  var newsPastLoaded = false;

  function renderNewsPastSessions() {
    var content = document.getElementById('news-content');
    if (!content) return;
    content.insertAdjacentHTML('afterend', ''
      + '<div class="card" style="margin-top:24px">'
      +   '<div class="card-header" style="cursor:pointer;display:flex;justify-content:space-between;align-items:center" id="news-past-toggle">'
      +     '<span>Past News Sessions</span>'
      +     '<span id="news-past-arrow" style="font-size:12px">&#x25BC;</span>'
      +   '</div>'
      +   '<div id="news-past-sessions" style="display:none;padding:8px 0">'
      +     '<div style="text-align:center;padding:12px;color:var(--text-muted)">Loading...</div>'
      +   '</div>'
      + '</div>'
    );

    document.getElementById('news-past-toggle').addEventListener('click', function () {
      var body = document.getElementById('news-past-sessions');
      var arrow = document.getElementById('news-past-arrow');
      if (body.style.display === 'none') {
        body.style.display = 'block';
        arrow.innerHTML = '&#x25B2;';
        if (!newsPastLoaded) {
          newsPastLoaded = true;
          loadNewsPastSessions();
        }
      } else {
        body.style.display = 'none';
        arrow.innerHTML = '&#x25BC;';
      }
    });
  }

  function loadNewsPastSessions() {
    var body = document.getElementById('news-past-sessions');
    API.listSessions('news').then(function (sessions) {
      if (!sessions || sessions.length === 0) {
        body.innerHTML = '<div style="text-align:center;padding:12px;color:var(--text-muted);font-size:12px">No past news sessions</div>';
        return;
      }
      var recent = sessions.slice(0, 10);
      body.innerHTML = recent.map(function (s) {
        var date = s.created_at ? s.created_at.split('T')[0] : '';
        var title = Utils.escapeHtml((s.title || 'News').length > 60 ? s.title.substring(0, 57) + '...' : s.title || 'News');
        return '<div style="display:flex;justify-content:space-between;align-items:center;padding:8px 12px;border-bottom:1px solid var(--border-color);cursor:pointer" data-session-id="' + s.id + '" class="news-past-item">'
          + '<span style="font-size:12px;color:var(--text-muted);flex-shrink:0;margin-right:12px">' + date + '</span>'
          + '<span style="font-size:13px;flex:1">' + title + '</span>'
          + '<span style="font-size:11px;color:var(--text-muted);flex-shrink:0">' + (s.word_count || 0) + ' words</span>'
          + '</div>';
      }).join('');
      body.querySelectorAll('.news-past-item').forEach(function (el) {
        el.addEventListener('click', function () {
          loadPastNewsSession(el.dataset.sessionId);
        });
      });
    }).catch(function () {
      body.innerHTML = '<div style="text-align:center;padding:12px;color:var(--danger);font-size:12px">Failed to load sessions</div>';
    });
  }

  function loadPastNewsSession(id) {
    var container = document.getElementById('active-tab-content');
    if (!container) return;
    container.innerHTML = '<div style="max-width:900px;margin:0 auto"><div style="text-align:center;padding:40px;color:var(--text-muted)">Loading news session...</div></div>';
    API.getSession(id).then(function (session) {
      var md = Utils.escapeHtml(session.content || '')
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

      container.innerHTML = ''
        + '<div style="max-width:900px;margin:0 auto">'
        + '<div style="padding:8px 0">'
        + '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px">'
        + '<h3 style="margin:0;font-size:16px;font-weight:600">' + Utils.escapeHtml(session.title || 'News Session') + '</h3>'
        + '<button class="btn btn-secondary btn-sm" onclick="javascript:Router.setActive(\'news\')">Back to News</button>'
        + '</div>'
        + '<div style="line-height:1.7;font-size:13px;background:var(--bg-card);border:1px solid var(--border-color);border-radius:var(--radius-sm);padding:20px">'
        + '<p style="margin-bottom:8px;line-height:1.7">' + md + '</p>'
        + '</div>'
        + '</div>'
        + '</div>';
    }).catch(function (e) {
      container.innerHTML = '<div class="alert alert-error">' + Utils.escapeHtml(e.message) + '</div>';
    });
  }

  async function loadInterests() {
    try {
      const data = await fetch('/api/v1/agents/news/interests', { headers: authHeaders() }).then(r => r.json());
      const interests = data.interests || [];
      const content = document.getElementById('news-content');

      if (interests.length === 0) {
        content.innerHTML = `
          <div class="card">
            <div class="card-header">No Interests Configured</div>
            <p style="color:var(--text-muted);font-size:13px;margin-bottom:12px">Create your first news interest to start monitoring AI news.</p>
            ${renderInterestForm()}
          </div>`;
        bindInterestForm();
        return;
      }

      var html = interests.map(function (i) { return `
        <div class="card">
          <div class="card-header" style="display:flex;justify-content:space-between;align-items:center">
            <span>${Utils.escapeHtml(i.name)}</span>
            <div style="display:flex;gap:8px">
              <button class="btn btn-primary btn-sm" onclick="window.newsTriggerRun(${i.id}, this)">Run Now</button>
              <button class="btn btn-danger btn-sm" onclick="window.newsDeleteInterest(${i.id}, this)">Delete</button>
            </div>
          </div>
          <div style="font-size:12px;color:var(--text-muted);margin-bottom:8px">
            Schedule: ${Utils.escapeHtml(i.start_time)} every ${i.interval_hours}h | Summary: ${i.target_summary_words}w | Script: ${i.target_script_words}w
          </div>
          <div style="display:flex;gap:16px;font-size:12px;color:var(--text-secondary)">
            <span>${i.enable_summary ? 'Summary' : ''}</span>
            <span>${i.enable_script ? 'Script' : ''}</span>
            <span>${i.enable_brief ? 'Brief' : ''}</span>
          </div>
          <div id="news-runs-${i.id}" style="margin-top:12px">
            <button class="btn btn-secondary btn-sm" onclick="window.newsLoadRuns(${i.id}, this)">Load Runs</button>
          </div>
        </div>`; }).join('');

      html += '<hr style="border-color:var(--border-color);margin:24px 0"><div class="card"><div class="card-header">Add Interest</div>' + renderInterestForm() + '</div>';

      content.innerHTML = html;
      bindInterestForm();
    } catch (e) {
      document.getElementById('news-content').innerHTML = '<div class="alert alert-error">Failed to load interests: ' + Utils.escapeHtml(String(e.message)) + '</div>';
    }
  }

  function renderInterestForm() {
    return `
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
        <div class="form-group">
          <label>Name</label>
          <input class="form-input" id="ni-name" placeholder="e.g. AI News" />
        </div>
        <div class="form-group">
          <label>Start Time (HH:MM)</label>
          <input class="form-input" id="ni-start" value="04:00" />
        </div>
        <div class="form-group">
          <label>Interval (hours)</label>
          <input class="form-input" id="ni-interval" type="number" value="24" min="1" max="168" />
        </div>
        <div class="form-group">
          <label>Summary Words</label>
          <input class="form-input" id="ni-summary" type="number" value="750" />
        </div>
        <div class="form-group">
          <label>Script Words</label>
          <input class="form-input" id="ni-script" type="number" value="1250" />
        </div>
      </div>
      <div style="display:flex;gap:16px;margin:12px 0">
        <label class="toggle"><input type="checkbox" id="ni-enable-summary" checked><span class="toggle-switch"></span><span class="toggle-label">Summary</span></label>
        <label class="toggle"><input type="checkbox" id="ni-enable-script" checked><span class="toggle-switch"></span><span class="toggle-label">Script</span></label>
        <label class="toggle"><input type="checkbox" id="ni-enable-brief" checked><span class="toggle-switch"></span><span class="toggle-label">Brief</span></label>
      </div>
      <button class="btn btn-primary" id="btn-create-interest">Create Interest</button>
      <div id="news-feed-section" style="margin-top:16px"></div>`;
  }

  function bindInterestForm() {
    const btn = document.getElementById('btn-create-interest');
    if (!btn) return;
    btn.addEventListener('click', async () => {
      const data = {
        name: document.getElementById('ni-name').value.trim(),
        start_time: document.getElementById('ni-start').value.trim(),
        interval_hours: parseInt(document.getElementById('ni-interval').value),
        target_summary_words: parseInt(document.getElementById('ni-summary').value),
        target_script_words: parseInt(document.getElementById('ni-script').value),
        enable_summary: document.getElementById('ni-enable-summary')?.checked ?? true,
        enable_script: document.getElementById('ni-enable-script')?.checked ?? true,
        enable_brief: document.getElementById('ni-enable-brief')?.checked ?? true,
        enable_email: true,
      };
      if (!data.name) { Utils.showToast('Name is required', 'error'); return; }
      Utils.setButtonLoading(btn, 'Creating...');
      try {
        await fetch('/api/v1/agents/news/interests', { method:'POST', headers: authHeaders(), body: JSON.stringify(data) });
        Utils.setButtonSuccess(btn, 'Created!');
        Utils.showToast('Interest created', 'success');
        loadInterests();
      } catch (e) {
        Utils.resetButton(btn);
        Utils.showToast('Failed: ' + e.message, 'error');
      }
    });
  }

  window.newsTriggerRun = async (interestId, btn) => {
    if (btn) Utils.setButtonLoading(btn, 'Running...');
    try {
      const resp = await fetch(`/api/v1/agents/news/interests/${interestId}/run`, { method:'POST', headers: authHeaders() });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || 'Run failed');
      Utils.showToast('Pipeline started (run #' + data.run_id + ')', 'success');
    } catch (e) { Utils.showToast(e.message, 'error'); }
    finally { if (btn) Utils.resetButton(btn); }
  };

  window.newsDeleteInterest = async (interestId, btn) => {
    if (!confirm('Delete this interest?')) return;
    if (btn) Utils.setButtonLoading(btn, 'Deleting...');
    try {
      await fetch(`/api/v1/agents/news/interests/${interestId}`, { method:'DELETE', headers: authHeaders() });
      Utils.showToast('Interest deleted', 'info');
      loadInterests();
    } catch (e) { Utils.showToast('Delete failed: ' + e.message, 'error'); }
    finally { if (btn) Utils.resetButton(btn); }
  };

  window.newsLoadRuns = async (interestId, btn) => {
    const container = document.getElementById('news-runs-' + interestId);
    if (btn) Utils.setButtonLoading(btn, 'Loading...');
    try {
      const data = await fetch('/api/v1/agents/news/interests/' + interestId + '/runs', { headers: authHeaders() }).then(function (r) { return r.json(); });
      const runs = data.runs || [];
      container.innerHTML = runs.length === 0
        ? '<p style="font-size:12px;color:var(--text-muted)">No runs yet</p>'
        : runs.map(function (r) { return `
          <div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--border-color);font-size:12px">
            <span>#${r.id} — ${Utils.escapeHtml(r.run_date)} — <span class="status-dot ${r.status === 'completed' ? 'active' : r.status === 'failed' ? 'error' : 'inactive'}"></span> ${Utils.escapeHtml(r.status)}</span>
            ${r.current_stage ? '<span style="color:var(--text-muted)">' + Utils.escapeHtml(r.current_stage) + '</span>' : ''}
          </div>`; }).join('');
    } catch (e) { container.innerHTML = '<span style="color:var(--danger);font-size:12px">Error: ' + Utils.escapeHtml(String(e.message)) + '</span>'; }
    finally { if (btn) Utils.resetButton(btn); }
  };

  window.newsShowThemes = async (runId) => {
    try {
      const data = await fetch('/api/v1/agents/news/runs/' + runId + '/themes', { headers: authHeaders() }).then(function (r) { return r.json(); });
      const themes = data.themes || [];
      var html = '<h3>Themes</h3>';
      themes.forEach(function (t) {
        html += '<div class="card"><strong>' + Utils.escapeHtml(t.title) + '</strong><p style="font-size:12px;color:var(--text-muted)">' + Utils.escapeHtml(t.description) + '</p></div>';
      });
      const container = document.getElementById('active-tab-content');
      container.innerHTML += html;
    } catch (e) { console.error(e); }
  };

  function authHeaders() {
    const key = API.getApiKey();
    return {
      'Content-Type': 'application/json',
      'Authorization': 'Bearer ' + key,
    };
  }
})();
