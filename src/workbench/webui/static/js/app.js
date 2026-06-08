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
      document.getElementById('active-tab-content').innerHTML = '';
      await renderTabs();
      renderMain();
      var firstTab = document.querySelector('#header-tabs .tab-btn');
      if (firstTab) {
        Router.setActive(firstTab.dataset.tab);
      }
    } catch (e) {
      try {
        var setupStatus = await API.setupStatus();
        if (setupStatus.needs_setup) {
          renderSetup();
          return;
        }
      } catch (_) {}
      var params = new URLSearchParams(window.location.search);
      var path = window.location.pathname;
      if (path.indexOf('/setup') !== -1 && params.get('token')) {
        renderAcceptInvite(params.get('token'));
      } else if (path.indexOf('/reset-password') !== -1 && params.get('token')) {
        renderResetPassword(params.get('token'));
      } else {
        renderLogin();
      }
    }
  }

  /* ---- Auth flow ---- */
  function renderLogin() {
    var container = document.getElementById('active-tab-content');
    container.innerHTML = '<div class="welcome-screen"><div class="welcome-card">' +
      '<h2>Workbench</h2>' +
      '<p>Unified BYOK AI Workbench</p>' +
      '<div class="card" style="margin-top:24px;text-align:left;max-width:400px;margin-left:auto;margin-right:auto">' +
      '<div class="card-header">Sign In</div>' +
      '<div id="login-section"></div></div></div></div>';

    var loginSection = document.getElementById('login-section');
    loginSection.innerHTML =
      '<div class="form-group">' +
      '<label>Email or Username</label>' +
      '<input class="form-input" id="login-email-or-username" placeholder="Enter your email or username" />' +
      '</div>' +
      '<div class="form-group">' +
      '<label>Password</label>' +
      '<input class="form-input" id="login-password" type="password" placeholder="Enter your password" />' +
      '</div>' +
      '<button class="btn btn-primary" id="btn-login-password" style="width:100%">Sign In</button>' +
      '<div style="margin-top:8px;text-align:center">' +
      '<a href="#" id="link-forgot-password" style="font-size:12px;color:var(--text-muted)">Forgot password?</a>' +
      '</div>' +
      '<div style="margin-top:20px;padding-top:20px;border-top:1px solid var(--border-color)">' +
      '<div class="form-group">' +
      '<label>API Key</label>' +
      '<input class="form-input" id="login-api-key" placeholder="Or paste your API key to sign in" />' +
      '</div>' +
      '<button class="btn btn-secondary" id="btn-login-apikey" style="width:100%">Sign In with API Key</button>' +
      '</div>' +
      '<div id="login-message" style="margin-top:12px"></div>';

    document.getElementById('btn-login-password').addEventListener('click', async function () {
      var emailOrUsername = document.getElementById('login-email-or-username').value.trim();
      var password = document.getElementById('login-password').value;
      if (!emailOrUsername || !password) return;
      Utils.setButtonLoading(this, 'Signing in...');
      try {
        await API.passwordLogin(emailOrUsername, password);
        boot();
      } catch (e) {
        Utils.resetButton(this);
        document.getElementById('login-message').innerHTML = '<div class="alert alert-error">Invalid credentials</div>';
      }
    });

    document.getElementById('btn-login-apikey').addEventListener('click', async function () {
      var key = document.getElementById('login-api-key').value.trim();
      if (!key) return;
      Utils.setButtonLoading(this, 'Signing in...');
      try {
        await API.apiKeyLogin(key);
        boot();
      } catch (e) {
        Utils.resetButton(this);
        document.getElementById('login-message').innerHTML = '<div class="alert alert-error">' + Utils.escapeHtml(e.message) + '</div>';
      }
    });

    document.getElementById('link-forgot-password').addEventListener('click', function (e) {
      e.preventDefault();
      renderForgotPassword();
    });
  }

  function renderForgotPassword() {
    var container = document.getElementById('active-tab-content');
    container.innerHTML = '<div class="welcome-screen"><div class="welcome-card">' +
      '<h2>Workbench</h2>' +
      '<div class="card" style="margin-top:24px;text-align:left;max-width:400px;margin-left:auto;margin-right:auto">' +
      '<div class="card-header">Forgot Password</div>' +
      '<div class="form-group">' +
      '<label>Email</label>' +
      '<input class="form-input" id="forgot-email" type="email" placeholder="Enter your email address" />' +
      '</div>' +
      '<button class="btn btn-primary" id="btn-send-reset-link" style="width:100%">Send Reset Link</button>' +
      '<div style="margin-top:12px;text-align:center">' +
      '<a href="#" id="link-back-to-login" style="font-size:12px;color:var(--text-muted)">Back to Sign In</a>' +
      '</div>' +
      '<div id="forgot-message" style="margin-top:12px"></div>' +
      '</div></div></div>';

    document.getElementById('btn-send-reset-link').addEventListener('click', async function () {
      var email = document.getElementById('forgot-email').value.trim();
      if (!email) return;
      Utils.setButtonLoading(this, 'Sending...');
      try {
        await API.forgotPassword(email);
        Utils.resetButton(this);
        document.getElementById('forgot-message').innerHTML = '<div class="alert alert-success">If an account with that email exists, a reset link has been sent.</div>';
      } catch (e) {
        Utils.resetButton(this);
        document.getElementById('forgot-message').innerHTML = '<div class="alert alert-error">' + Utils.escapeHtml(e.message) + '</div>';
      }
    });

    document.getElementById('link-back-to-login').addEventListener('click', function (e) {
      e.preventDefault();
      renderLogin();
    });
  }

  function renderSetup() {
    var container = document.getElementById('active-tab-content');
    container.innerHTML = '<div class="welcome-screen"><div class="welcome-card">' +
      '<h2>Workbench</h2>' +
      '<p>First-run setup</p>' +
      '<div class="card" style="margin-top:24px;text-align:left;max-width:400px;margin-left:auto;margin-right:auto">' +
      '<div class="card-header">Create Admin Account</div>' +
      '<div class="form-group">' +
      '<label>Username</label>' +
      '<input class="form-input" id="setup-username" placeholder="Choose a username" />' +
      '</div>' +
      '<div class="form-group">' +
      '<label>Email</label>' +
      '<input class="form-input" id="setup-email" type="email" placeholder="admin@example.com" />' +
      '</div>' +
      '<div class="form-group">' +
      '<label>Password</label>' +
      '<input class="form-input" id="setup-password" type="password" placeholder="Min 8 characters" />' +
      '</div>' +
      '<div class="form-group">' +
      '<label>Confirm Password</label>' +
      '<input class="form-input" id="setup-confirm-password" type="password" placeholder="Re-enter password" />' +
      '</div>' +
      '<button class="btn btn-primary" id="btn-setup" style="width:100%">Create Account</button>' +
      '<div id="setup-message" style="margin-top:12px"></div>' +
      '</div></div></div>';

    document.getElementById('btn-setup').addEventListener('click', async function () {
      var username = document.getElementById('setup-username').value.trim();
      var email = document.getElementById('setup-email').value.trim();
      var password = document.getElementById('setup-password').value;
      var confirmPassword = document.getElementById('setup-confirm-password').value;
      if (!username || !email || !password) return;
      if (password.length < 8) {
        document.getElementById('setup-message').innerHTML = '<div class="alert alert-error">Password must be at least 8 characters.</div>';
        return;
      }
      if (password !== confirmPassword) {
        document.getElementById('setup-message').innerHTML = '<div class="alert alert-error">Passwords do not match.</div>';
        return;
      }
      Utils.setButtonLoading(this, 'Creating...');
      try {
        await API.setup(username, email, password);
        Utils.showToast('Account created', 'success');
        boot();
      } catch (e) {
        Utils.resetButton(this);
        document.getElementById('setup-message').innerHTML = '<div class="alert alert-error">' + Utils.escapeHtml(e.message) + '</div>';
      }
    });
  }

  function renderAcceptInvite(token) {
    var container = document.getElementById('active-tab-content');
    container.innerHTML = '<div class="welcome-screen"><div class="welcome-card">' +
      '<h2>Workbench</h2>' +
      '<div class="card" style="margin-top:24px;text-align:left;max-width:400px;margin-left:auto;margin-right:auto">' +
      '<div class="card-header">Set Up Your Account</div>' +
      '<div class="form-group">' +
      '<label>Password</label>' +
      '<input class="form-input" id="invite-password" type="password" placeholder="Min 8 characters" />' +
      '</div>' +
      '<div class="form-group">' +
      '<label>Confirm Password</label>' +
      '<input class="form-input" id="invite-confirm-password" type="password" placeholder="Re-enter password" />' +
      '</div>' +
      '<button class="btn btn-primary" id="btn-accept-invite" style="width:100%">Create Account</button>' +
      '<div id="invite-message" style="margin-top:12px"></div>' +
      '</div></div></div>';

    document.getElementById('btn-accept-invite').addEventListener('click', async function () {
      var password = document.getElementById('invite-password').value;
      var confirmPassword = document.getElementById('invite-confirm-password').value;
      if (password.length < 8) {
        document.getElementById('invite-message').innerHTML = '<div class="alert alert-error">Password must be at least 8 characters.</div>';
        return;
      }
      if (password !== confirmPassword) {
        document.getElementById('invite-message').innerHTML = '<div class="alert alert-error">Passwords do not match.</div>';
        return;
      }
      Utils.setButtonLoading(this, 'Creating...');
      try {
        await API.acceptInvite(token, password);
        Utils.showToast('Account created', 'success');
        boot();
      } catch (e) {
        Utils.resetButton(this);
        document.getElementById('invite-message').innerHTML = '<div class="alert alert-error">' + Utils.escapeHtml(e.message) + '</div>';
      }
    });
  }

  function renderResetPassword(token) {
    var container = document.getElementById('active-tab-content');
    container.innerHTML = '<div class="welcome-screen"><div class="welcome-card">' +
      '<h2>Workbench</h2>' +
      '<div class="card" style="margin-top:24px;text-align:left;max-width:400px;margin-left:auto;margin-right:auto">' +
      '<div class="card-header">Reset Your Password</div>' +
      '<div class="form-group">' +
      '<label>New Password</label>' +
      '<input class="form-input" id="reset-password" type="password" placeholder="Min 8 characters" />' +
      '</div>' +
      '<div class="form-group">' +
      '<label>Confirm Password</label>' +
      '<input class="form-input" id="reset-confirm-password" type="password" placeholder="Re-enter password" />' +
      '</div>' +
      '<button class="btn btn-primary" id="btn-reset-password" style="width:100%">Reset Password</button>' +
      '<div id="reset-message" style="margin-top:12px"></div>' +
      '</div></div></div>';

    document.getElementById('btn-reset-password').addEventListener('click', async function () {
      var password = document.getElementById('reset-password').value;
      var confirmPassword = document.getElementById('reset-confirm-password').value;
      if (password.length < 8) {
        document.getElementById('reset-message').innerHTML = '<div class="alert alert-error">Password must be at least 8 characters.</div>';
        return;
      }
      if (password !== confirmPassword) {
        document.getElementById('reset-message').innerHTML = '<div class="alert alert-error">Passwords do not match.</div>';
        return;
      }
      Utils.setButtonLoading(this, 'Resetting...');
      try {
        await API.resetPassword(token, password);
        Utils.showToast('Password reset', 'success');
        boot();
      } catch (e) {
        Utils.resetButton(this);
        document.getElementById('reset-message').innerHTML = '<div class="alert alert-error">' + Utils.escapeHtml(e.message) + '</div>';
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
      owuiBtn.innerHTML = getIcon('globe') + ' OpenWebUI';
      owuiBtn.addEventListener('click', function () { Router.setActive('owui'); });
      headerTabs.appendChild(owuiBtn);
    } catch (e) {
      headerTabs.innerHTML = '<span style="color:var(--text-muted);font-size:12px;">No agents</span>';
    }
  }

  function renderMain() {
    Router.register('settings', renderSettings);

    Router.register('owui', null);

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
        ? '<p>Logged in as <strong>' + Utils.escapeHtml(currentUser.username) + '</strong></p>' +
          (currentUser.email ? '<p>Email: ' + Utils.escapeHtml(currentUser.email) + '</p>' : '')
        : '') +
      '</div>';

    if (currentUser && currentUser.has_password) {
      content.innerHTML +=
        '<div class="settings-section">' +
        '<h3>Change Password</h3>' +
        '<div class="form-group">' +
        '<label>Current Password</label>' +
        '<input class="form-input" id="change-password-current" type="password" placeholder="Current password" />' +
        '</div>' +
        '<div class="form-group">' +
        '<label>New Password</label>' +
        '<input class="form-input" id="change-password-new" type="password" placeholder="New password (min 8 chars)" />' +
        '</div>' +
        '<button class="btn btn-primary" id="btn-change-password">Save Password</button>' +
        '<div id="change-password-message" style="margin-top:8px;font-size:12px;color:var(--text-muted)"></div>' +
        '</div>';
    }

    if (currentUser && currentUser.is_admin) {
      content.innerHTML +=
        '<div class="settings-section">' +
        '<h3>Invite Users</h3>' +
        '<div class="form-group">' +
        '<label>Email</label>' +
        '<input class="form-input" id="invite-email" type="email" placeholder="user@example.com" />' +
        '</div>' +
        '<div class="form-group">' +
        '<label>Username</label>' +
        '<input class="form-input" id="invite-username" placeholder="username" />' +
        '</div>' +
        '<button class="btn btn-primary" id="btn-send-invite">Send Invite</button>' +
        '<div id="invite-status" style="margin-top:8px;font-size:12px;color:var(--text-muted)"></div>' +
        '<div id="invite-list" style="margin-top:16px"></div>' +
        '</div>';
    }

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
      '<h3>API Keys' + (currentUser ? ' <span style="font-weight:400;font-size:12px;color:var(--text-muted)">for ' + Utils.escapeHtml(currentUser.username) + '</span>' : '') + '</h3>' +
      '<div id="api-keys-section"></div>' +
      '</div>';

    content.innerHTML +=
      '<div class="settings-section">' +
      '<button class="btn btn-danger" id="btn-logout" style="width:100%">Sign Out</button>' +
      '</div>';

    document.getElementById('btn-save-or-key') && document.getElementById('btn-save-or-key').addEventListener('click', async function () {
      var val = document.getElementById('or-key-input').value.trim();
      if (!val) return;
      Utils.setButtonLoading(this, 'Saving...');
      try {
        await API.setOpenRouterKey(val);
        Utils.setButtonSuccess(this, 'Saved!');
        document.getElementById('or-key-status').textContent = 'Key saved.';
      } catch (e) {
        Utils.resetButton(this);
        document.getElementById('or-key-status').textContent = 'Error: ' + e.message;
      }
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

    document.getElementById('btn-change-password') && document.getElementById('btn-change-password').addEventListener('click', async function () {
      var current = document.getElementById('change-password-current').value;
      var newPass = document.getElementById('change-password-new').value;
      if (!current || !newPass) return;
      if (newPass.length < 8) {
        document.getElementById('change-password-message').textContent = 'New password must be at least 8 characters.';
        return;
      }
      Utils.setButtonLoading(this, 'Saving...');
      try {
        await API.changePassword(current, newPass);
        Utils.setButtonSuccess(this, 'Saved!');
        document.getElementById('change-password-message').textContent = 'Password changed.';
        document.getElementById('change-password-current').value = '';
        document.getElementById('change-password-new').value = '';
      } catch (e) {
        Utils.resetButton(this);
        document.getElementById('change-password-message').textContent = 'Error: ' + e.message;
      }
    });

    document.getElementById('btn-send-invite') && document.getElementById('btn-send-invite').addEventListener('click', async function () {
      var email = document.getElementById('invite-email').value.trim();
      var username = document.getElementById('invite-username').value.trim();
      if (!email || !username) return;
      Utils.setButtonLoading(this, 'Sending...');
      try {
        await API.createInvite(email, username);
        Utils.setButtonSuccess(this, 'Sent!');
        document.getElementById('invite-email').value = '';
        document.getElementById('invite-username').value = '';
        document.getElementById('invite-status').textContent = 'Invite sent.';
        loadInviteList();
      } catch (e) {
        Utils.resetButton(this);
        document.getElementById('invite-status').textContent = 'Error: ' + e.message;
      }
    });

    if (currentUser && currentUser.is_admin) {
      loadInviteList();
    }

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
        Utils.setButtonLoading(this, 'Saving...');
        try {
          await API.updateAgentSettings(agentName, { settings: sett });
          Utils.setButtonSuccess(this, 'Saved!');
          var status = document.getElementById('save-status-' + agentName);
          if (status) { status.textContent = 'Saved'; setTimeout(function () { status.textContent = ''; }, 2000); }
        } catch (e) {
          Utils.resetButton(this);
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

      var listHtml = keys.length === 0
        ? '<p style="font-size:13px;color:var(--text-muted);text-align:center;padding:16px 0">No API keys yet. Create your first one below.</p>'
        : keys.map(function (k) {
          var created = k.created_at ? k.created_at.split('T')[0] : '';
          var lastUsed = k.last_used_at ? 'Last used ' + k.last_used_at.split('T')[0] : '';
          var fp = k.key_fingerprint
            ? '<span style="font-size:10px;color:var(--text-muted);font-family:var(--font-mono)">' + Utils.escapeHtml(k.key_fingerprint) + '</span>'
            : '';
          return '<div style="display:flex;align-items:center;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--border-color)">' +
            '<div>' +
            '<span style="font-weight:500;font-size:13px">' + Utils.escapeHtml(k.label) + '</span>' +
            (fp ? ' <span style="margin-left:6px">' + fp + '</span>' : '') +
            '<span style="font-size:11px;color:var(--text-muted);margin-left:8px">Created ' + created + '</span>' +
            (lastUsed ? '<span style="font-size:11px;color:var(--text-muted);margin-left:8px">' + lastUsed + '</span>' : '') +
            '</div>' +
            '<button class="btn btn-danger btn-sm" data-delete-key="' + Utils.escapeHtml(k.id) + '">Delete</button>' +
            '</div>';
        }).join('');

      var formHtml =
        '<div style="margin-top:16px;padding-top:12px;border-top:1px solid var(--border-color)">' +
        '<label style="font-size:12px;font-weight:600;color:var(--text-secondary);display:block;margin-bottom:8px">Create New Key</label>' +
        '<div style="display:flex;gap:8px;align-items:flex-end">' +
        '<div style="flex:1">' +
        '<label style="font-size:11px;color:var(--text-muted);display:block;margin-bottom:4px">Key Name</label>' +
        '<input class="form-input" id="new-key-label" placeholder="e.g. production, staging, personal" style="margin:0" />' +
        '</div>' +
        '<button class="btn btn-primary btn-sm" id="btn-create-key" style="flex-shrink:0">Create Key</button>' +
        '</div>' +
        '<div id="new-key-display" style="margin-top:8px"></div>' +
        '</div>';

      section.innerHTML = listHtml + formHtml;

      section.querySelectorAll('[data-delete-key]').forEach(function (btn) {
        btn.addEventListener('click', async function () {
          await API.deleteApiKey(btn.dataset.deleteKey);
          Utils.showToast('Key deleted', 'info');
          loadApiKeys();
        });
      });

      document.getElementById('btn-create-key') && document.getElementById('btn-create-key').addEventListener('click', async function () {
        var label = document.getElementById('new-key-label').value.trim();
        if (!label) { Utils.showToast('Please enter a name for the key', 'error'); return; }
        Utils.setButtonLoading(this, 'Creating...');
        try {
          var result = await API.createApiKey(label);
          Utils.setButtonSuccess(this, 'Created!');
          await loadApiKeys();
          document.getElementById('new-key-display').innerHTML =
            '<div class="alert alert-success">' +
            '<div style="display:flex;align-items:center;justify-content:space-between">' +
            '<span>Key <strong>' + Utils.escapeHtml(label) + '</strong> created</span>' +
            '<button class="btn btn-sm btn-secondary" id="btn-copy-key" style="font-size:11px;padding:2px 8px">Copy</button>' +
            '</div>' +
            '<code style="display:block;word-break:break-all;margin-top:4px;font-family:var(--font-mono);font-size:11px">' +
            Utils.escapeHtml(result.api_key) + '</code>' +
            '<span style="font-size:11px;color:var(--text-muted);display:block;margin-top:4px">Save this key &mdash; it won\'t be shown again.</span>' +
            '</div>';
          document.getElementById('btn-copy-key').addEventListener('click', function () {
            navigator.clipboard.writeText(result.api_key);
            this.textContent = 'Copied!';
            var self = this;
            setTimeout(function () { self.textContent = 'Copy'; }, 2000);
          });
        } catch (e) { Utils.resetButton(this); Utils.showToast(e.message, 'error'); }
      });
    } catch (e) { /* silently fail */ }
  }

  async function loadInviteList() {
    try {
      var invites = await API.listInvites();
      var listEl = document.getElementById('invite-list');
      if (!listEl) return;
      if (invites.length === 0) {
        listEl.innerHTML = '<p style="font-size:13px;color:var(--text-muted);padding:8px 0">No invites yet.</p>';
        return;
      }
      listEl.innerHTML = '<div style="font-size:12px;font-weight:600;color:var(--text-secondary);margin-bottom:8px">Existing Invites</div>';
      invites.forEach(function (inv) {
        var status = inv.is_revoked ? 'Revoked' : (inv.accepted_at ? 'Accepted' : 'Pending');
        var statusClass = 'status-dot ';
        if (status === 'Accepted') statusClass += 'active';
        else if (status === 'Revoked') statusClass += 'error';
        else statusClass += 'inactive';
        var createdDate = inv.created_at ? inv.created_at.split('T')[0] : '';
        var expiresDate = inv.expires_at ? inv.expires_at.split('T')[0] : '';
        listEl.innerHTML +=
          '<div style="display:flex;align-items:center;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--border-color)">' +
          '<div style="display:flex;align-items:center;gap:8px">' +
          '<span class="' + statusClass + '"></span>' +
          '<div>' +
          '<span style="font-weight:500;font-size:13px">' + Utils.escapeHtml(inv.email) + '</span>' +
          '<span style="font-size:11px;color:var(--text-muted);margin-left:8px">' + Utils.escapeHtml(inv.username) + '</span>' +
          '<br><span style="font-size:10px;color:var(--text-muted)">' +
          'Created ' + createdDate + ' | Expires ' + expiresDate +
          '</span>' +
          '</div>' +
          '</div>' +
          (status !== 'Revoked' && status !== 'Accepted'
            ? '<button class="btn btn-danger btn-sm" data-revoke-invite="' + Utils.escapeHtml(inv.id) + '">Revoke</button>'
            : '<span style="font-size:11px;color:var(--text-muted)">' + Utils.escapeHtml(status) + '</span>') +
          '</div>';
      });
      listEl.querySelectorAll('[data-revoke-invite]').forEach(function (btn) {
        btn.addEventListener('click', async function () {
          try {
            await API.deleteInvite(btn.dataset.revokeInvite);
            loadInviteList();
          } catch (e) {
            document.getElementById('invite-status').textContent = 'Error: ' + e.message;
          }
        });
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
      database: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/></svg>',
    };
    return icons[name] || icons.puzzle;
  }

  /* ---- Settings toggle ---- */
  settingsToggle.addEventListener('click', function () { Router.setActive('settings'); });

  /* ---- Boot ---- */
  boot();
})();
