/* ==========================================
   Workbench — Main Application
   Boot sequence, auth flows, tab rendering, settings
   ========================================== */

(function () {
  const headerTabs = document.getElementById('header-tabs');
  const settingsToggle = document.getElementById('settings-toggle');

  Theme.init();

  /* ---- State ---- */
  let currentUser = null;

  /* ---- Boot ---- */
  async function boot() {
    if (API.hasApiKey()) {
      try {
        currentUser = await API.me();
        renderTabs();
        renderMain();
      } catch (e) {
        if (e.status === 401) {
          API.setApiKey('');
          renderAuth();
        }
      }
    } else {
      renderAuth();
    }
  }

  /* ---- Auth flow ---- */
  function renderAuth() {
    const container = document.getElementById('active-tab-content');
    container.innerHTML = `
      <div class="welcome-screen">
        <div class="welcome-card">
          <h2>Workbench</h2>
          <p>Unified BYOK AI Workbench — agent-driven infrastructure for LLM-powered tools</p>
          <div class="card" style="margin-top:24px; text-align:left; max-width:400px; margin-left:auto; margin-right:auto;">
            <div class="card-header">Get Started</div>
            <div id="auth-section"></div>
          </div>
        </div>
      </div>`;

    const authSection = document.getElementById('auth-section');
    authSection.innerHTML = `
      <div class="form-group">
        <label>Username</label>
        <input class="form-input" id="reg-username" placeholder="Choose a username" />
      </div>
      <button class="btn btn-primary" id="btn-register" style="width:100%">Register &amp; Get API Key</button>
      <div style="margin-top:16px; padding-top:16px; border-top:1px solid var(--border-color)">
        <div class="form-group">
          <label>API Key</label>
          <input class="form-input" id="auth-key" placeholder="Paste your API key" />
        </div>
        <button class="btn btn-secondary" id="btn-login" style="width:100%">Login with API Key</button>
      </div>`;

    document.getElementById('btn-register').addEventListener('click', async () => {
      const username = document.getElementById('reg-username').value.trim();
      if (!username) return;
      try {
        const result = await API.register(username);
        API.setApiKey(result.api_key);
        renderApiKeyReveal(result.api_key);
      } catch (e) {
        alert('Registration failed: ' + e.message);
      }
    });

    document.getElementById('btn-login').addEventListener('click', async () => {
      const key = document.getElementById('auth-key').value.trim();
      if (!key) return;
      API.setApiKey(key);
      boot();
    });
  }

  function renderApiKeyReveal(rawKey) {
    const authSection = document.getElementById('auth-section');
    authSection.innerHTML = `
      <div class="alert alert-success">Account created!</div>
      <div class="form-group">
        <label>Your API Key (save it — visible only once)</label>
         <div class="api-key-display" style="cursor:pointer" onclick="navigator.clipboard.writeText(this.textContent)">${Utils.escapeHtml(rawKey)}</div>
      </div>
      <button class="btn btn-primary" onclick="location.reload()">Continue to Workbench</button>`;
  }

  /* ---- Tabs ---- */
  async function renderTabs() {
    try {
      const data = await API.listTabs();
      const tabs = data.tabs || [];
      headerTabs.innerHTML = tabs.map(t => {
        const iconSvg = getIcon(t.icon || 'puzzle');
        return `<button class="tab-btn" data-tab="${t.id}" data-component="${t.component || ''}" data-js="${t.js || ''}" onclick="window.RouterState.setActive('${t.id}')">${iconSvg} ${t.displayName}</button>`;
      }).join('');

      headerTabs.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => Router.setActive(btn.dataset.tab));
      });

      // Open WebUI tab — not agent-registered, embedded SPA
      const owuiBtn = document.createElement('button');
      owuiBtn.className = 'tab-btn';
      owuiBtn.dataset.tab = 'owui';
      owuiBtn.dataset.js = '/static/js/components/owui-tab.js';
      owuiBtn.innerHTML = getIcon('globe') + ' LLMs';
      owuiBtn.addEventListener('click', () => Router.setActive('owui'));
      headerTabs.appendChild(owuiBtn);
    } catch (e) {
      headerTabs.innerHTML = '<span style="color:var(--text-muted);font-size:12px;">No agents</span>';
    }
  }

  function renderMain() {
    Router.register('settings', renderSettings);

    const settingsBtn = document.createElement('button');
    settingsBtn.className = 'tab-btn';
    settingsBtn.dataset.tab = 'settings';
    settingsBtn.innerHTML = getIcon('settings') + ' Settings';
    settingsBtn.addEventListener('click', () => Router.setActive('settings'));
    headerTabs.appendChild(settingsBtn);
  }

  /* ---- Settings page ---- */
  async function renderSettings(container) {
    container.innerHTML = `
      <h2 style="margin-bottom:24px;font-size:20px;font-weight:600">Settings</h2>
      <div id="settings-content"></div>`;

    const content = document.getElementById('settings-content');

    content.innerHTML += `
      <div class="settings-section">
        <h3>Profile</h3>
        ${currentUser ? `<p>Logged in as <strong>${Utils.escapeHtml(currentUser.username)}</strong> — <code style="font-size:11px">${currentUser.id}</code></p>` : ''}
      </div>`;

    const hasKey = currentUser?.has_openrouter_key;
    content.innerHTML += `
      <div class="settings-section">
        <h3>OpenRouter API Key</h3>
        <p>Your personal BYOK key. Encrypted at rest. Never shared.</p>
        <div class="form-group">
          <input class="form-input" id="or-key-input" type="password" placeholder="${hasKey ? '(stored — enter new to replace)' : 'sk-or-v1-...'}" />
        </div>
        <button class="btn btn-primary" id="btn-save-or-key">Save Key</button>
        ${hasKey ? '<button class="btn btn-danger btn-sm" id="btn-delete-or-key" style="margin-left:8px">Remove Key</button>' : ''}
        <div id="or-key-status" style="margin-top:8px;font-size:12px;color:var(--text-muted)"></div>
      </div>`;

    content.innerHTML += `
      <div class="settings-section">
        <h3>Theme</h3>
        <button class="btn btn-secondary" id="btn-theme-switch">Switch to ${Theme.get() === 'dark' ? 'Light' : 'Dark'} Theme</button>
      </div>`;

    content.innerHTML += `
      <div class="settings-section">
        <h3>Agents</h3>
        <div class="agent-grid" id="agent-list"></div>
      </div>`;

    content.innerHTML += `
      <div class="settings-section">
        <h3>API Keys</h3>
        <div id="api-keys-section"></div>
      </div>`;

    document.getElementById('btn-save-or-key')?.addEventListener('click', async () => {
      const val = document.getElementById('or-key-input').value.trim();
      if (!val) return;
      try {
        await API.setOpenRouterKey(val);
        document.getElementById('or-key-status').textContent = 'Key saved.';
      } catch (e) { document.getElementById('or-key-status').textContent = 'Error: ' + e.message; }
    });

    document.getElementById('btn-delete-or-key')?.addEventListener('click', async () => {
      await API.deleteOpenRouterKey();
      renderSettings(container);
    });

    document.getElementById('btn-theme-switch')?.addEventListener('click', () => {
      Theme.toggle();
      renderSettings(container);
    });

    loadAgentList();
    loadApiKeys();
  }

  async function loadAgentList() {
    try {
      const agents = await API.listAgents();
      const grid = document.getElementById('agent-list');
      if (!grid) return;
      grid.innerHTML = agents.map(p => `
        <div class="agent-card">
          <div class="agent-card-header">
            <span class="agent-card-name">${getIcon(p.icon)} ${p.display_name}</span>
            <label class="toggle">
              <input type="checkbox" ${p.enabled ? 'checked' : ''} onchange="window.toggleAgent('${p.name}', this.checked)">
              <span class="toggle-switch"></span>
            </label>
          </div>
          <p class="agent-card-desc">${p.description}</p>
          <p class="agent-card-version">v${p.version}</p>
        </div>`).join('');
    } catch (e) { /* silently fail */ }
  }

  async function loadApiKeys() {
    try {
      const keys = await API.listApiKeys();
      const section = document.getElementById('api-keys-section');
      if (!section) return;
      section.innerHTML = keys.map(k => `
        <div style="display:flex;align-items:center;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--border-color)">
          <div>
            <span style="font-weight:500;font-size:13px">${Utils.escapeHtml(k.label)}</span>
            <span style="font-size:11px;color:var(--text-muted);margin-left:8px">Created ${k.created_at?.split('T')[0]}</span>
            ${k.last_used_at ? `<span style="font-size:11px;color:var(--text-muted);margin-left:8px">Last used ${k.last_used_at?.split('T')[0]}</span>` : ''}
          </div>
          <button class="btn btn-danger btn-sm" onclick="window.deleteApiKeyAndRefresh('${k.id}')">Delete</button>
        </div>`).join('');

      section.innerHTML += `
        <div style="margin-top:12px;display:flex;gap:8px">
          <input class="form-input" id="new-key-label" placeholder="Key label" />
          <button class="btn btn-primary btn-sm" id="btn-create-key">Create Key</button>
        </div>
        <div id="new-key-display" style="margin-top:8px"></div>`;

      document.getElementById('btn-create-key')?.addEventListener('click', async () => {
        const label = document.getElementById('new-key-label').value.trim() || 'default';
        try {
          const result = await API.createApiKey(label);
          document.getElementById('new-key-display').innerHTML = `
            <div class="alert alert-success">New key: <code style="word-break:break-all">${Utils.escapeHtml(result.api_key)}</code> — save it now!</div>`;
          loadApiKeys();
        } catch (e) { alert(e.message); }
      });
    } catch (e) { /* silently fail */ }
  }

  /* ---- Global helpers exposed to onclick handlers ---- */
  window.toggleAgent = async (name, enabled) => {
    try {
      await API.updateAgentSettings(name, { enabled });
      renderTabs();
    } catch (e) { console.error(e); }
  };

  window.deleteApiKeyAndRefresh = async (id) => {
    await API.deleteApiKey(id);
    loadApiKeys();
  };

  window.RouterState = { setActive: Router.setActive, getActive: Router.getActive };

  /* ---- SVG icons ---- */
  function getIcon(name) {
    const icons = {
      puzzle: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19.439 7.85c-.049.322.059.648.289.878l1.568 1.568c.47.47.706 1.087.706 1.704s-.235 1.233-.706 1.704l-1.611 1.611a.98.98 0 0 1-.837.276c-.47-.07-.802-.48-.968-.925a2.501 2.501 0 1 0-3.214 3.214c.446.166.855.497.925.968a.979.979 0 0 1-.276.837l-1.61 1.611a2.404 2.404 0 0 1-1.705.706 2.404 2.404 0 0 1-1.704-.706l-1.568-1.568a1.026 1.026 0 0 0-.877-.29c-.493.074-.84.504-1.02.968a2.5 2.5 0 1 1-3.237-3.237c.464-.18.894-.527.967-1.02a1.026 1.026 0 0 0-.289-.877l-1.568-1.568A2.404 2.404 0 0 1 1.998 12c0-.617.236-1.234.706-1.704L4.315 8.685a.98.98 0 0 1 .837-.276c.47.07.802.48.968.925a2.501 2.501 0 1 0 3.214-3.214c-.446-.166-.855-.497-.925-.968a.979.979 0 0 1 .276-.837l1.61-1.611a2.404 2.404 0 0 1 1.705-.706c.617 0 1.234.236 1.704.706l1.568 1.568c.23.23.556.338.877.29.493-.074.84-.504 1.02-.968a2.5 2.5 0 1 1 3.237 3.237c-.464.18-.894.527-.967 1.02Z"/></svg>',
      settings: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>',
      "message-circle": '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>',
      newspaper: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 11a9 9 0 0 1 9 9"/><path d="M4 4a16 16 0 0 1 16 16"/><circle cx="5" cy="19" r="1"/></svg>',
      scale: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>',
      users: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>',
      search: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>',
      target: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/></svg>',
      globe: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 014 10 15.3 15.3 0 01-4 10 15.3 15.3 0 01-4-10 15.3 15.3 0 014-10z"/></svg>',
    };
    return icons[name] || icons.puzzle;
  }

  /* ---- Settings toggle ---- */
  settingsToggle.addEventListener('click', () => Router.setActive('settings'));

  /* ---- Boot ---- */
  boot();
})();
