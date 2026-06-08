/** Chat Agent Tab Component */

(function () {
  Router.register("chat", renderChatTab);

  function renderChatTab(container) {
    container.innerHTML = `
      <div style="max-width:800px;margin:0 auto">
        <h2 style="margin-bottom:16px;font-size:20px;font-weight:600">Chat</h2>
        <div id="chat-messages" style="min-height:400px;max-height:60vh;overflow-y:auto;margin-bottom:16px;padding:16px;background:var(--bg-card);border:1px solid var(--border-color);border-radius:var(--radius)"></div>
        <div style="display:flex;gap:8px">
          <input class="form-input" id="chat-input" placeholder="Type your message..." style="flex:1" onkeydown="if(event.key==='Enter')window.chatSend()" />
          <button class="btn btn-primary" onclick="window.chatSend()">Send</button>
        </div>
        <div style="margin-top:8px;font-size:11px;color:var(--text-muted);text-align:center">Powered by your OpenRouter API key</div>
      </div>`;

    document.getElementById('chat-messages').innerHTML = '<div style="text-align:center;color:var(--text-muted);padding:40px">Start a conversation</div>';
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
        body: JSON.stringify({ message: msg }),
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
