---
title: "MCP OAuth Authentication"
date: 2026-02-11
status: proposal
author: PlanExe
---

# MCP OAuth Authentication

**Status:** Proposal  
**Date:** 2026-02-11  
**Audience:** Developers implementing OAuth for the MCP server

---

## Overview

PlanExe's MCP server (`mcp.planexe.org`) currently uses API key authentication only. Users generate API keys at `home.planexe.org`, then pass them via `X-API-Key` or `Authorization: Bearer <key>`. The MCP Inspector's OAuth flow fails with "Failed to discover OAuth metadata" because the server does not expose OAuth discovery endpoints.

This proposal outlines what is required to support OAuth for MCP, enabling the Inspector's native OAuth UI and a more familiar sign-in flow for users.

---

## Current Architecture

| Component | Role |
|-----------|------|
| **frontend_multi_user** | OAuth *client* for web login (Google, GitHub, Discord via Authlib) |
| **mcp_cloud** | API key auth only. Gatekeeper uses `PLANEXE_MCP_API_KEY` (single env var) or no validation if unset |
| **UserApiKey** | Per-user API keys (`pex_...`) stored in DB, hashed. Used for credits and attribution in `task_create` |
| **home.planexe.org** | Users sign in, generate API keys, manage credits |

---

## MCP OAuth Requirements

For OAuth to work with the MCP Inspector and other standards-compliant MCP clients, the following must exist:

1. **Protected Resource Metadata** ([RFC 9728](https://www.rfc-editor.org/rfc/rfc9728)): The MCP server advertises where to get tokens. Served at:
   - `/.well-known/oauth-protected-resource`, or
   - `/.well-known/oauth-protected-resource/mcp` (path-specific)
   - Must include `authorization_servers` with at least one issuer URL

2. **WWW-Authenticate on 401**: When returning 401 Unauthorized, the server may include `resource_metadata` in the header so clients know where to discover auth.

3. **Authorization Server Metadata** ([RFC 8414](https://datatracker.ietf.org/doc/html/rfc8414)): The authorization server exposes discovery at:
   - `/.well-known/oauth-authorization-server`, or
   - `/.well-known/openid-configuration`
   - Describes `authorization_endpoint`, `token_endpoint`, `scopes_supported`, etc.

---

## Implementation Options

### Option A: PlanExe as Own Authorization Server (Recommended long-term)

**Idea:** home.planexe.org acts as the OAuth Authorization Server that issues tokens for mcp.planexe.org. Users sign in with existing OAuth (Google/GitHub/Discord); PlanExe issues short-lived JWTs for MCP use.

**Components:**

| Component | Where | Effort |
|-----------|-------|--------|
| OAuth AS metadata | `home.planexe.org/.well-known/oauth-authorization-server` | Low |
| Authorization endpoint | `GET /oauth/authorize` – redirect to login; after login, redirect back with `code` | Medium |
| Token endpoint | `POST /oauth/token` – exchange `code` for access token (JWT) | Medium |
| Protected resource metadata | `mcp.planexe.org/.well-known/oauth-protected-resource` – points to home.planexe.org as AS | Low |
| JWT validation in mcp_cloud | Validate Bearer JWTs issued by PlanExe; map `sub`/claims to `UserAccount` | Medium |
| Session → authorization code | Tie temporary `code` to logged-in user and desired scopes | Medium |

**Flow (summary):**

1. MCP client calls `GET https://mcp.planexe.org/mcp/` → 401 with `WWW-Authenticate` including `resource_metadata`
2. Client fetches Protected Resource Metadata → sees `authorization_servers: ["https://home.planexe.org"]`
3. Client fetches `https://home.planexe.org/.well-known/oauth-authorization-server`
4. Client redirects user to `https://home.planexe.org/oauth/authorize?response_type=code&client_id=...&redirect_uri=...&resource=https://mcp.planexe.org/mcp`
5. User signs in (or is already logged in) → redirect back with `code`
6. Client exchanges `code` for access token at `/oauth/token`
7. Client sends `Authorization: Bearer <token>` to mcp.planexe.org
8. mcp_cloud validates JWT, maps to `UserAccount` for credits and task attribution

**Estimated effort:** ~3–5 days for a minimal implementation.

---

### Option B: Third-Party Auth (Auth0, Keycloak, etc.)

**Idea:** Use an external OAuth Authorization Server. PlanExe would:

- Configure the provider with mcp.planexe.org as an audience/resource
- Expose Protected Resource Metadata pointing to that provider
- Validate JWTs in mcp_cloud signed by that provider
- Provision/link `UserAccount` from token claims (e.g. `sub`, `email`)

**Pros:** Less custom auth logic  
**Cons:** External dependency, possible cost, extra integration work

---

### Option C: "Get MCP Token" Page (Quick win)

**Idea:** Skip the full OAuth discovery flow. Add an endpoint on home.planexe.org that returns a short-lived MCP token when the user is logged in.

**Flow:**

1. User goes to home.planexe.org/account, signs in
2. Clicks "Get MCP access token" (or similar)
3. Server issues a short-lived JWT (e.g. 1 hour) bound to the user
4. User copies token, pastes into Inspector under Custom Headers → `Authorization: Bearer <token>`

**Pros:** Small change, works immediately with existing Inspector Custom Headers  
**Cons:** No native OAuth button in Inspector; manual copy-paste

**Estimated effort:** ~0.5–1 day.

---

## Recommendation

- **Short term:** Option C – add a "Get MCP token" button on the account page. Users continue using Custom Headers but with JWTs instead of long-lived API keys.
- **Long term:** Option A – implement PlanExe as an OAuth Authorization Server so the Inspector's built-in OAuth flow works end-to-end.

---

## References

- [MCP Authorization Specification](https://modelcontextprotocol.io/specification/draft/basic/authorization)
- [RFC 9728 – OAuth 2.0 Protected Resource Metadata](https://www.rfc-editor.org/rfc/rfc9728)
- [RFC 8414 – OAuth 2.0 Authorization Server Metadata](https://datatracker.ietf.org/doc/html/rfc8414)
- [docs/user_accounts_and_billing.md](../user_accounts_and_billing.md) – UserAccount, UserApiKey, credits
