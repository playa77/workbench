/* ==========================================
   Workbench — Utility Helpers
   ========================================== */

const Utils = (() => {
  const entityMap = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  };

  function escapeHtml(str) {
    if (!str || typeof str !== 'string') return '';
    return str.replace(/[&<>"']/g, function (c) {
      return entityMap[c];
    });
  }

  /* ---- Toast notifications ---- */
  function getContainer() {
    var el = document.getElementById('toast-container');
    if (!el) {
      el = document.createElement('div');
      el.id = 'toast-container';
      el.className = 'toast-container';
      document.body.appendChild(el);
    }
    return el;
  }

  function showToast(message, type, duration) {
    type = type || 'info';
    duration = duration || 3000;
    var container = getContainer();
    var toast = document.createElement('div');
    toast.className = 'toast toast-' + type;
    var icons = { success: '\u2713', error: '\u2717', info: '\u2139' };
    toast.innerHTML = '<span style="font-size:14px">' + (icons[type] || icons.info) + '</span><span>' + escapeHtml(message) + '</span>';
    container.appendChild(toast);
    setTimeout(function () {
      if (toast.parentNode) toast.parentNode.removeChild(toast);
    }, duration);
  }

  /* ---- Button feedback ---- */
  function setButtonLoading(btn, loadingText) {
    if (!btn) return;
    btn.disabled = true;
    if (loadingText) {
      btn._originalText = btn.textContent;
      btn.textContent = loadingText;
    }
    btn.classList.add('btn-loading');
  }

  function setButtonSuccess(btn, successText) {
    if (!btn) return;
    btn.classList.remove('btn-loading');
    btn.disabled = false;
    if (successText) {
      btn.textContent = successText;
    }
    btn.classList.add('btn-success-flash');
    var originalText = btn._originalText;
    setTimeout(function () {
      btn.classList.remove('btn-success-flash');
      if (originalText) {
        btn.textContent = originalText;
        btn._originalText = null;
      }
      btn.disabled = false;
    }, 1200);
  }

  function resetButton(btn) {
    if (!btn) return;
    btn.classList.remove('btn-loading', 'btn-success-flash');
    btn.disabled = false;
    if (btn._originalText) {
      btn.textContent = btn._originalText;
      btn._originalText = null;
    }
  }

  /* ---- Markdown export ---- */
  function exportMarkdownAsHtml(markdown, title) {
    title = title || 'Report';
    // Convert markdown to HTML exactly as renderReport does
    var md = escapeHtml(markdown)
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.+?)\*/g, '<em>$1</em>')
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/^### (.+)$/gm, '<h3>$1</h3>')
      .replace(/^## (.+)$/gm, '<h2>$1</h2>')
      .replace(/^# (.+)$/gm, '<h1>$1</h1>')
      .replace(/^> (.+)$/gm, '<blockquote>$1</blockquote>')
      .replace(/^(  -|  \*) (.+)$/gm, '<li style="margin-left:40px">$2</li>')
      .replace(/^[-*] (.+)$/gm, '<li style="margin-left:20px">$1</li>')
      .replace(/\n\n/g, '</p><p>')
      .replace(/\n/g, '<br>');

    var html = '<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="UTF-8">\n'
      + '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
      + '<title>' + escapeHtml(title) + '</title>\n'
      + '<style>\n'
      + '  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; '
      + '    line-height: 1.7; max-width: 900px; margin: 0 auto; padding: 40px 24px; '
      + '    color: #1a1d23; background: #fff; }\n'
      + '  h1 { font-size: 24px; margin: 32px 0 16px; }\n'
      + '  h2 { font-size: 20px; margin: 28px 0 12px; }\n'
      + '  h3 { font-size: 17px; margin: 24px 0 8px; }\n'
      + '  p { margin-bottom: 12px; }\n'
      + '  code { font-family: "SF Mono", "Fira Code", monospace; font-size: 13px; '
      + '    background: #f0f3f5; padding: 2px 6px; border-radius: 4px; }\n'
      + '  pre { background: #f0f3f5; padding: 16px; border-radius: 6px; overflow-x: auto; }\n'
      + '  pre code { background: none; padding: 0; }\n'
      + '  blockquote { border-left: 3px solid #2563eb; padding: 4px 16px; '
      + '    margin: 12px 0; color: #666; font-style: italic; }\n'
      + '  @media print { body { padding: 0; } }\n'
      + '</style>\n</head>\n<body>\n'
      + '<p>' + md + '</p>\n'
      + '</body>\n</html>';

    var blob = new Blob([html], { type: 'text/html;charset=utf-8' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = title.replace(/[^a-zA-Z0-9]/g, '_') + '.html';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  function exportMarkdownAsPdf(markdown, title) {
    title = title || 'Report';
    // Use the backend endpoint to generate a PDF print page
    var apiKey = '';
    try { apiKey = (typeof API !== 'undefined' && API.getApiKey) ? API.getApiKey() : ''; } catch(e) {}
    fetch('/api/v1/export/pdf', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + apiKey },
      body: JSON.stringify({ content: markdown, title: title }),
    })
      .then(function (resp) { return resp.text(); })
      .then(function (html) {
        var w = window.open('', '_blank', 'width=900,height=700');
        if (w) {
          w.document.write(html);
          w.document.close();
          // Small delay so the browser can parse the document before printing
          setTimeout(function () { w.print(); }, 500);
        } else {
          // Fallback: open in same window
          var blob = new Blob([html], { type: 'text/html;charset=utf-8' });
          var url = URL.createObjectURL(blob);
          var a = document.createElement('a');
          a.href = url;
          a.target = '_blank';
          a.click();
          URL.revokeObjectURL(url);
          showToast('Opening print dialog...', 'info');
        }
      })
      .catch(function (e) {
        showToast('Export failed: ' + e.message, 'error');
      });
  }

  return {
    escapeHtml: escapeHtml,
    showToast: showToast,
    setButtonLoading: setButtonLoading,
    setButtonSuccess: setButtonSuccess,
    resetButton: resetButton,
    exportMarkdownAsHtml: exportMarkdownAsHtml,
    exportMarkdownAsPdf: exportMarkdownAsPdf,
  };
})();
