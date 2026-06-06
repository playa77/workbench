/** Open WebUI Tab Component
 * Embeds the Open WebUI instance via iframe inside the workbench.
 * Always health-checks before embedding.
 * OpenWebUI must be running at /open-webui/ via nginx reverse proxy.
 */

(function () {
  var healthChecked = false;
  var healthOk = false;

  Router.register("owui", renderOwuiTab);

  function renderOwuiTab(container) {
    container.innerHTML = ''
      + '<div style="max-width:1000px;margin:0 auto">'
      +   '<h2 style="margin-bottom:16px;font-size:20px;font-weight:600">Open WebUI</h2>'
      +   '<div class="card">'
      +     '<div id="owui-status" style="font-size:12px;color:var(--text-muted)">'
      +       '<div class="spinner" style="width:14px;height:14px;margin-right:8px"></div>'
      +       ' Checking Open WebUI status...'
      +     '</div>'
      +     '<div style="margin-top:12px;display:flex;gap:8px">'
      +       '<button class="btn btn-secondary btn-sm" id="btn-owui-retry">Retry</button>'
      +       '<a href="/open-webui/" target="_blank" class="btn btn-primary btn-sm" style="text-decoration:none">Open in New Tab</a>'
      +     '</div>'
      +   '</div>'
      +   '<div id="owui-content" style="margin-top:16px"></div>'
      + '</div>';

    document.getElementById('btn-owui-retry').addEventListener('click', function () {
      healthChecked = false;
      healthOk = false;
      doHealthCheck();
    });

    doHealthCheck();
  }

  function doHealthCheck() {
    var status = document.getElementById('owui-status');
    if (status) {
      status.innerHTML = '<div class="spinner" style="width:14px;height:14px;margin-right:8px"></div> Checking Open WebUI status...';
    }

    var url = '/open-webui/health';
    fetch(url)
      .then(function (resp) {
        if (resp.ok) {
          healthChecked = true;
          healthOk = true;
          showOwuiActive();
        } else {
          healthChecked = true;
          healthOk = false;
          showOwuiUnreachable();
        }
      })
      .catch(function () {
        healthChecked = true;
        healthOk = false;
        showOwuiUnreachable();
      });
  }

  function showOwuiActive() {
    var status = document.getElementById('owui-status');
    if (status) {
      status.innerHTML = '<span class="status-dot active" style="width:8px;height:8px;margin-right:6px"></span> Connected';
    }

    var content = document.getElementById('owui-content');
    if (!content) return;

    var owuiUrl = '/open-webui/';

    content.innerHTML = ''
      + '<div class="card" style="padding:0;overflow:hidden">'
      +   '<div style="display:flex;justify-content:space-between;align-items:center;padding:12px 16px;background:var(--bg-hover);border-bottom:1px solid var(--border-color)">'
      +     '<span style="font-size:12px;color:var(--text-secondary)">Open WebUI — embedded</span>'
      +     '<a href="/open-webui/" target="_blank" class="btn btn-primary btn-sm" style="text-decoration:none">Open in New Tab</a>'
      +   '</div>'
      +   '<iframe id="owui-iframe"'
      +     ' src="' + owuiUrl + '"'
      +     ' style="width:100%;height:75vh;border:none"'
      +     ' sandbox="allow-same-origin allow-scripts allow-forms allow-popups allow-popups-to-escape-sandbox allow-top-navigation"'
      +     ' allow="camera;microphone"'
      +     ' onerror="var fb=document.getElementById(\'owui-fallback\');if(fb)fb.style.display=\'block\';this.style.display=\'none\'">'
      +   '</iframe>'
      +   '<div id="owui-fallback" style="display:none;padding:40px;text-align:center">'
      +     '<p style="color:var(--text-muted);margin-bottom:16px">Open WebUI could not be loaded in the embedded frame.</p>'
      +     '<a href="/open-webui/" target="_blank" class="btn btn-primary">Open in New Tab</a>'
      +   '</div>'
      + '</div>';
  }

  function showOwuiUnreachable() {
    var status = document.getElementById('owui-status');
    if (status) {
      status.innerHTML = '<span class="status-dot error" style="width:8px;height:8px;margin-right:6px"></span> Open WebUI is not running';
    }

    var content = document.getElementById('owui-content');
    if (!content) return;

    content.innerHTML = ''
      + '<div class="card">'
      +   '<div class="card-header">Open WebUI Not Available</div>'
      +   '<p style="color:var(--text-muted);font-size:13px;margin-bottom:16px">'
      +     'The Open WebUI server could not be reached at /open-webui/. '
      +     'It should be running alongside the workbench via Docker Compose and nginx reverse proxy.'
      +   '</p>'
      +   '<div style="display:flex;gap:8px">'
      +     '<button class="btn btn-primary btn-sm" onclick="Router.setActive(\'owui\')">Retry Health Check</button>'
      +     '<a href="/open-webui/" target="_blank" class="btn btn-secondary btn-sm" style="text-decoration:none">Try Open WebUI Directly</a>'
      +   '</div>'
      + '</div>';
  }
})();
