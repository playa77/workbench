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

  function exportMarkdownAsPdf(markdown, title, template, btn) {
    title = title || 'Report';
    template = template || 'professional';
    var apiKey = '';
    try { apiKey = (typeof API !== 'undefined' && API.getApiKey) ? API.getApiKey() : ''; } catch(e) {}

    var pdfBtn = btn || document.getElementById('btn-export-pdf');
    setButtonLoading(pdfBtn, 'Generating PDF...');

    return fetch('/api/v1/export/pdf', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + apiKey },
      body: JSON.stringify({ content: markdown, title: title, template: template }),
    })
      .then(function (resp) {
        if (!resp.ok) throw new Error('Export failed: ' + resp.status);
        return resp.blob();
      })
      .then(function (blob) {
        var url = URL.createObjectURL(blob);
        var a = document.createElement('a');
        a.href = url;
        a.download = title.replace(/[^a-zA-Z0-9]/g, '_') + '.pdf';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        resetButton(pdfBtn);
        showToast('PDF downloaded', 'success');
      })
      .catch(function (e) {
        resetButton(pdfBtn);
        showToast('Export failed: ' + e.message, 'error');
        throw e;
      });
  }

  /* ---- Confirmation Modal ---- */
  /* Nielsen #5 (Error Prevention), #3 (User Control): Replace native confirm()
     dialogs with accessible custom modals that show what will be deleted and
     explain consequences. Native confirm() is a modal trap with no undo. */

  /** Show a confirmation dialog.
   *  @param {string} title - Modal title (e.g. "Delete API Key")
   *  @param {string} message - Body text explaining what will happen and consequences
   *  @param {string} confirmLabel - Button text describing the action (e.g. "Delete 'Production Key'")
   *  @param {string} confirmStyle - CSS class for confirm button: 'danger', 'primary', 'warning'
   *  @returns {Promise<boolean>} - Resolves true if confirmed, false if cancelled
   */
  function showConfirm(title, message, confirmLabel, confirmStyle) {
    confirmStyle = confirmStyle || 'danger';
    return new Promise(function (resolve) {
      // Remove any existing modal
      var existing = document.getElementById('confirm-modal-overlay');
      if (existing) existing.remove();

      var overlay = document.createElement('div');
      overlay.id = 'confirm-modal-overlay';
      overlay.className = 'confirm-overlay';
      overlay.setAttribute('role', 'dialog');
      overlay.setAttribute('aria-modal', 'true');
      overlay.setAttribute('aria-labelledby', 'confirm-modal-title');

      var styleClass = 'btn-confirm-' + confirmStyle;
      overlay.innerHTML =
        '<div class="confirm-modal">' +
        '  <h3 class="confirm-title" id="confirm-modal-title">' + escapeHtml(title) + '</h3>' +
        '  <p class="confirm-message">' + message + '</p>' +
        '  <div class="confirm-actions">' +
        '    <button class="btn btn-secondary btn-cancel" id="confirm-btn-cancel">Cancel</button>' +
        '    <button class="btn ' + styleClass + '" id="confirm-btn-confirm">' + escapeHtml(confirmLabel) + '</button>' +
        '  </div>' +
        '</div>';

      document.body.appendChild(overlay);

      // Focus trap: focus the cancel button by default (safer choice)
      var cancelBtn = document.getElementById('confirm-btn-cancel');
      var confirmBtn = document.getElementById('confirm-btn-confirm');
      cancelBtn.focus();

      function cleanup() {
        if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
        document.removeEventListener('keydown', onKeydown);
      }

      function onKeydown(e) {
        if (e.key === 'Escape') {
          e.preventDefault();
          cleanup();
          resolve(false);
        }
        // Trap focus within modal
        if (e.key === 'Tab') {
          var focusable = overlay.querySelectorAll('button');
          if (focusable.length === 0) return;
          var first = focusable[0];
          var last = focusable[focusable.length - 1];
          if (e.shiftKey && document.activeElement === first) {
            e.preventDefault();
            last.focus();
          } else if (!e.shiftKey && document.activeElement === last) {
            e.preventDefault();
            first.focus();
          }
        }
      }

      document.addEventListener('keydown', onKeydown);

      cancelBtn.addEventListener('click', function () {
        cleanup();
        resolve(false);
      });

      confirmBtn.addEventListener('click', function () {
        cleanup();
        resolve(true);
      });

      // Close on overlay click (not on modal click)
      overlay.addEventListener('click', function (e) {
        if (e.target === overlay) {
          cleanup();
          resolve(false);
        }
      });
    });
  }

  return {
    escapeHtml: escapeHtml,
    showToast: showToast,
    showConfirm: showConfirm,
    setButtonLoading: setButtonLoading,
    setButtonSuccess: setButtonSuccess,
    resetButton: resetButton,
    exportMarkdownAsHtml: exportMarkdownAsHtml,
    exportMarkdownAsPdf: exportMarkdownAsPdf,
  };
})();

window.renderTemplateSelector = function(containerId) {
    fetch('/api/v1/export/templates', {
      headers: { 'Authorization': 'Bearer ' + (typeof API !== 'undefined' && API.getApiKey ? API.getApiKey() : '') },
    })
      .then(function(resp) { return resp.json(); })
      .then(function(templates) {
        var container = document.getElementById(containerId);
        if (!container || !templates || !templates.length) return;
        var sel = '<select id="template-select" style="padding:4px 8px;border-radius:4px;border:1px solid #444;background:#1a1f2e;color:#cbd5e1;font-size:12px;margin-right:4px">';
        for (var i = 0; i < templates.length; i++) {
          var t = templates[i];
          sel += '<option value="' + t.key + '"' + (t.key === 'professional' ? ' selected' : '') + '>' + t.name + '</option>';
        }
        sel += '</select>';
        container.innerHTML = sel + container.innerHTML;
        window._templateSelectorLoaded = true;
      })
      .catch(function() {});
};

window.getSelectedTemplate = function() {
    var sel = document.getElementById('template-select');
    return sel ? sel.value : 'professional';
};
