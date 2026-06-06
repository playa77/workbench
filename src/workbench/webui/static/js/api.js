const API = (() => {
  async function request(method, path, body) {
    var opts = { method: method, headers: { 'Content-Type': 'application/json' } };
    if (body !== undefined) opts.body = JSON.stringify(body);
    var resp = await fetch(path, opts);
    var data = await resp.json().catch(function() { return null; });
    if (!resp.ok) {
      var err = new Error(data && data.detail ? data.detail : resp.statusText);
      err.status = resp.status;
      throw err;
    }
    return data;
  }

  return {
    setupStatus: function() { return request('GET', '/api/v1/auth/setup-status'); },
    setup: function(username, email, password) { return request('POST', '/api/v1/auth/setup', { username: username, email: email, password: password }); },
    passwordLogin: function(emailOrUsername, password) { return request('POST', '/api/v1/auth/login', { email_or_username: emailOrUsername, password: password }); },
    apiKeyLogin: function(key) { return request('POST', '/api/v1/auth/login', { api_key: key }); },
    logout: function() { return request('POST', '/api/v1/auth/logout'); },
    me: function() { return request('GET', '/api/v1/me'); },
    forgotPassword: function(email) { return request('POST', '/api/v1/auth/forgot-password', { email: email }); },
    resetPassword: function(token, password) { return request('POST', '/api/v1/auth/reset-password', { token: token, password: password }); },
    acceptInvite: function(token, password) { return request('POST', '/api/v1/auth/accept-invite', { token: token, password: password }); },
    changePassword: function(currentPassword, newPassword) { return request('POST', '/api/v1/me/change-password', { current_password: currentPassword, new_password: newPassword }); },
    listInvites: function() { return request('GET', '/api/v1/admin/invites'); },
    createInvite: function(email, username) { return request('POST', '/api/v1/admin/invites', { email: email, username: username }); },
    deleteInvite: function(id) { return request('DELETE', '/api/v1/admin/invites/' + id); },
    setOpenRouterKey: function(key) { return request('POST', '/api/v1/me/openrouter-key', { api_key: key }); },
    deleteOpenRouterKey: function() { return request('DELETE', '/api/v1/me/openrouter-key'); },
    listApiKeys: function() { return request('GET', '/api/v1/me/api-keys'); },
    createApiKey: function(label) { return request('POST', '/api/v1/me/api-keys', { label: label }); },
    deleteApiKey: function(id) { return request('DELETE', '/api/v1/me/api-keys/' + id); },
    listAgents: function() { return request('GET', '/api/v1/agents'); },
    getAgentSettings: function(name) { return request('GET', '/api/v1/agents/' + name + '/settings'); },
    updateAgentSettings: function(name, data) { return request('PUT', '/api/v1/agents/' + name + '/settings', data); },
    listTabs: function() { return request('GET', '/api/v1/tabs'); },
    getApiKey: function() { return ''; },
    health: function() { return request('GET', '/health'); },
  };
})();
