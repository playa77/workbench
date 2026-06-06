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

  function register(name, renderFn) {
    tabCallbacks[name] = renderFn;
    if (activeTab === name && !tabPanels[name]) {
      _createAndRender(name);
    }
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
    panel.innerHTML = '<div class="spinner" style="margin:40px auto"></div>';

    if (jsPath && !loadedScripts[jsPath]) {
      loadedScripts[jsPath] = true;
      var script = document.createElement('script');
      script.src = jsPath;
      script.onload = function () {
        if (tabCallbacks[name]) {
          _createAndRender(name);
          panel.style.display = 'block';
        }
      };
      document.body.appendChild(script);
      return;
    }

    panel.innerHTML = '<div class="card"><p>Agent "' + Utils.escapeHtml(name) + '" has no UI yet.</p></div>';
  }

  function getActive() {
    return activeTab;
  }

  return { register, setActive, getActive, _getOrCreatePanel };
})();
