# Workbench -- Deployment Guide

This document covers production deployment of Workbench. For local development setup, see [README.md](README.md).

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Deployment Paths](#deployment-paths)
   - [Docker Compose (Recommended)](#docker-compose-recommended)
   - [Bare-Metal](#bare-metal)
3. [Reverse Proxy with TLS](#reverse-proxy-with-tls)
4. [Open WebUI Integration](#open-webui-integration)
5. [Health Checks](#health-checks)
6. [Backup and Restore](#backup-and-restore)
7. [Upgrading](#upgrading)
8. [Logging and Monitoring](#logging-and-monitoring)
9. [Security Hardening Checklist](#security-hardening-checklist)
10. [Troubleshooting](#troubleshooting)
11. [Environment Variable Reference](#environment-variable-reference)

---

## Prerequisites

### Required

* **OpenRouter API key** -- [sign up](https://openrouter.ai) (free, pay-per-token). Key format: `sk-or-v1-...`
* **A machine** running Linux (amd64/arm64). Minimum: 1 CPU, 1 GB RAM, 2 GB disk. Recommended: 2 CPUs, 2 GB RAM, 10 GB disk.
* **Docker and Docker Compose** (v2+) for the Docker path, or **Python 3.11+** for bare-metal.

### Supported Databases

| Environment | Database | Driver |
|---|---|---|
| Production (Docker) | PostgreSQL 16 + pgvector | asyncpg |
| Production (bare-metal) | PostgreSQL 14+ or SQLite | asyncpg / aiosqlite |
| Development / Testing | SQLite (in-memory or file) | aiosqlite |

---

## Deployment Paths

### Docker Compose (Recommended)

This is the simplest path. Two containers: PostgreSQL 16 (pgvector) and the Workbench application.

#### Step 1: Clone and Prepare

```bash
git clone https://github.com/your-org/workbench.git
cd workbench
```

#### Step 2: Create the Environment File

```bash
cp .env.example .env
```

#### Step 3: Generate Secrets

```bash
# Generate a 64-hex-char AES encryption key
python3 -c "import secrets; print(secrets.token_hex(32))"
```

```bash
# Generate a strong PostgreSQL password
python3 -c "import secrets; print(secrets.token_urlsafe(24))"
```

#### Step 4: Edit `.env`

Fill in these mandatory values:

```ini
POSTGRES_USER=workbench
POSTGRES_PASSWORD=<your-generated-password>
POSTGRES_DB=workbench
ENCRYPTION_KEY=<64-hex-char-key>
# Optional: server-wide OpenRouter fallback key
OPENROUTER_API_KEY=sk-or-v1-...
```

**All four values are mandatory.** Docker Compose will fail with an error if any required variable is missing or empty.

#### Step 5: Start

```bash
docker compose up -d
```

Wait ~10 seconds for PostgreSQL to become healthy, then Workbench starts.

#### Step 6: Verify

```bash
curl http://localhost:8420/health
# Expected: {"status":"ok"}
```

#### Step 7: Create Initial User

```bash
docker compose exec workbench workbench create-user admin
# Saves the API key output -- it is shown only once.
```

#### Step 8: Access

Open `http://<your-server>:8420` in a browser. Log in with the API key from step 7.

#### Service Management

```bash
docker compose ps                     # Show container status
docker compose logs -f workbench      # Follow Workbench logs
docker compose logs -f db             # Follow database logs
docker compose restart workbench      # Restart after config changes
docker compose down                   # Stop and remove containers
docker compose down -v                # Also delete volumes (destroys database!)
```

---

### Bare-Metal

Use this for systems without Docker, or when you want to manage the database yourself.

#### Step 1: Install System Dependencies

```bash
# Debian / Ubuntu
sudo apt install -y python3 python3-venv python3-pip git

# RHEL / Fedora
sudo dnf install -y python3 python3-pip git
```

#### Step 2: Clone and Set Up the Application

```bash
git clone https://github.com/your-org/workbench.git /opt/workbench
cd /opt/workbench

python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[news,research,planning]"
```

#### Step 3: Set Up the Database

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

#### Step 4: Generate an Encryption Key

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

#### Step 5: Set Environment Variables

```bash
export ENCRYPTION_KEY="<64-hex-char-key>"
# Optional:
export OPENROUTER_API_KEY="sk-or-v1-..."
```

#### Step 6: Create an Admin User

```bash
workbench create-user admin
```

#### Step 7: Start

```bash
workbench serve --host 127.0.0.1 --port 8420
```

#### Step 8: Set Up systemd (Optional but Recommended)

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

## Reverse Proxy with TLS

For public access, place Workbench behind a reverse proxy with HTTPS.

### nginx

Install nginx and certbot:

```bash
sudo apt install -y nginx certbot python3-certbot-nginx
```

Create `/etc/nginx/sites-available/workbench`:

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        return 301 https://$host$request_uri;
    }
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate     /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    # SSE endpoints need unbuffered proxying
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
}
```

Enable and get certificates:

```bash
sudo ln -s /etc/nginx/sites-available/workbench /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx

sudo certbot --nginx -d your-domain.com
```

### CORS Configuration

If your frontend domain differs from the API domain, set CORS origins:

```bash
# In .env (Docker) or environment (bare-metal):
WORKBENCH_API__CORS_ORIGINS=["https://your-domain.com"]
```

### HSTS

To enable HSTS, set in `.env` or environment:

```bash
WORKBENCH_API__STRICT_TRANSPORT_SECURITY="max-age=31536000; includeSubDomains"
```

---

## Open WebUI Integration

Workbench includes an optional Open WebUI container that embeds via iframe in a dedicated tab.

### Start with Open WebUI

```bash
docker compose --profile openwebui up -d
```

This adds a container on port 3000. The Open WebUI tab auto-detects it at `http://localhost:3000`.

### Custom Open WebUI URL

You can point the tab to any Open WebUI instance (local, remote, or cloud-hosted). Configure this in the agent settings endpoint, or modify the frame-src CSP directive if your Open WebUI is on a different host:

```bash
WORKBENCH_API__CSP_HEADER="default-src 'self'; ...; frame-src 'self' http://localhost:3000 https://your-openwebui-host.com"
```

---

## Health Checks

### Endpoint

```
GET /health
```

Response:
```json
{"status": "ok"}
```

Used by Docker Compose healthcheck, load balancers, and uptime monitors.

### Docker

```bash
# Check container health
docker compose ps

# Expected output for healthy containers:
# workbench   Up (healthy)
# db          Up (healthy)
```

### Monitoring Script

```bash
#!/bin/bash
# check_workbench.sh -- suitable for cron or monitoring tools

HEALTH=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8420/health)
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

# Also back up the data volume in case of SQLite usage within the container:
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
docker compose up -d

# Check logs for errors
docker compose logs -f workbench

# Verify
curl http://localhost:8420/health
```

Database migrations run automatically on startup. No manual migration step needed.

### Bare-Metal

```bash
cd /opt/workbench
git pull origin main

source .venv/bin/activate
pip install -e ".[news,research,planning]"

# Run migrations
workbench init-db

# Restart
sudo systemctl restart workbench
sudo systemctl status workbench
```

### Upgrade Notes

* Always review `CHANGELOG.md` or git log for breaking changes before upgrading.
* Migrations are additive and idempotent. Running `init-db` on an already-migrated database is safe.
* The encryption key must remain the same across upgrades. **Changing `ENCRYPTION_KEY` after storing encrypted data will make existing keys unrecoverable.**
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
- [ ] Never expose the PostgreSQL port (5432) to the public internet. Docker Compose already only exposes internally.
- [ ] Run behind a reverse proxy (nginx/Caddy) with TLS. Use Let's Encrypt for free certificates.
- [ ] Enable HSTS via `WORKBENCH_API__STRICT_TRANSPORT_SECURITY` once TLS is confirmed working.
- [ ] Set CORS origins explicitly: `WORKBENCH_API__CORS_ORIGINS=["https://your-domain.com"]`
- [ ] Set CSP header for your production domain: `WORKBENCH_API__CSP_HEADER=...` -- include your Open WebUI host in `frame-src` if using that feature.
- [ ] Consider setting `WORKBENCH_AUTH__ALLOW_REGISTRATION=false` after creating your initial users.
- [ ] Run the application as a non-root user (the Docker image runs as root by default in slim images; add a `USER` directive if needed).
- [ ] Restrict file permissions on `.env` and backup files: `chmod 600 .env`.
- [ ] Set up firewall rules to allow only 443 (and 80 for ACME) on the public interface. Block 8420 and 5432 from all but localhost.
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

### 413 Request Entity Too Large

Long texts (e.g., pasting large documents) may exceed the default request size limit. Increase it by running behind nginx with `client_max_body_size 10m;`.

### Disk space growing unexpectedly

Check log volume and database growth:

```bash
du -sh logs/ data/pgdata/
docker compose exec db psql -U workbench -c "SELECT pg_size_pretty(pg_database_size('workbench'));"
```

### Cannot create user with CLI while server is running

The `create-user` command and server can run concurrently since the CLI uses its own database connection pool. If you encounter locking issues, wait and retry.

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

### Optional -- Server Configuration

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://...` or `data/workbench.db` | Full database connection string. If unset, SQLite is used. |
| `OPENROUTER_API_KEY` | (none) | Server-wide fallback OpenRouter API key |
| `WORKBENCH_GENERAL__LOG_LEVEL` | `INFO` | Logging level: DEBUG, INFO, WARNING, ERROR |
| `WORKBENCH_GENERAL__DATA_DIR` | `data` | Directory for data files |

### Optional -- Network

| Variable | Default | Purpose |
|---|---|---|
| `WORKBENCH_API__HOST` | `127.0.0.1` | Bind address |
| `WORKBENCH_API__PORT` | `8420` | Listen port |
| `WORKBENCH_API__CORS_ORIGINS` | `["http://localhost:8420","http://localhost:3000"]` | Allowed CORS origins (JSON array) |
| `WORKBENCH_API__CSP_HEADER` | (restrictive default) | Content-Security-Policy header value |
| `WORKBENCH_API__STRICT_TRANSPORT_SECURITY` | (empty) | HSTS header value (e.g. `max-age=31536000`) |

### Optional -- OpenRouter

| Variable | Default | Purpose |
|---|---|---|
| `WORKBENCH_OPENROUTER__BASE_URL` | `https://openrouter.ai/api/v1` | OpenRouter API endpoint |
| `WORKBENCH_OPENROUTER__DEFAULT_MODEL` | `deepseek/deepseek-v4-pro` | Default model for new agent runs |
| `WORKBENCH_OPENROUTER__TIMEOUT_SECONDS` | `120` | HTTP timeout for LLM calls |
| `WORKBENCH_OPENROUTER__MAX_RETRIES` | `2` | Retries on transient failures |

### Optional -- Authentication

| Variable | Default | Purpose |
|---|---|---|
| `WORKBENCH_AUTH__API_KEY_PREFIX` | `wb` | Prefix for generated API keys |
| `WORKBENCH_AUTH__MAX_KEYS_PER_USER` | `5` | Maximum API keys per user account |
| `WORKBENCH_AUTH__ALLOW_REGISTRATION` | `true` | Allow new user registration via the API |
| `WORKBENCH_AUTH__SESSION_EXPIRY_HOURS` | `24` | Session cookie lifetime |

### Optional -- Rate Limiting

| Variable | Default | Purpose |
|---|---|---|
| `WORKBENCH_RATE_LIMIT__ENABLED` | `true` | Enable/disable rate limiting |
| `WORKBENCH_RATE_LIMIT__AUTH` | `5/minute` | Rate limit for auth endpoints |
| `WORKBENCH_RATE_LIMIT__AGENTS` | `60/minute` | Rate limit for agent endpoints |
| `WORKBENCH_RATE_LIMIT__GENERAL` | `120/minute` | Rate limit for all other endpoints |

### Optional -- Encryption

| Variable | Default | Purpose |
|---|---|---|
| `WORKBENCH_ENCRYPTION__ENCRYPT_REPORTS` | `false` | Also encrypt stored research reports at rest |

---

## Firewall Rules (iptables/nftables)

Example rules for a public-facing server using iptables:

```bash
# Allow SSH, HTTP, HTTPS
iptables -A INPUT -p tcp --dport 22 -j ACCEPT
iptables -A INPUT -p tcp --dport 80 -j ACCEPT
iptables -A INPUT -p tcp --dport 443 -j ACCEPT

# Block direct access to Workbench and PostgreSQL from outside
iptables -A INPUT -p tcp --dport 8420 -s 127.0.0.1 -j ACCEPT
iptables -A INPUT -p tcp --dport 8420 -j DROP
iptables -A INPUT -p tcp --dport 5432 -j DROP

# Allow established connections
iptables -A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT

# Default deny
iptables -P INPUT DROP
iptables -P FORWARD DROP
iptables -P OUTPUT ACCEPT
```

Save with `iptables-save > /etc/iptables/rules.v4` (Debian/Ubuntu) or your distribution's equivalent.
