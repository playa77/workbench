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
    div.innerHTML = `<div style="font-size:11px;font-weight:600;margin-bottom:4px;color:var(--text-muted)">${role === 'user' ? 'You' : 'Assistant'}</div><div style="font-size:13px;white-space:pre-wrap">${content}</div>`;
    msgs.appendChild(div);
    msgs.scrollTop = msgs.scrollHeight;
  }

  window.chatSend = async () => {
    const input = document.getElementById('chat-input');
    const msg = input.value.trim();
    if (!msg) return;
    input.value = '';
    addMessage('user', msg);

    const key = API.getApiKey();
    try {
      const resp = await fetch('/api/v1/agents/chat/send', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${key}` },
        body: JSON.stringify({ message: msg }),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || 'Error');
      addMessage('assistant', data.response);
    } catch (e) {
      addMessage('assistant', 'Error: ' + e.message);
    }
  };
})();
