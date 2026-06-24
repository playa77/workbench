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
      +   '<div class="card-header" style="cursor:pointer;display:flex;justify-content:space-between;align-items:center" id="news-past-toggle" data-tooltip="Click to show or hide past news pipeline sessions." data-help-page="/static/help/news.html#interest-run">'
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
        + '<button class="btn btn-secondary btn-sm" onclick="javascript:Router.setActive(\'news\')" data-tooltip="Return to the news pipeline overview." data-help-page="/static/help/news.html#overview">Back to News</button>'
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
        <div class="card" id="news-interest-card-${i.id}">
          <div class="card-header" style="display:flex;justify-content:space-between;align-items:center">
            <span>${Utils.escapeHtml(i.name)}</span>
            <div style="display:flex;gap:6px;flex-wrap:wrap">
              <button class="btn btn-secondary btn-sm" onclick="window.newsEditInterest(${i.id}, this)" data-tooltip="Edit this interest's settings — name, schedule interval, summary/script prompts, and toggle options." data-help-page="/static/help/news.html#interest-edit">Edit</button>
              <button class="btn btn-secondary btn-sm" onclick="window.newsToggleFeeds(${i.id}, this)" data-tooltip="Manage RSS/Atom feeds for this interest. Add new feed URLs or remove existing ones." data-help-page="/static/help/news.html#interest-feeds">Feeds</button>
              <button class="btn btn-primary btn-sm" onclick="window.newsTriggerRun(${i.id}, this)" data-tooltip="Execute the news pipeline immediately for this interest — fetch feeds, process articles, generate summaries." data-help-page="/static/help/news.html#interest-run">Run Now</button>
              <button class="btn btn-danger btn-sm" onclick="window.newsDeleteInterest(${i.id}, this)" data-tooltip="Permanently delete this interest and all associated data. This cannot be undone." data-help-page="/static/help/news.html#interest-delete">Delete</button>
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
          <div id="news-edit-${i.id}" style="display:none;margin-top:12px;padding:12px;border:1px solid var(--border-color);border-radius:var(--radius-sm)"></div>
          <div id="news-feeds-${i.id}" style="display:none;margin-top:12px;padding:12px;border:1px solid var(--border-color);border-radius:var(--radius-sm)"></div>
          <div id="news-runs-${i.id}" style="margin-top:12px">
            <button class="btn btn-secondary btn-sm" onclick="window.newsLoadRuns(${i.id}, this)" data-tooltip="View past pipeline execution results for this interest, including summaries and scripts." data-help-page="/static/help/news.html#interest-run">Load Runs</button>
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
          <input class="form-input" id="ni-name" placeholder="e.g. AI News" data-tooltip="Name for this news interest — e.g. 'AI Research', 'Climate Science'. Used to identify the interest in the list." data-help-page="/static/help/news.html#interest-create" />
        </div>
        <div class="form-group">
          <label>Start Time (HH:MM)</label>
          <input class="form-input" id="ni-start" value="04:00" data-tooltip="Start time for scheduled runs in HH:MM format (24-hour). The pipeline only processes articles published after this time." data-help-page="/static/help/news.html#interest-create" />
        </div>
        <div class="form-group">
          <label>Interval (hours)</label>
          <input class="form-input" id="ni-interval" type="number" value="24" min="1" max="168" data-tooltip="How often the pipeline runs automatically, in hours. Minimum 1, maximum 168 (one week)." data-help-page="/static/help/news.html#interest-create" />
        </div>
        <div class="form-group">
          <label>Summary Words</label>
          <input class="form-input" id="ni-summary" type="number" value="750" data-tooltip="Target word count for the LLM-generated article summary." data-help-page="/static/help/news.html#interest-create" />
        </div>
        <div class="form-group">
          <label>Script Words</label>
          <input class="form-input" id="ni-script" type="number" value="1250" data-tooltip="Target word count for the LLM-generated script/analysis output." data-help-page="/static/help/news.html#interest-create" />
        </div>
      </div>
      <div style="display:flex;gap:16px;margin:12px 0">
        <label class="toggle"><input type="checkbox" id="ni-enable-summary" checked data-tooltip="Enable or disable article summarization for this interest." data-help-page="/static/help/news.html#interest-create"><span class="toggle-switch"></span><span class="toggle-label">Summary</span></label>
        <label class="toggle"><input type="checkbox" id="ni-enable-script" checked data-tooltip="Enable or disable script/analysis generation for this interest." data-help-page="/static/help/news.html#interest-create"><span class="toggle-switch"></span><span class="toggle-label">Script</span></label>
        <label class="toggle"><input type="checkbox" id="ni-enable-brief" checked data-tooltip="Enable or disable brief/concise mode for this interest." data-help-page="/static/help/news.html#interest-create"><span class="toggle-switch"></span><span class="toggle-label">Brief</span></label>
      </div>
      <button class="btn btn-primary" id="btn-create-interest" data-tooltip="Save and create this news interest with the configured settings." data-help-page="/static/help/news.html#interest-create">Create Interest</button>
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

  // ---- Interest editing ----
  window.newsEditInterest = function (interestId, btn) {
    var editDiv = document.getElementById('news-edit-' + interestId);
    if (!editDiv) return;
    if (editDiv.style.display === 'block') { editDiv.style.display = 'none'; return; }
    if (btn) Utils.setButtonLoading(btn, 'Loading...');
    fetch('/api/v1/agents/news/interests', { headers: authHeaders() })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var interests = data.interests || [];
        var interest = interests.find(function (i) { return i.id === interestId; });
        if (!interest) { if (btn) Utils.resetButton(btn); return; }
        editDiv.innerHTML = 
          '<div style="font-size:12px;font-weight:600;margin-bottom:8px">Edit Interest</div>' +
          '<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">' +
          '<div class="form-group"><label>Name</label><input class="form-input" id="ei-name-' + interestId + '" value="' + Utils.escapeHtml(interest.name || '') + '" /></div>' +
          '<div class="form-group"><label>Start Time (HH:MM)</label><input class="form-input" id="ei-start-' + interestId + '" value="' + Utils.escapeHtml(interest.start_time || '') + '" /></div>' +
          '<div class="form-group"><label>Interval (hours)</label><input class="form-input" id="ei-interval-' + interestId + '" type="number" value="' + (interest.interval_hours || 24) + '" /></div>' +
          '<div class="form-group"><label>Summary Words</label><input class="form-input" id="ei-summary-' + interestId + '" type="number" value="' + (interest.target_summary_words || 750) + '" /></div>' +
          '<div class="form-group"><label>Script Words</label><input class="form-input" id="ei-script-' + interestId + '" type="number" value="' + (interest.target_script_words || 1250) + '" /></div>' +
          '</div>' +
          '<div style="display:flex;gap:12px;margin:8px 0">' +
          '<label class="toggle"><input type="checkbox" id="ei-sum-' + interestId + '"' + (interest.enable_summary ? ' checked' : '') + '><span class="toggle-switch"></span><span class="toggle-label">Summary</span></label>' +
          '<label class="toggle"><input type="checkbox" id="ei-scr-' + interestId + '"' + (interest.enable_script ? ' checked' : '') + '><span class="toggle-switch"></span><span class="toggle-label">Script</span></label>' +
          '<label class="toggle"><input type="checkbox" id="ei-brf-' + interestId + '"' + (interest.enable_brief ? ' checked' : '') + '><span class="toggle-switch"></span><span class="toggle-label">Brief</span></label>' +
          '</div>' +
          '<button class="btn btn-primary btn-sm" onclick="window.newsSaveInterest(' + interestId + ', this)">Save</button>' +
          '<button class="btn btn-secondary btn-sm" style="margin-left:6px" onclick="document.getElementById(\'news-edit-' + interestId + '\').style.display=\'none\'">Cancel</button>';
        editDiv.style.display = 'block';
        if (btn) Utils.resetButton(btn);
      }).catch(function (e) {
        if (btn) Utils.resetButton(btn);
        Utils.showToast('Failed: ' + e.message, 'error');
      });
  };

  window.newsSaveInterest = function (interestId, btn) {
    var data = {};
    data.name = document.getElementById('ei-name-' + interestId).value.trim();
    data.start_time = document.getElementById('ei-start-' + interestId).value.trim();
    data.interval_hours = parseInt(document.getElementById('ei-interval-' + interestId).value) || 24;
    data.target_summary_words = parseInt(document.getElementById('ei-summary-' + interestId).value) || 750;
    data.target_script_words = parseInt(document.getElementById('ei-script-' + interestId).value) || 1250;
    data.enable_summary = document.getElementById('ei-sum-' + interestId)?.checked ?? true;
    data.enable_script = document.getElementById('ei-scr-' + interestId)?.checked ?? true;
    data.enable_brief = document.getElementById('ei-brf-' + interestId)?.checked ?? true;
    if (!data.name) { Utils.showToast('Name is required', 'error'); return; }
    Utils.setButtonLoading(btn, 'Saving...');
    fetch('/api/v1/agents/news/interests/' + interestId, {
      method: 'PATCH',
      headers: authHeaders(),
      body: JSON.stringify(data),
    }).then(function (r) {
      if (!r.ok) return r.json().then(function (e) { throw new Error(e.detail); });
      Utils.setButtonSuccess(btn, 'Saved!');
      Utils.showToast('Interest updated', 'success');
      loadInterests();
    }).catch(function (e) {
      Utils.resetButton(btn);
      Utils.showToast('Failed: ' + e.message, 'error');
    });
  };

  // ---- Feed management ----
  window.newsToggleFeeds = function (interestId, btn) {
    var feedsDiv = document.getElementById('news-feeds-' + interestId);
    if (!feedsDiv) return;
    if (feedsDiv.style.display === 'block') { feedsDiv.style.display = 'none'; return; }
    if (btn) Utils.setButtonLoading(btn, 'Loading...');
    fetch('/api/v1/agents/news/interests/' + interestId + '/feeds', { headers: authHeaders() })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var feeds = data.feeds || [];
        var html = '<div style="font-size:12px;font-weight:600;margin-bottom:8px">Feeds (' + feeds.length + ')</div>';
        if (feeds.length === 0) {
          html += '<p style="font-size:12px;color:var(--text-muted);margin-bottom:8px">No feeds yet.</p>';
        } else {
          html += feeds.map(function (f) {
            return '<div style="display:flex;justify-content:space-between;align-items:center;padding:4px 0;border-bottom:1px solid var(--border-color);font-size:12px">' +
              '<span>' + Utils.escapeHtml(f.name || f.url) + ' <span style="color:var(--text-muted);font-size:10px">' + Utils.escapeHtml(f.url || '') + '</span></span>' +
              '<button class="btn btn-danger btn-sm" style="padding:2px 6px;font-size:10px" onclick="window.newsDeleteFeed(' + interestId + ',' + f.id + ',this)">Remove</button>' +
              '</div>';
          }).join('');
        }
        html += '<div style="display:flex;gap:6px;margin-top:8px;align-items:flex-end">' +
          '<div style="flex:1"><input class="form-input" id="nf-name-' + interestId + '" placeholder="Feed name" style="font-size:11px;padding:4px 8px" /></div>' +
          '<div style="flex:2"><input class="form-input" id="nf-url-' + interestId + '" placeholder="RSS/Atom URL" style="font-size:11px;padding:4px 8px" /></div>' +
          '<button class="btn btn-primary btn-sm" onclick="window.newsAddFeed(' + interestId + ',this)" style="flex-shrink:0">Add</button>' +
          '</div>';
        feedsDiv.innerHTML = html;
        feedsDiv.style.display = 'block';
        if (btn) Utils.resetButton(btn);
      }).catch(function (e) {
        if (btn) Utils.resetButton(btn);
        Utils.showToast('Failed: ' + e.message, 'error');
      });
  };

  window.newsAddFeed = function (interestId, btn) {
    var nameEl = document.getElementById('nf-name-' + interestId);
    var urlEl = document.getElementById('nf-url-' + interestId);
    var name = nameEl ? nameEl.value.trim() : '';
    var url = urlEl ? urlEl.value.trim() : '';
    if (!url) { Utils.showToast('URL is required', 'error'); return; }
    Utils.setButtonLoading(btn, 'Adding...');
    fetch('/api/v1/agents/news/interests/' + interestId + '/feeds', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ name: name || url, url: url, category: 'news' }),
    }).then(function (r) {
      if (!r.ok) return r.json().then(function (e) { throw new Error(e.detail); });
      if (nameEl) nameEl.value = '';
      if (urlEl) urlEl.value = '';
      Utils.resetButton(btn);
      Utils.showToast('Feed added', 'success');
      newsToggleFeeds(interestId, null);
    }).catch(function (e) {
      Utils.resetButton(btn);
      Utils.showToast('Failed: ' + e.message, 'error');
    });
  };

  window.newsDeleteFeed = function (interestId, feedId, btn) {
    if (!confirm('Remove this feed?')) return;
    Utils.setButtonLoading(btn, 'Removing...');
    fetch('/api/v1/agents/news/interests/' + interestId + '/feeds/' + feedId, {
      method: 'DELETE',
      headers: authHeaders(),
    }).then(function () {
      Utils.showToast('Feed removed', 'info');
      newsToggleFeeds(interestId, null);
    }).catch(function (e) {
      Utils.resetButton(btn);
      Utils.showToast('Failed: ' + e.message, 'error');
    });
  };

  function authHeaders() {
    const key = API.getApiKey();
    return {
      'Content-Type': 'application/json',
      'Authorization': 'Bearer ' + key,
    };
  }
})();
