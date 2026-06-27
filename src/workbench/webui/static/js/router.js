/* ==========================================
   Workbench — Tab Router
   Persistent tab containers — show/hide instead of re-render
   ========================================== */

const Router = (() => {
  let activeTab = null;
  const tabCallbacks = {};
  const loadedScripts = {};
  const loadedStyles = {};
  const tabPanels = {};
  const onActivateCallbacks = {};

  function register(name, renderFn) {
    tabCallbacks[name] = renderFn;
    if (activeTab === name && !tabPanels[name]) {
      _createAndRender(name);
    }
  }

  function onActivate(name, fn) {
    onActivateCallbacks[name] = fn;
  }

  function _getOrCreatePanel(name) {
    if (!tabPanels[name]) {
      var panel = document.createElement('div');
      panel.id = 'tab-panel-' + name;
      panel.className = 'tab-panel';
      panel.style.display = 'none';
      var container = document.getElementById('active-tab-content');
      container.appendChild(panel);
      tabPanels[name] = panel;
    }
    return tabPanels[name];
  }

  function _createAndRender(name) {
    var panel = _getOrCreatePanel(name);
    panel.innerHTML = '';
    if (tabCallbacks[name]) {
      tabCallbacks[name](panel);
    }
  }

  function setActive(name) {
    var prevTab = activeTab;
    activeTab = name;

    var tabs = document.querySelectorAll('.tab-btn');
    tabs.forEach(function (t) {
      t.classList.toggle('active', t.dataset.tab === name);
    });

    var ws = document.getElementById('welcome-screen');
    if (ws) ws.style.display = 'none';
    var sp = document.getElementById('settings-panel');
    sp.style.display = 'none';

    var container = document.getElementById('active-tab-content');
    container.style.display = 'block';

    Object.keys(tabPanels).forEach(function (k) {
      tabPanels[k].style.display = 'none';
    });

    if (name === 'settings') {
      document.getElementById('settings-panel').style.display = 'block';
      container.style.display = 'none';
      if (tabCallbacks[name]) {
        tabCallbacks[name](document.getElementById('settings-panel'));
      }
      return;
    }

    if (tabPanels[name]) {
      tabPanels[name].style.display = 'block';
      if (onActivateCallbacks[name]) {
        onActivateCallbacks[name](prevTab);
      }
      return;
    }

    var btn = document.querySelector('.tab-btn[data-tab="' + name + '"]');
    var jsPath = btn ? btn.dataset.js : null;
    var cssPath = btn ? btn.dataset.css : null;

    if (cssPath && !loadedStyles[cssPath]) {
      loadedStyles[cssPath] = true;
      var link = document.createElement('link');
      link.rel = 'stylesheet';
      link.href = cssPath;
      document.head.appendChild(link);
    }

    if (tabCallbacks[name]) {
      _createAndRender(name);
      var panel = _getOrCreatePanel(name);
      panel.style.display = 'block';
      return;
    }

    var panel = _getOrCreatePanel(name);
    panel.style.display = 'block';
    // Nielsen #1 (Visibility of system status): Show what's happening with a
    // descriptive loading state, not just a spinner.
    panel.innerHTML = '<div class="tab-loading">' +
      '<div class="spinner" style="margin:40px auto 12px"></div>' +
      '<p style="text-align:center;color:var(--text-muted);font-size:13px">Loading ' + Utils.escapeHtml(name) + '...</p>' +
      '</div>';

    if (jsPath && !loadedScripts[jsPath]) {
      loadedScripts[jsPath] = true;
      var script = document.createElement('script');
      script.src = jsPath;

      // C2: Tab load failure recovery — timeout after 15 seconds with error
      // state and retry button. Applies Nielsen #1 (Visibility) and Don Norman
      // principle #4 (Feedback).
      var loadTimeout = setTimeout(function () {
        if (!tabCallbacks[name]) {
          panel.innerHTML = '<div class="card" style="text-align:center;padding:40px">' +
            '<p style="color:var(--text-muted);margin-bottom:16px">Could not load <strong>' + Utils.escapeHtml(name) + '</strong>. The component script may be unavailable or the server may be slow.</p>' +
            '<button class="btn btn-primary btn-sm" id="tab-retry-' + Utils.escapeHtml(name) + '">Retry</button>' +
            '</div>';
          document.getElementById('tab-retry-' + name).addEventListener('click', function () {
            // Reset state and retry loading
            delete loadedScripts[jsPath];
            delete tabPanels[name];
            Router.setActive(name);
          });
        }
      }, 15000);

      script.onload = function () {
        clearTimeout(loadTimeout);
        if (tabCallbacks[name]) {
          _createAndRender(name);
          panel.style.display = 'block';
        } else {
          // Script loaded but didn't register a callback — component error
          panel.innerHTML = '<div class="card" style="text-align:center;padding:40px">' +
            '<p style="color:var(--text-muted);margin-bottom:16px"><strong>' + Utils.escapeHtml(name) + '</strong> component loaded but failed to initialize.</p>' +
            '<button class="btn btn-primary btn-sm" onclick="location.reload()">Reload Page</button>' +
            '</div>';
        }
      };

      script.onerror = function () {
        clearTimeout(loadTimeout);
        panel.innerHTML = '<div class="card" style="text-align:center;padding:40px">' +
          '<p style="color:var(--text-muted);margin-bottom:16px">Failed to load <strong>' + Utils.escapeHtml(name) + '</strong>. Check your connection and try again.</p>' +
          '<button class="btn btn-primary btn-sm" id="tab-retry-' + Utils.escapeHtml(name) + '">Retry</button>' +
          '</div>';
        document.getElementById('tab-retry-' + name).addEventListener('click', function () {
          delete loadedScripts[jsPath];
          delete tabPanels[name];
          Router.setActive(name);
        });
      };

      document.body.appendChild(script);
      return;
    }

    panel.innerHTML = '<div class="card" style="text-align:center;padding:32px">' +
      '<p style="color:var(--text-muted);margin-bottom:12px">' + Utils.escapeHtml(name) + ' is not yet available in this version.</p>' +
      '<button class="btn btn-secondary btn-sm" onclick="Router.setActive(\'chat\')">Open Chat</button>' +
      '</div>';
  }

  function getActive() {
    return activeTab;
  }

  return { register, setActive, getActive, onActivate, _getOrCreatePanel };
})();
