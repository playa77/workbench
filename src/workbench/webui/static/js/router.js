/* ==========================================
   Workbench — Tab Router
   Lazy-loads tab component scripts and styles on demand
   ========================================== */

const Router = (() => {
  let activeTab = null;
  const tabCallbacks = {};
  const loadedScripts = {};
  const loadedStyles = {};
  let _pendingActivation = null;

  function register(name, renderFn) {
    tabCallbacks[name] = renderFn;
  }

  function _activatePending() {
    if (_pendingActivation !== null) {
      var pending = _pendingActivation;
      _pendingActivation = null;
      setActive(pending);
    }
  }

  function setActive(name) {
    activeTab = name;
    const tabs = document.querySelectorAll('.tab-btn');
    tabs.forEach(t => t.classList.toggle('active', t.dataset.tab === name));

    document.getElementById('welcome-screen').style.display = 'none';
    document.getElementById('settings-panel').style.display = 'none';

    if (name === 'settings') {
      document.getElementById('settings-panel').style.display = 'block';
      document.getElementById('active-tab-content').style.display = 'none';
      return;
    }

    document.getElementById('active-tab-content').style.display = 'block';

    const btn = document.querySelector(`.tab-btn[data-tab="${name}"]`);
    const jsPath = btn ? btn.dataset.js : null;
    const cssPath = btn ? btn.dataset.css : null;
    const container = document.getElementById('active-tab-content');

    if (cssPath && !loadedStyles[cssPath]) {
      loadedStyles[cssPath] = true;
      const link = document.createElement('link');
      link.rel = 'stylesheet';
      link.href = cssPath;
      document.head.appendChild(link);
    }

    if (tabCallbacks[name]) {
      tabCallbacks[name](container);
      return;
    }

    container.innerHTML = '<div class="spinner" style="margin:40px auto"></div>';

    if (jsPath && !loadedScripts[jsPath]) {
      loadedScripts[jsPath] = true;
      const script = document.createElement('script');
      script.src = jsPath;
      script.onload = () => {
        _pendingActivation = name;
        var fallback = document.createElement('script');
        fallback.textContent = 'setTimeout(function() { Router._activatePending(); }, 10);';
        document.body.appendChild(fallback);
      };
      document.body.appendChild(script);
      return;
    }

    container.innerHTML = `<div class="card"><p>Agent "${name}" has no UI yet.</p></div>`;
  }

  function getActive() {
    return activeTab;
  }

  return { register, setActive, getActive, _activatePending };
})();
