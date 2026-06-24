/** Chat Agent Tab Component */

(function () {
  Router.register("chat", renderChatTab);

  function renderChatTab(container) {
    container.innerHTML = `
      <div style="max-width:800px;margin:0 auto">
        <h2 style="margin-bottom:16px;font-size:20px;font-weight:600">Chat</h2>
        <div id="chat-messages" style="min-height:400px;max-height:60vh;overflow-y:auto;margin-bottom:16px;padding:16px;background:var(--bg-card);border:1px solid var(--border-color);border-radius:var(--radius)"></div>
        <div style="display:flex;gap:8px">
          <select class="form-input" id="chat-model" style="font-size:12px;padding:6px 10px;width:auto;flex-shrink:0;max-width:260px" disabled data-tooltip="Select which LLM model to use for chat. Configure models in Settings → Inference Providers." data-help-page="/static/help/chat.html#model-selector">
            <option>Loading models...</option>
          </select>
          <input class="form-input" id="chat-input" placeholder="Type your message..." style="flex:1" onkeydown="if(event.key==='Enter')window.chatSend()" data-tooltip="Type your message and press Enter to send. The AI will respond using the selected model." data-help-page="/static/help/chat.html#message-input" />
          <button class="btn btn-primary" onclick="window.chatSend()" data-tooltip="Send your message to the AI. The button shows a loading state while the response is being generated." data-help-page="/static/help/chat.html#send-button">Send</button>
        </div>
        <div style="margin-top:8px;font-size:11px;color:var(--text-muted);text-align:center">Powered by your inference provider</div>
      </div>`;

    document.getElementById('chat-messages').innerHTML = '<div style="text-align:center;color:var(--text-muted);padding:40px">Start a conversation</div>';

    // Fetch available models dynamically from the backend
    var modelSelect = document.getElementById('chat-model');
    fetch('/api/v1/me/inference/models')
      .then(function (resp) { return resp.json(); })
      .then(function (data) {
        var models = data.models || [];
        var defaultModel = data.default_model || (models.length > 0 ? models[0] : '');
        modelSelect.innerHTML = '';
        models.forEach(function (m) {
          var opt = document.createElement('option');
          opt.value = m;
          opt.textContent = m;
          if (m === defaultModel) opt.selected = true;
          modelSelect.appendChild(opt);
        });
        modelSelect.disabled = false;
      })
      .catch(function () {
        modelSelect.innerHTML = '<option value="">No models available</option>';
        modelSelect.disabled = false;
      });

    renderChatPastSessions();
  }

  // Past Chat Sessions
  var chatPastLoaded = false;

  function renderChatPastSessions() {
    var container = document.getElementById('chat-messages');
    if (!container) return;
    container.insertAdjacentHTML('afterend', ''
      + '<div class="card" style="margin-top:24px">'
      +   '<div class="card-header" style="cursor:pointer;display:flex;justify-content:space-between;align-items:center" id="chat-past-toggle" data-tooltip="Click to expand or collapse the list of previous chat sessions. Click a session to reload it." data-help-page="/static/help/chat.html#past-sessions">'
      +     '<span>Past Chat Sessions</span>'
      +     '<span id="chat-past-arrow" style="font-size:12px">&#x25BC;</span>'
      +   '</div>'
      +   '<div id="chat-past-sessions" style="display:none;padding:8px 0">'
      +     '<div style="text-align:center;padding:12px;color:var(--text-muted)">Loading...</div>'
      +   '</div>'
      + '</div>'
    );

    document.getElementById('chat-past-toggle').addEventListener('click', function () {
      var body = document.getElementById('chat-past-sessions');
      var arrow = document.getElementById('chat-past-arrow');
      if (body.style.display === 'none') {
        body.style.display = 'block';
        arrow.innerHTML = '&#x25B2;';
        if (!chatPastLoaded) {
          chatPastLoaded = true;
          loadChatPastSessions();
        }
      } else {
        body.style.display = 'none';
        arrow.innerHTML = '&#x25BC;';
      }
    });
  }

  function loadChatPastSessions() {
    var body = document.getElementById('chat-past-sessions');
    API.listSessions('chat').then(function (sessions) {
      if (!sessions || sessions.length === 0) {
        body.innerHTML = '<div style="text-align:center;padding:12px;color:var(--text-muted);font-size:12px">No past chat sessions</div>';
        return;
      }
      var recent = sessions.slice(0, 10);
      body.innerHTML = recent.map(function (s) {
        var date = s.created_at ? s.created_at.split('T')[0] : '';
        var title = Utils.escapeHtml((s.title || 'Chat').length > 60 ? s.title.substring(0, 57) + '...' : s.title || 'Chat');
        return '<div style="display:flex;justify-content:space-between;align-items:center;padding:8px 12px;border-bottom:1px solid var(--border-color);cursor:pointer" data-session-id="' + s.id + '" class="chat-past-item">'
          + '<span style="font-size:12px;color:var(--text-muted);flex-shrink:0;margin-right:12px">' + date + '</span>'
          + '<span style="font-size:13px;flex:1">' + title + '</span>'
          + '<span style="font-size:11px;color:var(--text-muted);flex-shrink:0">' + (s.word_count || 0) + ' words</span>'
          + '</div>';
      }).join('');
      body.querySelectorAll('.chat-past-item').forEach(function (el) {
        el.addEventListener('click', function () {
          loadPastChatSession(el.dataset.sessionId);
        });
      });
    }).catch(function () {
      body.innerHTML = '<div style="text-align:center;padding:12px;color:var(--danger);font-size:12px">Failed to load sessions</div>';
    });
  }

  function loadPastChatSession(id) {
    API.getSession(id).then(function (session) {
      var msgs = document.getElementById('chat-messages');
      if (!msgs) return;
      var content = session.content || '';
      // Try to parse as JSON array of messages
      try {
        var messages = JSON.parse(content);
        if (Array.isArray(messages)) {
          msgs.innerHTML = '';
          messages.forEach(function (m) {
            addMessage(m.role || 'user', m.content || '');
          });
          return;
        }
      } catch (_e) { /* fall through */ }
      // Fallback: show as raw text
      msgs.innerHTML = '';
      addMessage('assistant', content);
    }).catch(function (e) {
      Utils.showToast('Failed to load session: ' + e.message, 'error');
    });
  }

  function addMessage(role, content) {
    const msgs = document.getElementById('chat-messages');
    if (msgs.querySelector('div[style*="text-align:center"]')) msgs.innerHTML = '';
    const div = document.createElement('div');
    div.style.cssText = `margin-bottom:12px;padding:10px 14px;border-radius:var(--radius-sm);max-width:85%;${
      role === 'user'
        ? 'margin-left:auto;background:var(--accent-bg);color:var(--text-primary)'
        : 'background:var(--bg-hover);color:var(--text-primary)'
    }`;
    div.innerHTML = `<div style="font-size:11px;font-weight:600;margin-bottom:4px;color:var(--text-muted)">${role === 'user' ? 'You' : 'Assistant'}</div><div style="font-size:13px;white-space:pre-wrap">${Utils.escapeHtml(content)}</div>`;
    msgs.appendChild(div);
    msgs.scrollTop = msgs.scrollHeight;
  }

  window.chatSend = async () => {
    const input = document.getElementById('chat-input');
    const msg = input.value.trim();
    if (!msg) return;
    input.value = '';
    addMessage('user', msg);

    // Add a temporary loading message
    const msgs = document.getElementById('chat-messages');
    const loadingDiv = document.createElement('div');
    loadingDiv.id = 'chat-loading-msg';
    loadingDiv.style.cssText = 'margin-bottom:12px;padding:10px 14px;border-radius:var(--radius-sm);max-width:85%;background:var(--bg-hover);color:var(--text-primary);display:flex;align-items:center;gap:8px';
    loadingDiv.innerHTML = '<div style="font-size:11px;font-weight:600;margin-bottom:0;color:var(--text-muted)">Assistant</div><div class="spinner" style="width:14px;height:14px;border-width:2px"></div><span style="font-size:12px;color:var(--text-muted)">Thinking...</span>';
    msgs.appendChild(loadingDiv);
    msgs.scrollTop = msgs.scrollHeight;

    // Disable the send button
    const sendBtn = document.querySelector('#chat-input + button') || document.querySelector('button[onclick="window.chatSend()"]');
    if (sendBtn) Utils.setButtonLoading(sendBtn);

    try {
      const resp = await fetch('/api/v1/agents/chat/send', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: msg, model: document.getElementById('chat-model').value }),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || 'Error');

      // Remove loading indicator
      const ld = document.getElementById('chat-loading-msg');
      if (ld) ld.remove();

      addMessage('assistant', data.response);
    } catch (e) {
      const ld = document.getElementById('chat-loading-msg');
      if (ld) ld.remove();
      addMessage('assistant', 'Error: ' + Utils.escapeHtml(e.message));
      Utils.showToast(e.message, 'error');
    } finally {
      if (sendBtn) Utils.resetButton(sendBtn);
    }
  };
})();
