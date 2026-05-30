/* ==========================================
   Workbench — API Client
   Centralized HTTP client with auth handling
   ========================================== */

const API = (() => {
  let apiKey = localStorage.getItem('wb_api_key') || '';
  const baseHeaders = () => {
    const h = { 'Content-Type': 'application/json' };
    if (apiKey) h['Authorization'] = `Bearer ${apiKey}`;
    return h;
  };

  async function request(method, path, body = undefined) {
    const opts = { method, headers: baseHeaders() };
    if (body !== undefined) opts.body = JSON.stringify(body);
    const resp = await fetch(path, opts);
    const data = await resp.json().catch(() => null);
    if (!resp.ok) {
      const err = new Error(data?.detail || resp.statusText);
      err.status = resp.status;
      throw err;
    }
    return data;
  }

  return {
    setApiKey(key) { apiKey = key; localStorage.setItem('wb_api_key', key); },
    getApiKey() { return apiKey; },
    hasApiKey() { return !!apiKey; },

    // Auth
    register(username) { return request('POST', '/api/v1/register', { username }); },
    me() { return request('GET', '/api/v1/me'); },
    setOpenRouterKey(key) { return request('POST', '/api/v1/me/openrouter-key', { api_key: key }); },
    deleteOpenRouterKey() { return request('DELETE', '/api/v1/me/openrouter-key'); },
    listApiKeys() { return request('GET', '/api/v1/me/api-keys'); },
    createApiKey(label) { return request('POST', '/api/v1/me/api-keys', { label }); },
    deleteApiKey(id) { return request('DELETE', `/api/v1/me/api-keys/${id}`); },

    // Agents
    listAgents() { return request('GET', '/api/v1/agents'); },
    getAgentSettings(name) { return request('GET', `/api/v1/agents/${name}/settings`); },
    updateAgentSettings(name, data) { return request('PUT', `/api/v1/agents/${name}/settings`, data); },

    // Tabs
    listTabs() { return request('GET', '/api/v1/tabs'); },

    // Health
    health() { return request('GET', '/health'); },
  };
})();
