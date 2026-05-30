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

      let html = interests.map(i => `
        <div class="card">
          <div class="card-header" style="display:flex;justify-content:space-between;align-items:center">
            <span>${i.name}</span>
            <div style="display:flex;gap:8px">
              <button class="btn btn-primary btn-sm" onclick="window.newsTriggerRun(${i.id})">Run Now</button>
              <button class="btn btn-danger btn-sm" onclick="window.newsDeleteInterest(${i.id})">Delete</button>
            </div>
          </div>
          <div style="font-size:12px;color:var(--text-muted);margin-bottom:8px">
            Schedule: ${i.start_time} every ${i.interval_hours}h | Summary: ${i.target_summary_words}w | Script: ${i.target_script_words}w
          </div>
          <div style="display:flex;gap:16px;font-size:12px;color:var(--text-secondary)">
            <span>${i.enable_summary ? 'Summary' : ''}</span>
            <span>${i.enable_script ? 'Script' : ''}</span>
            <span>${i.enable_brief ? 'Brief' : ''}</span>
          </div>
          <div id="news-runs-${i.id}" style="margin-top:12px">
            <button class="btn btn-secondary btn-sm" onclick="window.newsLoadRuns(${i.id})">Load Runs</button>
          </div>
        </div>`).join('');

      html += `<hr style="border-color:var(--border-color);margin:24px 0"><div class="card"><div class="card-header">Add Interest</div>${renderInterestForm()}</div>`;

      content.innerHTML = html;
      bindInterestForm();
    } catch (e) {
      document.getElementById('news-content').innerHTML = `<div class="alert alert-error">Failed to load interests: ${e.message}</div>`;
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
      if (!data.name) return alert('Name is required');
      try {
        await fetch('/api/v1/agents/news/interests', { method:'POST', headers: authHeaders(), body: JSON.stringify(data) });
        loadInterests();
      } catch (e) { alert('Failed: ' + e.message); }
    });
  }

  window.newsTriggerRun = async (interestId) => {
    try {
      const resp = await fetch(`/api/v1/agents/news/interests/${interestId}/run`, { method:'POST', headers: authHeaders() });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || 'Run failed');
      alert(`Pipeline started (run #${data.run_id})`);
    } catch (e) { alert(e.message); }
  };

  window.newsDeleteInterest = async (interestId) => {
    if (!confirm('Delete this interest and all its data?')) return;
    await fetch(`/api/v1/agents/news/interests/${interestId}`, { method:'DELETE', headers: authHeaders() });
    loadInterests();
  };

  window.newsLoadRuns = async (interestId) => {
    const container = document.getElementById(`news-runs-${interestId}`);
    try {
      const data = await fetch(`/api/v1/agents/news/interests/${interestId}/runs`, { headers: authHeaders() }).then(r => r.json());
      const runs = data.runs || [];
      container.innerHTML = runs.length === 0
        ? '<p style="font-size:12px;color:var(--text-muted)">No runs yet</p>'
        : runs.map(r => `
          <div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--border-color);font-size:12px">
            <span>#${r.id} — ${r.run_date} — <span class="status-dot ${r.status === 'completed' ? 'active' : r.status === 'failed' ? 'error' : 'inactive'}"></span> ${r.status}</span>
            ${r.current_stage ? `<span style="color:var(--text-muted)">${r.current_stage}</span>` : ''}
          </div>`).join('');
    } catch (e) { container.innerHTML = `<span style="color:var(--danger);font-size:12px">Error: ${e.message}</span>`; }
  };

  window.newsShowThemes = async (runId) => {
    try {
      const data = await fetch(`/api/v1/agents/news/runs/${runId}/themes`, { headers: authHeaders() }).then(r => r.json());
      const themes = data.themes || [];
      let html = '<h3>Themes</h3>';
      themes.forEach(t => {
        html += `<div class="card"><strong>${t.title}</strong><p style="font-size:12px;color:var(--text-muted)">${t.description}</p></div>`;
      });
      const container = document.getElementById('active-tab-content');
      container.innerHTML += html;
    } catch (e) { console.error(e); }
  };

  function authHeaders() {
    const key = API.getApiKey();
    return {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${key}`,
    };
  }
})();
