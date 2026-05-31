/* ==========================================
   Workbench — API Client
   Centralized HTTP client — auth via httpOnly cookies
   ========================================== */

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
    login: function(key) { return request('POST', '/api/v1/auth/login', { api_key: key }); },
    logout: function() { return request('POST', '/api/v1/auth/logout'); },
    register: function(username) { return request('POST', '/api/v1/register', { username: username }); },
    me: function() { return request('GET', '/api/v1/me'); },
    setOpenRouterKey: function(key) { return request('POST', '/api/v1/me/openrouter-key', { api_key: key }); },
    deleteOpenRouterKey: function() { return request('DELETE', '/api/v1/me/openrouter-key'); },
    listApiKeys: function() { return request('GET', '/api/v1/me/api-keys'); },
    createApiKey: function(label) { return request('POST', '/api/v1/me/api-keys', { label: label }); },
    deleteApiKey: function(id) { return request('DELETE', '/api/v1/me/api-keys/' + id); },
    listAgents: function() { return request('GET', '/api/v1/agents'); },
    getAgentSettings: function(name) { return request('GET', '/api/v1/agents/' + name + '/settings'); },
    updateAgentSettings: function(name, data) { return request('PUT', '/api/v1/agents/' + name + '/settings', data); },
    listTabs: function() { return request('GET', '/api/v1/tabs'); },
    health: function() { return request('GET', '/health'); },
  };
})();
