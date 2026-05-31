/** Open WebUI Tab Component
 * Embeds the Open WebUI instance (launched by electron wrapper) via iframe.
 * Health-checks the service before embedding. Falls back to launch instructions
 * if unreachable.
 */

(function () {
  var healthCheckTimer = null;
  var currentPort = null;
  var currentChecked = false;

  Router.register("owui", renderOwuiTab);

  function renderOwuiTab(container) {
    if (healthCheckTimer) { clearTimeout(healthCheckTimer); healthCheckTimer = null; }

    var savedPort = localStorage.getItem('wb_owui_port') || '8080';
    currentPort = parseInt(savedPort) || 8080;
    currentChecked = false;

    container.innerHTML = ''
      + '<div style="max-width:1000px;margin:0 auto">'
      +   '<h2 style="margin-bottom:16px;font-size:20px;font-weight:600">Open WebUI</h2>'
      +   '<div class="card">'
      +     '<div style="display:flex;align-items:flex-end;gap:8px;margin-bottom:8px">'
      +       '<div class="form-group" style="margin-bottom:0;flex:0 0 120px">'
      +         '<label>Port</label>'
      +         '<input class="form-input" id="owui-port" type="number" value="' + currentPort + '" min="1024" max="65535" style="padding:6px 10px" />'
      +       '</div>'
      +       '<button class="btn btn-secondary btn-sm" id="btn-owui-connect" style="margin-bottom:0">Connect</button>'
      +     '</div>'
      +     '<div id="owui-status" style="font-size:12px;color:var(--text-muted)">'
      +       '<div class="spinner" style="width:14px;height:14px;margin-right:8px"></div>'
      +       ' Checking health on port ' + currentPort + '...'
      +     '</div>'
      +   '</div>'
      +   '<div id="owui-content" style="margin-top:16px"></div>'
      + '</div>';

    document.getElementById('btn-owui-connect').addEventListener('click', function () {
      var newPort = parseInt(document.getElementById('owui-port').value) || 8080;
      currentPort = newPort;
      localStorage.setItem('wb_owui_port', String(newPort));
      doHealthCheck();
    });

    doHealthCheck();
  }

  function doHealthCheck() {
    currentChecked = false;
    var status = document.getElementById('owui-status');
    if (status) {
      status.innerHTML = '<div class="spinner" style="width:14px;height:14px;margin-right:8px"></div> Checking health on port ' + currentPort + '...';
    }

    if (healthCheckTimer) { clearTimeout(healthCheckTimer); }

    var url = 'http://localhost:' + currentPort + '/health';
    fetch(url, { mode: 'cors' })
      .then(function (resp) {
        if (resp.ok) {
          showOwuiActive();
        } else {
          showOwuiUnreachable();
        }
      })
      .catch(function () {
        showOwuiUnreachable();
      });
  }

  function showOwuiActive() {
    currentChecked = true;
    var status = document.getElementById('owui-status');
    if (status) {
      status.innerHTML = '<span class="status-dot active" style="width:8px;height:8px;margin-right:6px"></span> Running on port ' + currentPort;
    }

    var content = document.getElementById('owui-content');
    if (!content) return;

    var owuiUrl = 'http://localhost:' + currentPort + '/';

    content.innerHTML = ''
      + '<div class="card" style="padding:0;overflow:hidden">'
      +   '<div style="display:flex;justify-content:space-between;align-items:center;padding:12px 16px;background:var(--bg-hover);border-bottom:1px solid var(--border-color)">'
      +     '<span style="font-size:12px;color:var(--text-secondary)">' + owuiUrl + '</span>'
      +     '<a href="' + owuiUrl + '" target="_blank" class="btn btn-secondary btn-sm" style="text-decoration:none">Open in Tab</a>'
      +   '</div>'
      +   '<iframe id="owui-iframe"'
      +     ' src="' + owuiUrl + '"'
      +     ' style="width:100%;height:75vh;border:none"'
      +     ' sandbox="allow-same-origin allow-scripts allow-forms allow-popups allow-popups-to-escape-sandbox"'
      +     ' loading="lazy"'
      +     ' onerror="document.getElementById(\'owui-iframe-fallback\').style.display=\'block\';this.style.display=\'none\'">'
      +   '</iframe>'
      +   '<div id="owui-iframe-fallback" style="display:none;padding:40px;text-align:center">'
      +     '<p style="color:var(--text-muted);margin-bottom:16px">The Open WebUI refused to load in an embedded frame.</p>'
      +     '<a href="' + owuiUrl + '" target="_blank" class="btn btn-primary">Open in New Tab</a>'
      +   '</div>'
      + '</div>';
  }

  function showOwuiUnreachable() {
    currentChecked = true;
    var status = document.getElementById('owui-status');
    if (status) {
      status.innerHTML = '<span class="status-dot error" style="width:8px;height:8px;margin-right:6px"></span> Not running on port ' + currentPort;
    }

    var content = document.getElementById('owui-content');
    if (!content) return;

    content.innerHTML = ''
      + '<div class="card">'
      +   '<div class="card-header">Open WebUI Not Running</div>'
      +   '<p style="color:var(--text-muted);font-size:13px;margin-bottom:16px">'
      +     'The Open WebUI server is not reachable on port ' + currentPort + '. '
      +     'It must be launched via the Electron desktop wrapper or manually.'
      +   '</p>'
      +   '<div style="background:var(--bg-code);border:1px solid var(--border-color);border-radius:var(--radius-sm);padding:16px;margin-bottom:16px">'
      +     '<p style="font-size:12px;color:var(--text-secondary);margin-bottom:8px"><strong>Option A — Electron Wrapper</strong></p>'
      +     '<pre style="font-size:11px;background:transparent;padding:0">cd open-webui-wrapper\nnpm install\nnpm start</pre>'
      +     '<p style="font-size:12px;color:var(--text-secondary);margin-top:12px;margin-bottom:8px"><strong>Option B — Manual</strong></p>'
      +     '<pre style="font-size:11px;background:transparent;padding:0">uvx --from open-webui open-webui serve --port ' + currentPort + '</pre>'
      +   '</div>'
      +   '<div style="display:flex;gap:8px">'
      +     '<button class="btn btn-primary btn-sm" onclick="Router.setActive(\'owui\')">Retry Health Check</button>'
      +   '</div>'
      + '</div>';
  }
})();
