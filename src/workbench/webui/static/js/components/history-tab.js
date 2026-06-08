/** History / Reports Tab Component
 *  Displays past research reports with view, export, copy, and delete actions.
 */

(function () {
  Router.register('history', renderHistoryTab);

  function renderHistoryTab(container) {
    container.innerHTML = ''
      + '<div style="max-width:900px;margin:0 auto">'
      +   '<h2 style="margin-bottom:16px;font-size:20px;font-weight:600">Research History</h2>'
      +   '<div class="card">'
      +     '<div class="card-header">Saved Reports</div>'
      +     '<div id="history-content" style="padding:8px 0">'
      +       '<div style="text-align:center;padding:24px;color:var(--text-muted)">Loading reports...</div>'
      +     '</div>'
      +   '</div>'
      + '</div>';

    loadReports();
  }

  function loadReports() {
    var content = document.getElementById('history-content');
    API.listReports()
      .then(function (reports) {
        if (!reports || reports.length === 0) {
          content.innerHTML = '<div style="text-align:center;padding:32px 16px;color:var(--text-muted)">'
            + 'No research reports yet. Start a deep research task to generate your first report.'
            + '</div>';
          return;
        }

        var tableHtml = '<table style="width:100%;border-collapse:collapse;font-size:13px">'
          + '<thead><tr style="border-bottom:1px solid var(--border-color)">'
          + '<th style="padding:8px 12px;text-align:left;font-weight:600;color:var(--text-secondary);font-size:11px;text-transform:uppercase;letter-spacing:0.5px">Date</th>'
          + '<th style="padding:8px 12px;text-align:left;font-weight:600;color:var(--text-secondary);font-size:11px;text-transform:uppercase;letter-spacing:0.5px">Title</th>'
          + '<th style="padding:8px 12px;text-align:right;font-weight:600;color:var(--text-secondary);font-size:11px;text-transform:uppercase;letter-spacing:0.5px">Words</th>'
          + '<th style="padding:8px 12px;text-align:right;font-weight:600;color:var(--text-secondary);font-size:11px;text-transform:uppercase;letter-spacing:0.5px">Actions</th>'
          + '</tr></thead><tbody id="history-table-body"></tbody></table>';

        content.innerHTML = tableHtml;

        var tbody = document.getElementById('history-table-body');
        reports.forEach(function (r) {
          var date = r.created_at ? r.created_at.split('T')[0] : '';
          var title = Utils.escapeHtml(r.title.length > 80 ? r.title.substring(0, 77) + '...' : r.title);
          var row = document.createElement('tr');
          row.style.borderBottom = '1px solid var(--border-color)';
          row.innerHTML = ''
            + '<td style="padding:8px 12px;color:var(--text-muted);font-size:12px">' + date + '</td>'
            + '<td style="padding:8px 12px">' + title + '</td>'
            + '<td style="padding:8px 12px;text-align:right;color:var(--text-muted);font-size:12px">' + (r.word_count || 0) + '</td>'
            + '<td style="padding:8px 12px;text-align:right;white-space:nowrap">'
            + '<button class="btn btn-secondary btn-sm" data-action="view" data-id="' + r.id + '" style="margin-right:4px">View</button>'
            + '<button class="btn btn-secondary btn-sm" data-action="pdf" data-id="' + r.id + '" data-title="' + Utils.escapeHtml(r.title) + '" style="margin-right:4px">PDF</button>'
            + '<button class="btn btn-secondary btn-sm" data-action="copy" data-id="' + r.id + '" style="margin-right:4px">Copy MD</button>'
            + '<button class="btn btn-danger btn-sm" data-action="delete" data-id="' + r.id + '" data-title="' + Utils.escapeHtml(r.title) + '">Del</button>'
            + '</td>';
          tbody.appendChild(row);
        });

        // Wire up action buttons
        content.querySelectorAll('[data-action="view"]').forEach(function (btn) {
          btn.addEventListener('click', function () { viewReport(btn.dataset.id); });
        });
        content.querySelectorAll('[data-action="pdf"]').forEach(function (btn) {
          btn.addEventListener('click', function () { exportReportPdf(btn.dataset.id, btn.dataset.title); });
        });
        content.querySelectorAll('[data-action="copy"]').forEach(function (btn) {
          btn.addEventListener('click', function () { copyReport(btn.dataset.id); });
        });
        content.querySelectorAll('[data-action="delete"]').forEach(function (btn) {
          btn.addEventListener('click', function () { deleteReport(btn.dataset.id, btn.dataset.title); });
        });
      })
      .catch(function () {
        content.innerHTML = '<div style="text-align:center;padding:32px">'
          + '<div style="color:var(--danger);margin-bottom:12px">Could not load reports</div>'
          + '<button class="btn btn-primary btn-sm" onclick="window._historyLoadReports()">Retry</button>'
          + '</div>';
        window._historyLoadReports = loadReports;
      });
  }

  function viewReport(id) {
    var content = document.getElementById('history-content');
    // Show loading
    content.innerHTML = '<div style="text-align:center;padding:24px;color:var(--text-muted)">Loading report...</div>';

    API.getReport(id)
      .then(function (report) {
        var md = Utils.escapeHtml(report.content || '')
          .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
          .replace(/\*(.+?)\*/g, '<em>$1</em>')
          .replace(/`([^`]+)`/g, '<code>$1</code>')
          .replace(/^### (.+)$/gm, '<h3 style="margin:20px 0 8px;font-size:16px;font-weight:600">$1</h3>')
          .replace(/^## (.+)$/gm, '<h2 style="margin:24px 0 12px;font-size:18px;font-weight:700">$1</h2>')
          .replace(/^# (.+)$/gm, '<h1 style="margin:28px 0 16px;font-size:20px;font-weight:700">$1</h1>')
          .replace(/^> (.+)$/gm, '<blockquote style="border-left:3px solid var(--accent);padding:4px 12px;margin:8px 0;color:var(--text-muted);font-style:italic">$1</blockquote>')
          .replace(/^(  -|  \*) (.+)$/gm, '<li style="margin-left:40px">$2</li>')
          .replace(/^[-*] (.+)$/gm, '<li style="margin-left:20px">$1</li>')
          .replace(/\n\n/g, '</p><p style="margin-bottom:8px;line-height:1.7">')
          .replace(/\n/g, '<br>');

        content.innerHTML = ''
          + '<div style="padding:8px 0">'
          + '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px">'
          + '<h3 style="margin:0;font-size:16px;font-weight:600">' + Utils.escapeHtml(report.title || 'Report') + '</h3>'
          + '<button class="btn btn-secondary btn-sm" id="btn-back-to-list">Back to List</button>'
          + '</div>'
          + '<div style="line-height:1.7;font-size:13px;background:var(--bg-card);border:1px solid var(--border-color);border-radius:var(--radius-sm);padding:20px">'
          + '<p style="margin-bottom:8px;line-height:1.7">' + md + '</p>'
          + '</div>'
          + '</div>';

        document.getElementById('btn-back-to-list').addEventListener('click', function () {
          renderHistoryTab(document.getElementById('active-tab-content'));
        });
      })
      .catch(function (e) {
        content.innerHTML = '<div style="text-align:center;padding:24px;color:var(--danger)">'
          + 'Failed to load report: ' + Utils.escapeHtml(e.message) + '</div>';
      });
  }

  function exportReportPdf(id, title) {
    API.getReport(id)
      .then(function (report) {
        Utils.exportMarkdownAsPdf(report.content, title || report.title || 'Report');
      })
      .catch(function (e) {
        Utils.showToast('Export failed: ' + e.message, 'error');
      });
  }

  function copyReport(id) {
    API.getReport(id)
      .then(function (report) {
        navigator.clipboard.writeText(report.content || '').then(function () {
          Utils.showToast('Copied to clipboard', 'success');
        }).catch(function () {
          Utils.showToast('Could not copy to clipboard', 'error');
        });
      })
      .catch(function (e) {
        Utils.showToast('Failed: ' + e.message, 'error');
      });
  }

  function deleteReport(id, title) {
    if (!confirm('Delete report "' + title + '"?')) return;
    API.deleteReport(id)
      .then(function () {
        Utils.showToast('Report deleted', 'info');
        loadReports();
      })
      .catch(function (e) {
        Utils.showToast('Delete failed: ' + e.message, 'error');
      });
  }
})();
