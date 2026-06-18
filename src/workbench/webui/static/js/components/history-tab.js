/** History Tab Component
 *  Displays all past agent sessions in a unified, filterable list.
 *  Supports view, PDF export, and delete actions.
 */

(function () {
  Router.register('history', renderHistoryTab);

  var agentColors = {
    research: '#4a90d9',
    planning: '#7b61ff',
    debate: '#e67e22',
    chat: '#27ae60',
    deliberation: '#8e44ad',
    news: '#e74c3c',
  };

  var agentLabels = {
    research: 'Research',
    planning: 'Planning',
    debate: 'Debate',
    chat: 'Chat',
    deliberation: 'Deliberation',
    news: 'News',
  };

  function renderHistoryTab(container) {
    container.innerHTML = ''
      + '<div style="max-width:900px;margin:0 auto">'
      +   '<h2 style="margin-bottom:16px;font-size:20px;font-weight:600">Agent History</h2>'
      +   '<div style="margin-bottom:12px;display:flex;align-items:center;gap:8px">'
      +     '<label style="font-size:13px;color:var(--text-secondary);font-weight:500">Filter:</label>'
      +     '<select id="history-agent-filter" class="form-input" style="max-width:200px">'
      +       '<option value="">All Agents</option>'
      +       '<option value="research">Research</option>'
      +       '<option value="planning">Planning</option>'
      +       '<option value="debate">Debate</option>'
      +       '<option value="chat">Chat</option>'
      +       '<option value="deliberation">Deliberation</option>'
      +       '<option value="news">News</option>'
      +     '</select>'
      +     '<span id="history-template-picker"></span>'
      +   '</div>'
      +   '<div class="card">'
      +     '<div class="card-header">Saved Sessions</div>'
      +     '<div id="history-content" style="padding:8px 0">'
      +       '<div style="text-align:center;padding:24px;color:var(--text-muted)">Loading sessions...</div>'
      +     '</div>'
      +   '</div>'
      + '</div>';

    var filterEl = document.getElementById('history-agent-filter');
    filterEl.addEventListener('change', function () {
      loadSessions(filterEl.value);
    });

    loadSessions(filterEl.value);
  }

  function loadSessions(selectedAgent) {
    var content = document.getElementById('history-content');
    content.innerHTML = '<div style="text-align:center;padding:24px;color:var(--text-muted)">Loading sessions...</div>';

    API.listSessions(selectedAgent || undefined)
      .then(function (sessions) {
        if (!sessions || sessions.length === 0) {
          content.innerHTML = '<div style="text-align:center;padding:32px 16px;color:var(--text-muted)">'
            + 'No sessions found' + (selectedAgent ? ' for this agent type.' : '.')
            + '</div>';
          return;
        }

        var tableHtml = '<table style="width:100%;border-collapse:collapse;font-size:13px">'
          + '<thead><tr style="border-bottom:1px solid var(--border-color)">'
          + '<th style="padding:8px 12px;text-align:left;font-weight:600;color:var(--text-secondary);font-size:11px;text-transform:uppercase;letter-spacing:0.5px">Date</th>'
          + '<th style="padding:8px 12px;text-align:left;font-weight:600;color:var(--text-secondary);font-size:11px;text-transform:uppercase;letter-spacing:0.5px">Agent</th>'
          + '<th style="padding:8px 12px;text-align:left;font-weight:600;color:var(--text-secondary);font-size:11px;text-transform:uppercase;letter-spacing:0.5px">Title</th>'
          + '<th style="padding:8px 12px;text-align:right;font-weight:600;color:var(--text-secondary);font-size:11px;text-transform:uppercase;letter-spacing:0.5px">Words</th>'
          + '<th style="padding:8px 12px;text-align:right;font-weight:600;color:var(--text-secondary);font-size:11px;text-transform:uppercase;letter-spacing:0.5px">Actions</th>'
          + '</tr></thead><tbody id="history-table-body"></tbody></table>';

        content.innerHTML = tableHtml;

        if (window.renderTemplateSelector) {
          window.renderTemplateSelector('history-template-picker');
        }

        var tbody = document.getElementById('history-table-body');
        sessions.forEach(function (s) {
          var date = s.created_at ? s.created_at.split('T')[0] : '';
          var agent = s.agent_name || 'unknown';
          var color = agentColors[agent] || '#888';
          var label = agentLabels[agent] || agent;
          var title = Utils.escapeHtml((s.title || '').length > 80 ? s.title.substring(0, 77) + '...' : s.title || 'Untitled');
          var row = document.createElement('tr');
          row.style.borderBottom = '1px solid var(--border-color)';
          row.innerHTML = ''
            + '<td style="padding:8px 12px;color:var(--text-muted);font-size:12px">' + date + '</td>'
            + '<td style="padding:8px 12px"><span style="display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600;background:' + color + '22;color:' + color + '">' + Utils.escapeHtml(label) + '</span></td>'
            + '<td style="padding:8px 12px">' + title + '</td>'
            + '<td style="padding:8px 12px;text-align:right;color:var(--text-muted);font-size:12px">' + (s.word_count || 0) + '</td>'
            + '<td style="padding:8px 12px;text-align:right;white-space:nowrap">'
            + '<button class="btn btn-secondary btn-sm" data-action="view" data-id="' + s.id + '" style="margin-right:4px">View</button>'
            + '<button class="btn btn-secondary btn-sm" data-action="pdf" data-id="' + s.id + '" data-title="' + Utils.escapeHtml(s.title || 'Session') + '" style="margin-right:4px">PDF</button>'
            + '<button class="btn btn-danger btn-sm" data-action="delete" data-id="' + s.id + '" data-title="' + Utils.escapeHtml(s.title || 'Session') + '">Del</button>'
            + '</td>';
          tbody.appendChild(row);
        });

        // Wire up action buttons
        content.querySelectorAll('[data-action="view"]').forEach(function (btn) {
          btn.addEventListener('click', function () { viewSession(btn.dataset.id); });
        });
        content.querySelectorAll('[data-action="pdf"]').forEach(function (btn) {
          btn.addEventListener('click', function () { exportSessionPdf(btn.dataset.id, btn.dataset.title); });
        });
        content.querySelectorAll('[data-action="delete"]').forEach(function (btn) {
          btn.addEventListener('click', function () { deleteSession(btn.dataset.id, btn.dataset.title); });
        });
      })
      .catch(function () {
        content.innerHTML = '<div style="text-align:center;padding:32px">'
          + '<div style="color:var(--danger);margin-bottom:12px">Could not load sessions</div>'
          + '<button class="btn btn-primary btn-sm" onclick="window._historyLoadSessions()">Retry</button>'
          + '</div>';
        window._historyLoadSessions = function () {
          var filterEl = document.getElementById('history-agent-filter');
          loadSessions(filterEl ? filterEl.value : '');
        };
      });
  }

  function viewSession(id) {
    var content = document.getElementById('history-content');
    content.innerHTML = '<div style="text-align:center;padding:24px;color:var(--text-muted)">Loading session...</div>';

    API.getSession(id)
      .then(function (session) {
        var md = Utils.escapeHtml(session.content || '')
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

        var agent = session.agent_name || 'unknown';
        var color = agentColors[agent] || '#888';
        var label = agentLabels[agent] || agent;
        var date = session.created_at ? session.created_at.split('T')[0] : '';
        var metaHtml = '';
        if (session.metadata) {
          try {
            var meta = typeof session.metadata === 'string' ? JSON.parse(session.metadata) : session.metadata;
            var metaItems = [];
            Object.keys(meta).forEach(function (k) {
              var val = typeof meta[k] === 'object' ? JSON.stringify(meta[k]) : String(meta[k]);
              metaItems.push('<span style="font-size:11px;color:var(--text-muted)"><strong>' + Utils.escapeHtml(k) + ':</strong> ' + Utils.escapeHtml(val.length > 60 ? val.substring(0, 57) + '...' : val) + '</span>');
            });
            if (metaItems.length) metaHtml = '<div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:12px">' + metaItems.join('') + '</div>';
          } catch (_e) {}
        }

        content.innerHTML = ''
          + '<div style="padding:8px 0">'
          + '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px">'
          + '<h3 style="margin:0;font-size:16px;font-weight:600">' + Utils.escapeHtml(session.title || 'Session') + '</h3>'
          + '<button class="btn btn-secondary btn-sm" id="btn-back-to-list">Back to List</button>'
          + '</div>'
          + '<div style="display:flex;gap:12px;margin-bottom:12px;font-size:12px;color:var(--text-secondary)">'
          + '<span>Agent: <span style="display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600;background:' + color + '22;color:' + color + '">' + Utils.escapeHtml(label) + '</span></span>'
          + '<span>Date: ' + date + '</span>'
          + '<span>Words: ' + (session.word_count || 0) + '</span>'
          + '<span>Length: ' + (session.content_length || 0) + ' chars</span>'
          + '</div>'
          + metaHtml
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
          + 'Failed to load session: ' + Utils.escapeHtml(e.message) + '</div>';
      });
  }

  function exportSessionPdf(id, title) {
    var template = window.getSelectedTemplate ? window.getSelectedTemplate() : 'professional';
    API.getSession(id)
      .then(function (session) {
        Utils.exportMarkdownAsPdf(session.content || '', title || session.title || 'Session', template);
      })
      .catch(function (e) {
        Utils.showToast('Export failed: ' + e.message, 'error');
      });
  }

  function deleteSession(id, title) {
    if (!confirm('Delete session "' + title + '"?')) return;
    API.deleteSession(id)
      .then(function () {
        Utils.showToast('Session deleted', 'info');
        var filterEl = document.getElementById('history-agent-filter');
        loadSessions(filterEl ? filterEl.value : '');
      })
      .catch(function (e) {
        Utils.showToast('Delete failed: ' + e.message, 'error');
      });
  }
})();
