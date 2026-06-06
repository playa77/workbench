# Workbench -- Deployment Guide

This document covers production deployment of Workbench. For local development setup, see [README.md](README.md).

---

## Table of Contents

1. [Architecture](#architecture)
2. [Prerequisites](#prerequisites)
3. [Docker Compose Deployment](#docker-compose-deployment)
   - [Step 1: Prepare](#step-1-prepare)
   - [Step 2: Environment File](#step-2-environment-file)
   - [Step 3: Generate Secrets](#step-3-generate-secrets)
   - [Step 4: Build and Start](#step-4-build-and-start)
   - [Step 5: Install nginx Reverse Proxy](#step-5-install-nginx-reverse-proxy)
   - [Step 6: Verify](#step-6-verify)
   - [Step 7: Create Admin User](#step-7-create-admin-user)
   - [Step 8: Access](#step-8-access)
4. [Open WebUI Integration](#open-webui-integration)
5. [Service Management](#service-management)
6. [Reverse Proxy with TLS](#reverse-proxy-with-tls)
7. [Bare-Metal Deployment](#bare-metal-deployment)
8. [Health Checks](#health-checks)
9. [Backup and Restore](#backup-and-restore)
10. [Upgrading](#upgrading)
11. [Logging and Monitoring](#logging-and-monitoring)
12. [Security Hardening Checklist](#security-hardening-checklist)
13. [Troubleshooting](#troubleshooting)
14. [Environment Variable Reference](#environment-variable-reference)

---

## Architecture

```
                           ┌─────────────────────────────────────┐
Internet ──→ nginx (:80) ──┤  /             → workbench :8420    │ 127.0.0.1 only
                           │  /open-webui/  → open-webui :3000   │ 127.0.0.1 only
                           └─────────────────────────────────────┘
```

**nginx is the only service exposed to the network.** Both Workbench and Open WebUI bind exclusively to `127.0.0.1` — they are never directly reachable from outside. Open WebUI is proxied through nginx at the `/open-webui/` sub-path with content rewriting so the iframe embedded in Workbench loads correctly.

---

## Prerequisites

### Required

* **OpenRouter API key** -- [sign up](https://openrouter.ai) (free, pay-per-token). Key format: `sk-or-v1-...`
* **A machine** running Linux (amd64/arm64). Minimum: 1 CPU, 1 GB RAM, 2 GB disk. Recommended: 2 CPUs, 2 GB RAM, 10 GB disk.
* **Docker and Docker Compose** (v2+)
* **nginx** (installed in step 5)

### Supported Databases

| Environment | Database | Driver |
|---|---|---|
| Production (Docker) | PostgreSQL 16 + pgvector | asyncpg |
| Production (bare-metal) | PostgreSQL 14+ or SQLite | asyncpg / aiosqlite |
| Development / Testing | SQLite (in-memory or file) | aiosqlite |

---

## Docker Compose Deployment

Three containers: PostgreSQL 16 (pgvector), Workbench application, and optional Open WebUI.

### Step 1: Prepare

```bash
git clone https://github.com/your-org/workbench.git
cd workbench
```

### Step 2: Environment File

```bash
cp .env.example .env
chmod 600 .env
```

### Step 3: Generate Secrets

```bash
# Generate a 64-hex-char AES encryption key
python3 -c "import secrets; print(secrets.token_hex(32))"

# Generate a strong PostgreSQL password
python3 -c "import secrets; print(secrets.token_urlsafe(24))"
```

Edit `.env` and fill in:

```ini
POSTGRES_USER=workbench
POSTGRES_PASSWORD=<your-generated-password>
POSTGRES_DB=workbench
ENCRYPTION_KEY=<64-hex-char-key>
# Optional: server-wide OpenRouter fallback key
OPENROUTER_API_KEY=sk-or-v1-...
```

**All four values are mandatory.** Docker Compose will fail with an error if `POSTGRES_USER`, `POSTGRES_PASSWORD`, or `ENCRYPTION_KEY` is missing or empty.

### Step 4: Build and Start

```bash
docker compose build workbench
docker compose --profile openwebui up -d
```

Wait ~10 seconds for PostgreSQL to become healthy, then Workbench starts. The `--profile openwebui` flag includes the optional Open WebUI container; omit it if you don't want Open WebUI.

### Step 5: Install nginx Reverse Proxy

Both Workbench and Open WebUI bind to `127.0.0.1` only. nginx acts as the single public entry point.

```bash
sudo apt install -y nginx
```

Create `/etc/nginx/sites-available/workbench`:

```nginx
server {
    listen 80;
    server_name _;  # for TLS, replace with your domain (see Reverse Proxy with TLS below)

    # Workbench application (default route)
    location / {
        proxy_pass http://127.0.0.1:8420;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
        proxy_read_timeout 600s;
        proxy_send_timeout 600s;
    }

    # Open WebUI — proxied at /open-webui/ with path rewriting
    location /open-webui/ {
        rewrite ^/open-webui(/.*)$ $1 break;
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_buffering off;
        proxy_read_timeout 1800s;
        proxy_send_timeout 1800s;

        # Rewrite absolute paths so the SPA works under /open-webui/
        sub_filter_types application/javascript application/json text/css text/html;
        sub_filter_once off;
        sub_filter 'href="/' 'href="/open-webui/';
        sub_filter "href='/" "href='/open-webui/";
        sub_filter ' "/_app/' ' "/open-webui/_app/';
        sub_filter " '/_app/" " '/open-webui/_app/";
        sub_filter ' "/api/' ' "/open-webui/api/';
        sub_filter " '/api/" " '/open-webui/api/";
        sub_filter ' "/ws/' ' "/open-webui/ws/';
        sub_filter ' "/static/' ' "/open-webui/static/';
        sub_filter ' "/favicon' ' "/open-webui/favicon';
        sub_filter ' "/opensearch' ' "/open-webui/opensearch';
    }
}
```

Enable it:

```bash
sudo rm -f /etc/nginx/sites-enabled/default
sudo ln -s /etc/nginx/sites-available/workbench /etc/nginx/sites-enabled/workbench
sudo nginx -t
sudo systemctl reload nginx
sudo systemctl enable nginx
```

### Step 6: Verify

```bash
# Health check via nginx
curl http://localhost/health
# Expected: {"status":"ok","version":"0.1.0"}

# Workbench UI via nginx
curl -s -o /dev/null -w "%{http_code}" http://localhost/
# Expected: 200

# Open WebUI via nginx proxy
curl -s -o /dev/null -w "%{http_code}" http://localhost/open-webui/
# Expected: 200

# Verify internal ports are NOT exposed externally:
curl --connect-timeout 3 -s -o /dev/null -w "%{http_code}" http://<server-ip>:8420/health
# Expected: 000
curl --connect-timeout 3 -s -o /dev/null -w "%{http_code}" http://<server-ip>:3000/health
# Expected: 000

# Check container health
docker compose ps
```

### Step 7: Create Admin User

```bash
docker compose exec workbench workbench create-user admin
# Save the API key output — it is shown only once.
```

### Step 8: Access

Open `http://<your-server>` in a browser. Log in with the API key from step 7.

---

## Open WebUI Integration

Workbench includes an optional Open WebUI container that embeds via iframe in the "Open WebUI" tab. Open WebUI is **never exposed publicly** — it is only reachable through the nginx reverse proxy at `/open-webui/`.

### Why this design

Open WebUI (a SvelteKit app) does not support sub-path hosting natively — its static assets, API calls, and WebSocket connections use hardcoded absolute paths (`/_app/`, `/api/`, `/ws/`). **Open WebUI maintainers have explicitly rejected sub-path support** in favour of subdomain-only deployments. We work around this with nginx `sub_filter` that rewrites absolute paths in responses, making the SPA functional under `/open-webui/`.

### Start with Open WebUI

```bash
docker compose --profile openwebui up -d
```

The container binds to `127.0.0.1:3000`. nginx proxies it at `/open-webui/`.

### How the iframe works

The Workbench frontend (`owui-tab.js`) health-checks `/open-webui/health` and loads the iframe at `/open-webui/`. The CSP header allows this via `frame-src 'self'` — no external origins permitted.

### Limitations of sub_filter proxying

The `sub_filter` approach rewrites paths in text-based responses (HTML, CSS, JS, JSON). This covers almost all Open WebUI functionality, but note:

* **Client-side navigation** (SvelteKit's `goto()`) may break on page refresh. Use the browser back button or re-navigate from the Open WebUI UI.
* **WebSocket connections** work correctly since nginx passes through the `Upgrade` header.
* After upgrading the Open WebUI image, re-test the sub-path rewrite rules.

### Custom Open WebUI URL

If using an external Open WebUI instance (not the bundled container), configure it via the `WORKBENCH_API__CSP_HEADER` environment variable:

```bash
WORKBENCH_API__CSP_HEADER="default-src 'self'; ...; frame-src 'self' https://open-webui.yourdomain.com"
```

If pointing to an external instance served at a subdomain (the recommended approach by Open WebUI maintainers), update `owui-tab.js`'s iframe URL accordingly.

---

## Service Management

```bash
# Show container status (all profiles)
docker compose ps

# With Open WebUI
docker compose --profile openwebui ps

# Follow logs
docker compose logs -f workbench
docker compose logs -f open-webui   # if running with --profile openwebui

# Restart after config changes
docker compose --profile openwebui restart workbench

# Stop and remove containers (preserves volumes)
docker compose --profile openwebui down

# Stop and destroy all data (⚠️ irreversible)
docker compose --profile openwebui down -v

# Rebuild image after source changes
docker compose build workbench
docker compose --profile openwebui up -d

# nginx management
sudo systemctl restart nginx
sudo systemctl status nginx
sudo nginx -t
```

---

## Reverse Proxy with TLS

For public access with HTTPS, extend the nginx config with Let's Encrypt.

### Prerequisites

- A domain name with an A record pointing to your server's IP (e.g. Cloudflare DNS).
- The domain must resolve publicly before running certbot. Check with `dig +short your-domain.com A`.

### Install certbot

```bash
sudo apt install -y certbot python3-certbot-nginx
```

### Update nginx config for domain

Update `/etc/nginx/sites-available/workbench` to use your domain name instead of `_`:

```diff
-    server_name _;
+    server_name your-domain.com;
```

Reload:

```bash
sudo nginx -t && sudo systemctl reload nginx
```

Verify it responds on the domain:

```bash
curl http://your-domain.com/health
# Expected: {"status":"ok","version":"0.1.0"}
```

### Obtain Let's Encrypt certificate

Certbot automatically validates domain ownership (HTTP challenge), obtains a certificate, and rewrites the nginx config for HTTPS with HTTP→HTTPS redirect:

```bash
sudo certbot --nginx -d your-domain.com --non-interactive --agree-tos --email you@example.com
```

Certbot will:
- Validate domain ownership via HTTP challenge
- Obtain and install the Let's Encrypt certificate
- Rewrite the nginx config: add `listen 443 ssl`, certificate paths, and HTTP→HTTPS redirect
- Enable auto-renewal (certbot.timer runs twice daily, renews certificates nearing expiry)

### Configure CORS and HSTS

Once HTTPS is working, set CORS origins and enable HSTS. Add these to `.env`:

```ini
WORKBENCH_API__CORS_ORIGINS=["https://your-domain.com"]
WORKBENCH_API__STRICT_TRANSPORT_SECURITY="max-age=31536000; includeSubDomains"
```

Then recreate the workbench container to apply:

```bash
docker compose --profile openwebui up -d --force-recreate workbench
```

Verify the headers:

```bash
curl -sI https://your-domain.com/ | grep -i strict-transport
# Expected: strict-transport-security: max-age=31536000; includeSubDomains

curl -sI -H 'Origin: https://your-domain.com' https://your-domain.com/api/v1/agents | grep access-control
# Expected: access-control-allow-origin: https://your-domain.com
```

---

## Bare-Metal Deployment

Use this for systems without Docker, or when you want to manage the database yourself.

### Step 1: Install System Dependencies

```bash
# Debian / Ubuntu
sudo apt install -y python3 python3-venv python3-pip git nginx

# RHEL / Fedora
sudo dnf install -y python3 python3-pip git nginx
```

### Step 2: Clone and Set Up the Application

```bash
git clone https://github.com/your-org/workbench.git /opt/workbench
cd /opt/workbench

python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[news,research,planning]"
```

### Step 3: Set Up the Database

**Option A: SQLite (simple, single-machine)**

No external database needed. The application defaults to `data/workbench.db` in the working directory.

```bash
workbench init-db
```

**Option B: PostgreSQL (recommended for production)**

Install and configure PostgreSQL 16 with the pgvector extension:

```bash
# Debian / Ubuntu
sudo apt install -y postgresql-16 postgresql-16-pgvector

# Create database and user
sudo -u postgres psql -c "CREATE USER workbench WITH PASSWORD '<strong-password>';"
sudo -u postgres psql -c "CREATE DATABASE workbench OWNER workbench;"
sudo -u postgres psql -d workbench -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

Then set the connection string and initialize:

```bash
export DATABASE_URL="postgresql+asyncpg://workbench:<strong-password>@localhost:5432/workbench"
workbench init-db
```

### Step 4: Generate an Encryption Key

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### Step 5: Set Environment Variables

```bash
export ENCRYPTION_KEY="<64-hex-char-key>"
# Optional:
export OPENROUTER_API_KEY="sk-or-v1-..."
```

### Step 6: Create an Admin User

```bash
workbench create-user admin
```

### Step 7: Start

```bash
workbench serve --host 127.0.0.1 --port 8420
```

### Step 8: Set Up nginx Reverse Proxy

Same nginx config as the Docker path (see [Step 5: Install nginx Reverse Proxy](#step-5-install-nginx-reverse-proxy) and [Reverse Proxy with TLS](#reverse-proxy-with-tls)).

### Step 9: Set Up systemd (Optional but Recommended)

Create `/etc/systemd/system/workbench.service`:

```ini
[Unit]
Description=Workbench AI Workbench
After=network.target postgresql.service
Wants=postgresql.service

[Service]
Type=simple
User=workbench
Group=workbench
WorkingDirectory=/opt/workbench
Environment="DATABASE_URL=postgresql+asyncpg://workbench:<password>@localhost:5432/workbench"
Environment="ENCRYPTION_KEY=<64-hex-key>"
Environment="OPENROUTER_API_KEY=sk-or-v1-..."
ExecStart=/opt/workbench/.venv/bin/workbench serve --host 127.0.0.1 --port 8420
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo useradd -r -s /bin/false -d /opt/workbench workbench
sudo chown -R workbench:workbench /opt/workbench

sudo systemctl daemon-reload
sudo systemctl enable --now workbench
sudo systemctl status workbench
```

---

## Health Checks

### Endpoint

```
GET /health
```

Response:
```json
{"status": "ok", "version": "0.1.0"}
```

Used by Docker Compose healthcheck, load balancers, and uptime monitors.

### Docker

```bash
# Check container health
docker compose ps

# Expected output for healthy containers:
# workbench-workbench-1   Up 2 minutes (healthy)
# workbench-db-1           Up 2 minutes (healthy)
# workbench-open-webui-1   Up 2 minutes (healthy)
```

### Via nginx

```bash
# Workbench health
curl http://localhost/health

# Open WebUI health
curl http://localhost/open-webui/health
```

### Monitoring Script

```bash
#!/bin/bash
# check_workbench.sh -- suitable for cron or monitoring tools

HEALTH=$(curl -s -o /dev/null -w "%{http_code}" http://localhost/health)
if [ "$HEALTH" != "200" ]; then
    echo "Workbench health check failed (HTTP $HEALTH)"
    exit 1
fi
echo "Workbench is healthy"
```

---

## Backup and Restore

### Docker Compose (PostgreSQL)

**Backup:**

```bash
# Dump the database
docker compose exec db pg_dump -U workbench workbench > workbench_backup_$(date +%Y%m%d).sql

# Also back up the data volume:
docker compose cp workbench:/app/data ./data_backup_$(date +%Y%m%d)
```

**Restore:**

```bash
# Stop the application container so no writes occur during restore
docker compose stop workbench

# Restore the dump
docker compose exec -T db psql -U workbench workbench < workbench_backup_YYYYMMDD.sql

docker compose start workbench
```

### Bare-Metal (SQLite)

**Backup:**

```bash
cp /opt/workbench/data/workbench.db /opt/workbench/data/workbench_backup_$(date +%Y%m%d).db
```

**Restore:**

```bash
systemctl stop workbench
cp /path/to/backup.db /opt/workbench/data/workbench.db
systemctl start workbench
```

### Bare-Metal (PostgreSQL)

**Backup:**

```bash
pg_dump -U workbench workbench > workbench_backup_$(date +%Y%m%d).sql
```

**Restore:**

```bash
systemctl stop workbench
psql -U workbench workbench < workbench_backup_YYYYMMDD.sql
systemctl start workbench
```

### Automated Backup (Cron)

Add to the workbench user's crontab:

```cron
# Daily backup at 03:00
0 3 * * * docker compose exec -T db pg_dump -U workbench workbench > /opt/backups/workbench_$(date +\%Y\%m\%d).sql
# Keep only last 14 days
0 4 * * * find /opt/backups -name "workbench_*.sql" -mtime +14 -delete
```

---

## Upgrading

### Docker Compose

```bash
# Pull latest code
git pull origin main

# Rebuild and restart
docker compose build workbench
docker compose --profile openwebui up -d

# Check logs for errors
docker compose logs -f workbench

# Verify
curl http://localhost/health
```

Database migrations run automatically on startup. No manual migration step needed.

### Upgrade Notes

* Always review `CHANGELOG.md` or git log for breaking changes before upgrading.
* Migrations are additive and idempotent. Running `init-db` on an already-migrated database is safe.
* The encryption key must remain the same across upgrades. **Changing `ENCRYPTION_KEY` after storing encrypted data will make existing keys unrecoverable.**
* When upgrading Open WebUI (`docker compose --profile openwebui pull open-webui`), re-test the `/open-webui/` sub-path proxying — the `sub_filter` rules may need adjusting for new asset paths.
* Test upgrades on a staging instance before production.

---

## Logging and Monitoring

### Docker

```bash
docker compose logs -f workbench           # All logs, tailing
docker compose logs --tail=100 workbench   # Last 100 lines
docker compose logs -f --since=10m workbench  # Last 10 minutes
```

### Bare-Metal (systemd)

```bash
journalctl -u workbench -f                  # Follow logs
journalctl -u workbench --since "1 hour ago"
journalctl -u workbench -n 200
```

### nginx

```bash
# Access logs
sudo tail -f /var/log/nginx/access.log

# Error logs
sudo tail -f /var/log/nginx/error.log
```

### Log Levels

Set via `WORKBENCH_GENERAL__LOG_LEVEL` or in `config/default.toml`:

| Level | When to Use |
|---|---|
| `DEBUG` | Development. Verbose agent output, every LLM call. |
| `INFO` | Production default. Startup, migrations, scheduler events. |
| `WARNING` | Quiet production. Only unexpected conditions. |
| `ERROR` | Minimal. Only failures. |

### Resource Monitoring

Check container resource usage:

```bash
docker stats workbench-workbench-1 workbench-db-1
```

Alert if the workbench container approaches its 1 GB memory limit (configurable in `docker-compose.yml` under `deploy.resources.limits`).

---

## Security Hardening Checklist

Complete these items before exposing Workbench to the internet.

- [ ] Use a randomly generated `ENCRYPTION_KEY` (64 hex characters, generated with `secrets.token_hex(32)`)
- [ ] Change PostgreSQL credentials from any defaults. Use a strong, unique password.
- [ ] Never expose the PostgreSQL port (5432) to the public internet. Docker Compose only exposes it internally.
- [ ] Both Workbench (8420) and Open WebUI (3000) bind to `127.0.0.1` only in `docker-compose.yml`. Verify with `curl --connect-timeout 3 http://<server-ip>:8420/health` (should return `000`).
- [ ] Run behind nginx as the single public entry point. Enable TLS via Let's Encrypt (`certbot --nginx`).
- [ ] Enable HSTS via `WORKBENCH_API__STRICT_TRANSPORT_SECURITY` once TLS is confirmed working.
- [ ] Set CORS origins explicitly: `WORKBENCH_API__CORS_ORIGINS=["https://your-domain.com"]`
- [ ] CSP header defaults to `frame-src 'self'` — Open WebUI is iframed from the same origin. Only add external origins if using an externally hosted Open WebUI instance.
- [ ] Consider setting `WORKBENCH_AUTH__ALLOW_REGISTRATION=false` after creating your initial users.
- [ ] Run the application as a non-root user (the Docker image runs as root by default in slim images; add a `USER` directive if needed).
- [ ] Restrict file permissions on `.env` and backup files: `chmod 600 .env`.
- [ ] Set up firewall rules to allow only 80 and 443 on the public interface. Internal ports 8420 and 3000 are unreachable anyway since they bind to `127.0.0.1`.
- [ ] Review rate limit settings for your expected traffic patterns.
- [ ] Keep the host system, Docker, and Python packages updated regularly.
- [ ] Back up the database before any upgrade.

---

## Troubleshooting

### Container fails with "ENCRYPTION_KEY is required"

You have not set `ENCRYPTION_KEY` in `.env`, or it is empty. Generate one with:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### Container fails with "POSTGRES_PASSWORD is required"

Same issue. The Docker Compose file uses `${VAR:?message}` syntax which refuses to start if the variable is unset or empty.

### Workbench starts but cannot connect to PostgreSQL

Check that PostgreSQL is healthy:

```bash
docker compose exec db pg_isready -U workbench
```

If it returns "no response", the database container may still be initializing. Wait 10-15 seconds and retry.

If you previously deployed with different credentials, old volume data might conflict. Destroy and recreate:

```bash
docker compose --profile openwebui down -v
docker compose --profile openwebui up -d
```

### nginx returns 502 Bad Gateway

One of the backend containers isn't running or listening:

```bash
docker compose ps                           # All should show "Up (healthy)"
curl http://127.0.0.1:8420/health            # Workbench
curl http://127.0.0.1:3000/health            # Open WebUI
```

Check nginx error log:

```bash
sudo tail -20 /var/log/nginx/error.log
```

### Open WebUI iframe is blank or shows 404

Check the nginx `sub_filter` rules are catching all asset paths:

```bash
# Check for un-rewritten paths in Open WebUI responses
curl -s http://localhost/open-webui/ | grep -oP '(src|href)="/(?!open-webui)[^"]*"'
```

If you see un-rewritten paths, add additional `sub_filter` directives. Common paths to watch: `/_app/`, `/api/`, `/ws/`, `/static/`, `/favicon`, `/opensearch`.

### Open WebUI works at root but breaks on page refreshes

This is a known limitation of the `sub_filter` approach — SvelteKit's client-side router uses absolute paths that are rewritten at the HTTP level, but JavaScript-initiated navigations may bypass the rewrite. Reload from the browser's URL bar or re-navigate from within the Open WebUI UI.

### OpenRouter API returns 401 or 403

* Verify your key starts with `sk-or-v1-` and is valid at [openrouter.ai/keys](https://openrouter.ai/keys).
* Re-save the key in the Workbench Settings panel.
* If using the server-wide fallback key (`OPENROUTER_API_KEY`), ensure the format is correct.
* Check that the encryption key used to store the key is the same one currently in use.

### News scheduler not running / no scheduled runs

* Ensure the news agent is toggled on in Settings.
* Check logs for scheduler messages: `docker compose logs workbench | grep -i scheduler`.
* Verify that at least one user has configured an interest with active feeds.
* The scheduler runs in `Europe/Berlin` timezone. Scheduled times are relative to that timezone.

### Web UI loads but agent tabs show nothing

* Ensure the agent is enabled in Settings (toggle per agent).
* Open the browser's developer console (F12) and check for JavaScript errors.
* Verify CORS settings if accessing from a different host.

### sub_filter causes "unexpected /" nginx config error

On some nginx versions (observed on Ubuntu 24.04 / nginx 1.24.0), the single-quoted `sub_filter` directives in the Open WebUI location block can cause `nginx -t` to fail with:

```
nginx: [emerg] unexpected "/" in /etc/nginx/sites-enabled/workbench:...
```

**Quick fix:** Remove the `sub_filter` block from the `/open-webui/` location entirely. The Open WebUI iframe will still load, though some static assets (CSS/JS/images) may not resolve correctly under the sub-path. The iframe approach works best when Open WebUI is served at a subdomain (the approach recommended by Open WebUI maintainers).

**Alternative:** Replace single-quoted `sub_filter` directives with double-quoted variants:
```nginx
sub_filter "href=/" "href=/open-webui/";
sub_filter "'/_app/" "'/open-webui/_app/";
```
Test with `sudo nginx -t` after making changes.

### Agent tabs not showing after first login

Workbench enables all agent tabs by default for new users. If no tabs appear:
* Verify the JavaScript console (F12) for errors — a missing `#welcome-screen` element crash indicates an outdated `router.js`.
* Ensure the `GET /api/v1/tabs` endpoint returns agents with `"enabled": true`.
* If you modified the default enabled state in code, restart the workbench container and create a fresh user.

### 413 Request Entity Too Large

Long texts (e.g., pasting large documents) may exceed the default request size limit. Add to the nginx server block:

```nginx
client_max_body_size 10m;
```

### Disk space growing unexpectedly

Check log volume and database growth:

```bash
du -sh logs/ data/
docker compose exec db psql -U workbench -c "SELECT pg_size_pretty(pg_database_size('workbench'));"
```

### Cannot create user with CLI while server is running

The `create-user` command and server can run concurrently since the CLI uses its own database connection pool. If you encounter locking issues, wait and retry.

### User already exists

```bash
docker compose exec workbench workbench create-user admin
# "User 'admin' already exists."
```

Use a different username, or connect to the database directly to check existing users:

```bash
docker compose exec db psql -U workbench -c "SELECT username, id FROM workbench_users;"
```

---

## Environment Variable Reference

All variables that can appear in `.env` or the environment.

### Required

| Variable | Example | Purpose |
|---|---|---|
| `POSTGRES_USER` | `workbench` | PostgreSQL user (Docker only) |
| `POSTGRES_PASSWORD` | (generated) | PostgreSQL password (Docker only) |
| `POSTGRES_DB` | `workbench` | PostgreSQL database name (Docker only) |
| `ENCRYPTION_KEY` | `a1b2...64 chars total` | AES-256-GCM key for at-rest encryption |

### Optional — Server Configuration

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://...` or `data/workbench.db` | Full database connection string. If unset, SQLite is used. |
| `OPENROUTER_API_KEY` | (none) | Server-wide fallback OpenRouter API key |
| `WORKBENCH_GENERAL__LOG_LEVEL` | `INFO` | Logging level: DEBUG, INFO, WARNING, ERROR |
| `WORKBENCH_GENERAL__DATA_DIR` | `data` | Directory for data files |

### Optional — Network

| Variable | Default | Purpose |
|---|---|---|
| `WORKBENCH_API__HOST` | `127.0.0.1` | Bind address |
| `WORKBENCH_API__PORT` | `8420` | Listen port |
| `WORKBENCH_API__CORS_ORIGINS` | `["http://localhost:8420"]` | Allowed CORS origins (JSON array) |
| `WORKBENCH_API__CSP_HEADER` | (restrictive default with `frame-src 'self'`) | Content-Security-Policy header value |
| `WORKBENCH_API__STRICT_TRANSPORT_SECURITY` | (empty) | HSTS header value (e.g. `max-age=31536000`) |

### Optional — OpenRouter

| Variable | Default | Purpose |
|---|---|---|
| `WORKBENCH_OPENROUTER__BASE_URL` | `https://openrouter.ai/api/v1` | OpenRouter API endpoint |
| `WORKBENCH_OPENROUTER__DEFAULT_MODEL` | `deepseek/deepseek-v4-pro` | Default model for new agent runs |
| `WORKBENCH_OPENROUTER__TIMEOUT_SECONDS` | `120` | HTTP timeout for LLM calls |
| `WORKBENCH_OPENROUTER__MAX_RETRIES` | `2` | Retries on transient failures |

### Optional — Authentication

| Variable | Default | Purpose |
|---|---|---|
| `WORKBENCH_AUTH__API_KEY_PREFIX` | `wb` | Prefix for generated API keys |
| `WORKBENCH_AUTH__MAX_KEYS_PER_USER` | `5` | Maximum API keys per user account |
| `WORKBENCH_AUTH__ALLOW_REGISTRATION` | `true` | Allow new user registration via the API |
| `WORKBENCH_AUTH__SESSION_EXPIRY_HOURS` | `24` | Session cookie lifetime |

### Optional — Rate Limiting

| Variable | Default | Purpose |
|---|---|---|
| `WORKBENCH_RATE_LIMIT__ENABLED` | `true` | Enable/disable rate limiting |
| `WORKBENCH_RATE_LIMIT__AUTH` | `5/minute` | Rate limit for auth endpoints |
| `WORKBENCH_RATE_LIMIT__AGENTS` | `60/minute` | Rate limit for agent endpoints |
| `WORKBENCH_RATE_LIMIT__GENERAL` | `120/minute` | Rate limit for all other endpoints |

### Optional — Encryption

| Variable | Default | Purpose |
|---|---|---|
| `WORKBENCH_ENCRYPTION__ENCRYPT_REPORTS` | `false` | Also encrypt stored research reports at rest |
