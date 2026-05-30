/** Debate Agent Tab Component */

(function () {
  Router.register("debate", renderDebateTab);

  async function renderDebateTab(container) {
    container.innerHTML = `
      <div style="max-width:800px;margin:0 auto">
        <h2 style="margin-bottom:16px;font-size:20px;font-weight:600">Debate Arena</h2>
        <div class="form-group">
          <label>Topic</label>
          <input class="form-input" id="debate-topic" placeholder="Enter a topic to debate..." />
        </div>
        <div class="form-group">
          <label>Panel (select 2-5 roles)</label>
          <div id="debate-roles" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px">Loading roles...</div>
        </div>
        <button class="btn btn-primary" id="btn-start-debate">Start Debate</button>
        <div id="debate-result" style="margin-top:24px"></div>
      </div>`;

    loadRoles();
    document.getElementById('btn-start-debate').addEventListener('click', startDebate);
  }

  async function loadRoles() {
    const key = API.getApiKey();
    try {
      const data = await fetch('/api/v1/agents/debate/roles', { headers: { Authorization: `Bearer ${key}` } }).then(r => r.json());
      const roles = data.roles || [];
      document.getElementById('debate-roles').innerHTML = roles.map(r => `
        <label class="toggle" style="background:var(--bg-card);border:1px solid var(--border-color);border-radius:var(--radius-sm);padding:8px 12px">
          <input type="checkbox" class="debate-role-cb" value="${r.id}" ${['optimist','pessimist','pragmatist'].includes(r.id) ? 'checked' : ''}>
          <span class="toggle-label" style="margin-left:8px">${r.name}</span>
        </label>`).join('');
    } catch (e) {
      document.getElementById('debate-roles').innerHTML = 'Failed to load roles';
    }
  }

  async function startDebate() {
    const topic = document.getElementById('debate-topic').value.trim();
    if (!topic) return alert('Enter a topic');
    const selected = [...document.querySelectorAll('.debate-role-cb:checked')].map(cb => cb.value);
    if (selected.length < 2) return alert('Select at least 2 roles');

    const btn = document.getElementById('btn-start-debate');
    btn.disabled = true;
    btn.textContent = 'Debating...';
    document.getElementById('debate-result').innerHTML = '<div class="spinner" style="margin:20px auto"></div>';

    const key = API.getApiKey();
    try {
      const resp = await fetch('/api/v1/agents/debate/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${key}` },
        body: JSON.stringify({ topic, roles: selected }),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || 'Error');

      let html = `<h3 style="margin-bottom:16px">${data.topic}</h3>`;
      data.messages.forEach(msg => {
        const [role, ...content] = msg.split(']: ');
        html += `<div class="card"><strong>${role.replace('[','')}</strong><p style="margin-top:8px;font-size:13px;white-space:pre-wrap">${content.join(']: ')}</p></div>`;
      });
      document.getElementById('debate-result').innerHTML = html;
    } catch (e) {
      document.getElementById('debate-result').innerHTML = `<div class="alert alert-error">${e.message}</div>`;
    } finally {
      btn.disabled = false;
      btn.textContent = 'Start Debate';
    }
  }
})();
