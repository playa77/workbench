/* ==========================================
   Workbench — Main Application
   Boot sequence, auth flows, tab rendering, settings
   ========================================== */

(function () {
  var headerTabs = document.getElementById('header-tabs');
  var settingsToggle = document.getElementById('settings-toggle');

  Theme.init();

  /* ---- State ---- */
  var currentUser = null;

  /* ---- Boot ---- */
  async function boot() {
    try {
      currentUser = await API.me();
      renderTabs();
      renderMain();
    } catch (e) {
      if (e.status === 401 || e.status === 403) {
        renderAuth();
      } else {
        renderAuth();
      }
    }
  }

  /* ---- Auth flow ---- */
  function renderAuth() {
    var container = document.getElementById('active-tab-content');
    container.innerHTML = '<div class="welcome-screen"><div class="welcome-card">' +
      '<h2>Workbench</h2>' +
      '<p>Unified BYOK AI Workbench</p>' +
      '<div class="card" style="margin-top:24px;text-align:left;max-width:400px;margin-left:auto;margin-right:auto">' +
      '<div class="card-header">Sign In</div>' +
      '<div id="auth-section"></div></div></div></div>';

    var authSection = document.getElementById('auth-section');
    authSection.innerHTML =
      '<div class="form-group">' +
      '<label>Username</label>' +
      '<input class="form-input" id="reg-username" placeholder="Choose a username" />' +
      '</div>' +
      '<button class="btn btn-primary" id="btn-register" style="width:100%">Register</button>' +
      '<div style="margin-top:16px;padding-top:16px;border-top:1px solid var(--border-color)">' +
      '<div class="form-group">' +
      '<label>API Key</label>' +
      '<input class="form-input" id="auth-key" placeholder="Paste your API key to sign in" />' +
      '</div>' +
      '<button class="btn btn-secondary" id="btn-login" style="width:100%">Sign In with API Key</button>' +
      '</div>';

    document.getElementById('btn-register').addEventListener('click', async function () {
      var username = document.getElementById('reg-username').value.trim();
      if (!username) return;
      try {
        var result = await API.register(username);
        if (result.api_key) {
          renderApiKeyReveal(result.api_key);
        } else {
          alert(result.message || 'Registration processed.');
        }
      } catch (e) {
        if (e.status === 403) {
          alert('Registration is currently disabled. Contact your administrator for an account.');
        } else {
          alert('Registration failed: ' + e.message);
        }
      }
    });

    document.getElementById('btn-login').addEventListener('click', async function () {
      var key = document.getElementById('auth-key').value.trim();
      if (!key) return;
      try {
        await API.login(key);
        boot();
      } catch (e) {
        alert('Login failed: ' + e.message);
      }
    });
  }

  function renderApiKeyReveal(rawKey) {
    var authSection = document.getElementById('auth-section');
    authSection.innerHTML =
      '<div class="alert alert-success">Account created</div>' +
      '<div class="form-group">' +
      '<label>Your API Key (save it — visible only once)</label>' +
      '<div class="api-key-display" style="cursor:pointer" onclick="navigator.clipboard.writeText(this.textContent)">' +
      Utils.escapeHtml(rawKey) + '</div></div>' +
      '<button class="btn btn-primary" id="btn-auto-login" style="width:100%">Sign In &amp; Continue</button>';

    document.getElementById('btn-auto-login').addEventListener('click', async function () {
      try {
        await API.login(rawKey);
        boot();
      } catch (e) {
        alert('Login failed: ' + e.message);
      }
    });
  }

  /* ---- Tabs ---- */
  async function renderTabs() {
    try {
      var data = await API.listTabs();
      var tabs = data.tabs || [];
      headerTabs.innerHTML = tabs.map(function (t) {
        var iconSvg = getIcon(t.icon || 'puzzle');
        return '<button class="tab-btn" data-tab="' + Utils.escapeHtml(t.id) + '" data-component="' +
          Utils.escapeHtml(t.component || '') + '" data-js="' + Utils.escapeHtml(t.js || '') +
          '" data-css="' + Utils.escapeHtml(t.css || '') + '">' +
          iconSvg + ' ' + Utils.escapeHtml(t.displayName) + '</button>';
      }).join('');

      headerTabs.querySelectorAll('.tab-btn').forEach(function (btn) {
        btn.addEventListener('click', function () { Router.setActive(btn.dataset.tab); });
      });

      var owuiBtn = document.createElement('button');
      owuiBtn.className = 'tab-btn';
      owuiBtn.dataset.tab = 'owui';
      owuiBtn.dataset.js = '/static/js/components/owui-tab.js';
      owuiBtn.innerHTML = getIcon('globe') + ' LLMs';
      owuiBtn.addEventListener('click', function () { Router.setActive('owui'); });
      headerTabs.appendChild(owuiBtn);
    } catch (e) {
      headerTabs.innerHTML = '<span style="color:var(--text-muted);font-size:12px;">No agents</span>';
    }
  }

  function renderMain() {
    Router.register('settings', renderSettings);

    var settingsBtn = document.createElement('button');
    settingsBtn.className = 'tab-btn';
    settingsBtn.dataset.tab = 'settings';
    settingsBtn.innerHTML = getIcon('settings') + ' Settings';
    settingsBtn.addEventListener('click', function () { Router.setActive('settings'); });
    headerTabs.appendChild(settingsBtn);
  }

  /* ---- Settings page ---- */
  async function renderSettings(container) {
    container.innerHTML =
      '<h2 style="margin-bottom:24px;font-size:20px;font-weight:600">Settings</h2>' +
      '<div id="settings-content"></div>';

    var content = document.getElementById('settings-content');

    content.innerHTML +=
      '<div class="settings-section">' +
      '<h3>Profile</h3>' +
      (currentUser
        ? '<p>Logged in as <strong>' + Utils.escapeHtml(currentUser.username) + '</strong></p>'
        : '') +
      '</div>';

    var hasKey = currentUser && currentUser.has_openrouter_key;
    content.innerHTML +=
      '<div class="settings-section">' +
      '<h3>OpenRouter API Key</h3>' +
      '<p>Your personal BYOK key. Encrypted at rest. Never shared.</p>' +
      '<div class="form-group">' +
      '<input class="form-input" id="or-key-input" type="password" placeholder="' +
      (hasKey ? '(stored — enter new to replace)' : 'sk-or-v1-...') + '" />' +
      '</div>' +
      '<button class="btn btn-primary" id="btn-save-or-key">Save Key</button>' +
      (hasKey ? '<button class="btn btn-danger btn-sm" id="btn-delete-or-key" style="margin-left:8px">Remove Key</button>' : '') +
      '<div id="or-key-status" style="margin-top:8px;font-size:12px;color:var(--text-muted)"></div>' +
      '</div>';

    content.innerHTML +=
      '<div class="settings-section">' +
      '<h3>Theme</h3>' +
      '<button class="btn btn-secondary" id="btn-theme-switch">Switch to ' +
      (Theme.get() === 'dark' ? 'Light' : 'Dark') + ' Theme</button>' +
      '</div>';

    content.innerHTML +=
      '<div class="settings-section">' +
      '<h3>Agents</h3>' +
      '<div class="agent-grid" id="agent-list"></div>' +
      '</div>';

    content.innerHTML +=
      '<div class="settings-section">' +
      '<h3>API Keys</h3>' +
      '<div id="api-keys-section"></div>' +
      '</div>';

    content.innerHTML +=
      '<div class="settings-section">' +
      '<button class="btn btn-danger" id="btn-logout" style="width:100%">Sign Out</button>' +
      '</div>';

    document.getElementById('btn-save-or-key') && document.getElementById('btn-save-or-key').addEventListener('click', async function () {
      var val = document.getElementById('or-key-input').value.trim();
      if (!val) return;
      try {
        await API.setOpenRouterKey(val);
        document.getElementById('or-key-status').textContent = 'Key saved.';
      } catch (e) { document.getElementById('or-key-status').textContent = 'Error: ' + e.message; }
    });

    document.getElementById('btn-delete-or-key') && document.getElementById('btn-delete-or-key').addEventListener('click', async function () {
      await API.deleteOpenRouterKey();
      renderSettings(container);
    });

    document.getElementById('btn-theme-switch') && document.getElementById('btn-theme-switch').addEventListener('click', function () {
      Theme.toggle();
      renderSettings(container);
    });

    document.getElementById('btn-logout') && document.getElementById('btn-logout').addEventListener('click', async function () {
      await API.logout();
      currentUser = null;
      location.reload();
    });

    loadAgentList();
    loadApiKeys();
  }

  async function loadAgentList() {
    try {
      var agents = await API.listAgents();
      var grid = document.getElementById('agent-list');
      if (!grid) return;
      grid.innerHTML = agents.map(function (p) {
        return '<div class="agent-card" data-agent-card="' + Utils.escapeHtml(p.name) + '">' +
          '<div class="agent-card-header">' +
          '<span class="agent-card-name">' + getIcon(p.icon) + ' ' + Utils.escapeHtml(p.display_name) + '</span>' +
          '<label class="toggle">' +
          '<input type="checkbox" ' + (p.enabled ? 'checked' : '') + ' data-agent-name="' + Utils.escapeHtml(p.name) + '">' +
          '<span class="toggle-switch"></span>' +
          '</label>' +
          '</div>' +
          '<p class="agent-card-desc">' + Utils.escapeHtml(p.description) + '</p>' +
          '<p class="agent-card-version">v' + Utils.escapeHtml(p.version) + '</p>' +
          '<div class="agent-settings-form" id="agent-form-' + Utils.escapeHtml(p.name) + '"></div>' +
          '</div>';
      }).join('');

      grid.querySelectorAll('input[data-agent-name]').forEach(function (cb) {
        cb.addEventListener('change', function () {
          window.toggleAgent(cb.dataset.agentName, cb.checked);
        });
      });

      agents.forEach(function (p) {
        if (p.enabled) loadAgentSettingsForm(p.name);
      });
    } catch (e) { /* silently fail */ }
  }

  async function loadAgentSettingsForm(agentName) {
    try {
      var data = await API.getAgentSettings(agentName);
      var schema = data.settings_schema || {};
      var props = schema.properties || {};
      var current = data.current_settings || {};
      var formEl = document.getElementById('agent-form-' + Utils.escapeHtml(agentName));
      if (!formEl || Object.keys(props).length === 0) return;

      var html = '<div class="settings-form-divider"></div>' +
        '<div style="font-size:12px;font-weight:600;color:var(--text-secondary);margin-bottom:8px;text-transform:uppercase;letter-spacing:0.5px">Plugin Settings</div>';

      Object.keys(props).forEach(function (key) {
        var prop = props[key];
        var val = current[key] !== undefined ? current[key] : (prop.default !== undefined ? prop.default : '');
        html += '<div class="form-group" style="margin-bottom:10px">' +
          '<label>' + Utils.escapeHtml(prop.title || key) + '</label>';
        if (prop.enum) {
          html += '<select class="form-input" id="form-' + Utils.escapeHtml(agentName) + '-' + Utils.escapeHtml(key) + '" style="font-size:12px;padding:6px 10px">';
          prop.enum.forEach(function (opt) {
            var label = prop.enumLabels ? (prop.enumLabels[opt] || opt) : opt;
            html += '<option value="' + Utils.escapeHtml(opt) + '" ' + (String(val) === String(opt) ? 'selected' : '') + '>' + Utils.escapeHtml(label) + '</option>';
          });
          html += '</select>';
        } else if (prop.type === 'boolean') {
          html += '<label class="toggle" style="justify-content:flex-start">' +
            '<input type="checkbox" id="form-' + Utils.escapeHtml(agentName) + '-' + Utils.escapeHtml(key) + '" ' + (val ? 'checked' : '') + '>' +
            '<span class="toggle-switch"></span></label>';
        } else if (prop.type === 'number' || prop.type === 'integer') {
          html += '<input class="form-input" type="number" id="form-' + Utils.escapeHtml(agentName) + '-' + Utils.escapeHtml(key) + '" value="' + Utils.escapeHtml(String(val)) + '" style="font-size:12px;padding:6px 10px" />';
        } else {
          html += '<input class="form-input" type="text" id="form-' + Utils.escapeHtml(agentName) + '-' + Utils.escapeHtml(key) + '" value="' + Utils.escapeHtml(String(val)) + '" style="font-size:12px;padding:6px 10px" />';
        }
        if (prop.description) html += '<span style="font-size:10px;color:var(--text-muted)">' + Utils.escapeHtml(prop.description) + '</span>';
        html += '</div>';
      });

      html += '<button class="btn btn-primary btn-sm" id="btn-save-' + Utils.escapeHtml(agentName) + '" style="margin-top:4px">Save Settings</button>' +
        '<span id="save-status-' + Utils.escapeHtml(agentName) + '" style="margin-left:8px;font-size:11px;color:var(--success)"></span>';

      formEl.innerHTML = html;

      document.getElementById('btn-save-' + agentName).addEventListener('click', async function () {
        var sett = {};
        Object.keys(props).forEach(function (key) {
          var el = document.getElementById('form-' + agentName + '-' + key);
          var schema = props[key];
          if (!el || !schema) return;
          if (schema.type === 'boolean') {
            sett[key] = el.checked;
          } else if (schema.type === 'number' || schema.type === 'integer') {
            sett[key] = parseFloat(el.value);
          } else {
            sett[key] = el.value;
          }
        });
        try {
          await API.updateAgentSettings(agentName, { settings: sett });
          var status = document.getElementById('save-status-' + agentName);
          if (status) { status.textContent = 'Saved'; setTimeout(function () { status.textContent = ''; }, 2000); }
        } catch (e) {
          var status = document.getElementById('save-status-' + agentName);
          if (status) { status.textContent = 'Error: ' + e.message; }
        }
      });
    } catch (e) { /* silently fail */ }
  }

  async function loadApiKeys() {
    try {
      var keys = await API.listApiKeys();
      var section = document.getElementById('api-keys-section');
      if (!section) return;
      section.innerHTML = keys.map(function (k) {
        var created = k.created_at ? k.created_at.split('T')[0] : '';
        var lastUsed = k.last_used_at ? 'Last used ' + k.last_used_at.split('T')[0] : '';
        return '<div style="display:flex;align-items:center;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--border-color)">' +
          '<div>' +
          '<span style="font-weight:500;font-size:13px">' + Utils.escapeHtml(k.label) + '</span>' +
          '<span style="font-size:11px;color:var(--text-muted);margin-left:8px">Created ' + created + '</span>' +
          (lastUsed ? '<span style="font-size:11px;color:var(--text-muted);margin-left:8px">' + lastUsed + '</span>' : '') +
          '</div>' +
          '<button class="btn btn-danger btn-sm" data-delete-key="' + Utils.escapeHtml(k.id) + '">Delete</button>' +
          '</div>';
      }).join('');

      section.innerHTML +=
        '<div style="margin-top:12px;display:flex;gap:8px">' +
        '<input class="form-input" id="new-key-label" placeholder="Key label" />' +
        '<button class="btn btn-primary btn-sm" id="btn-create-key">Create Key</button>' +
        '</div>' +
        '<div id="new-key-display" style="margin-top:8px"></div>';

      section.querySelectorAll('[data-delete-key]').forEach(function (btn) {
        btn.addEventListener('click', async function () {
          await API.deleteApiKey(btn.dataset.deleteKey);
          loadApiKeys();
        });
      });

      document.getElementById('btn-create-key') && document.getElementById('btn-create-key').addEventListener('click', async function () {
        var label = document.getElementById('new-key-label').value.trim() || 'default';
        try {
          var result = await API.createApiKey(label);
          document.getElementById('new-key-display').innerHTML =
            '<div class="alert alert-success">New key: <code style="word-break:break-all">' +
            Utils.escapeHtml(result.api_key) + '</code> — save it now!</div>';
          loadApiKeys();
        } catch (e) { alert(e.message); }
      });
    } catch (e) { /* silently fail */ }
  }

  /* ---- Global helpers ---- */
  window.toggleAgent = async function (name, enabled) {
    try {
      await API.updateAgentSettings(name, { enabled: enabled });
      renderTabs();
    } catch (e) { console.error(e); }
  };

  /* ---- SVG icons ---- */
  function getIcon(name) {
    var icons = {
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
  settingsToggle.addEventListener('click', function () { Router.setActive('settings'); });

  /* ---- Boot ---- */
  boot();
})();
