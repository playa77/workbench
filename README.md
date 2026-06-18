# Workbench

**Self-hosted BYOK AI Workbench** -- one dashboard, eight LLM-powered agents plus Open WebUI, zero telemetry.

Run locally or deploy to a VPS with full HTTPS (Let's Encrypt + nginx). Bring your own OpenRouter key. Every agent lives in its own browser tab.

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688)](https://fastapi.tiangolo.com)

---

## What You Can Do

| Agent | Tab | Capability |
|---|---|---|
| **Chat** | Chat | Plain LLM conversation with any OpenRouter model. No setup required beyond pasting your key. |
| **News Pipeline** | News | RSS feed monitoring with AI theme extraction, scheduled background runs, and email delivery. Configure interests, the pipeline fetches, scrapes, analyzes, and delivers. |
| **Debate Arena** | Debate | Structured multi-agent debates with 12 persona roles. Use Director Mode to inject interventions, pause/resume debates, and observe how perspectives clash. |
| **Deep Research** | Research | Autonomous web research driven by function-calling. Multiple search iterations, source gathering, contradiction detection, and a single cited report at the end. |
| **Deliberation** | Deliberation | Multi-frame reasoning with 8 analysis frames (Pro/Con, SWOT, Stakeholder, Forces...). Pairwise critique, rhetoric analysis, disagreement surface mapping, and a final synthesis. |
| **Strategic Planning** | Planning | Generates any of 9 plan types: project plans, SWOT analyses, WBS, schedules, root cause analyses, pitch decks, governance frameworks, team compositions, or executive summaries. |
| **Math Tutor** | Math | Step-by-step problem solving with LaTeX rendering. Explains reasoning, not just answers. |
| **Knowledge Base** | Knowledge | Create document collections, upload files, and query them with RAG-style retrieval. |
| **History** | History | Unified searchable list of all past agent sessions. Filter by agent type, view full state, export as PDF. |
| **Open WebUI** | Open WebUI | Full chat-first LLM interface with model management, RAG, and multimodality. Runs alongside the agent tabs in its own iframe, proxied through nginx. |

---

## How It Works

1. You launch Workbench locally (Docker or bare-metal).
2. You register a username and save the generated API key.
3. You paste your OpenRouter key in Settings. It is encrypted at rest with AES-256-GCM on your machine.
4. Each agent tab is a self-contained tool backed by an LLM agent. The backend is a FastAPI server; the frontend is vanilla JavaScript with zero build step.
5. **Every LLM call** flows through `OpenRouterClient` -- a single, auditable code path. No other external APIs are called.

---

## Quick Start

### Prerequisites

* Python 3.11 or later
* An [OpenRouter](https://openrouter.ai) API key (free signup, pay-per-token)

### Install

```bash
git clone https://github.com/your-org/workbench.git
cd workbench

python -m venv .venv
source .venv/bin/activate

# Core install (all agent runtimes)
pip install -e ".[news,research,planning]"
```

> On modern Linux (Ubuntu 23.04+, Debian 12+) pip enforces PEP 668. Use a virtual environment. Never `--break-system-packages`.

### Run

```bash
workbench init-db
workbench serve
```

Open **http://localhost:8420**.

### First Login

1. The registration form appears if no user exists yet. Pick a username.
2. The API key is shown **once** -- copy it. It is your Bearer token for all API access and the web UI login.
3. Enter it on the login screen. You are in.
4. Open **Settings** (gear icon), paste your OpenRouter key (`sk-or-v1-...`), and click **Save**.
5. Toggle agents on/off. Click any tab to start.

### CLI Commands

```
workbench serve                         Start the server (default 127.0.0.1:8420)
workbench serve --port 9000             Use a different port
workbench serve --host 0.0.0.0          Listen on all interfaces
workbench init-db                       Run Alembic migrations
workbench create-user <username>        Create a new user and generate an API key
workbench version                       Print version
```

---

## Docker

```bash
cp .env.example .env
# Fill in POSTGRES_PASSWORD and ENCRYPTION_KEY
docker compose --profile openwebui up -d

# Create the default admin user
docker compose exec workbench workbench create-user --username admin --email admin@workbench.local --password admin123 --admin
```

Default login credentials: **admin** / **admin123**. Change the password after first login.

This starts PostgreSQL 16 (pgvector), Workbench on port 8420, and Open WebUI on port 3000. All bind to `127.0.0.1` only. The workbench service uses `restart: unless-stopped` so containers auto-restart on crash.

The Docker image includes the **tectonic** LaTeX engine (v0.15.0) for PDF export. No additional system packages are needed.

For production deployment -- nginx reverse proxy, Let's Encrypt TLS, CORS, HSTS -- see [DEPLOYMENT.md](DEPLOYMENT.md).

---

## Configuration

Workbench loads config in this priority order (lowest to highest):

1. `config/default.toml` -- shipped defaults
2. `.env` -- environment file variables
3. `WORKBENCH_*` -- environment variable overrides (use `__` for nesting: `WORKBENCH_API__PORT=9000`)

### Key Environment Variables

| Variable | Purpose | Required |
|---|---|---|
| `DATABASE_URL` | Database connection string (defaults to SQLite at `data/workbench.db`) | For Postgres |
| `ENCRYPTION_KEY` | 64 hex chars for AES-256-GCM at-rest encryption | Yes |
| `OPENROUTER_API_KEY` | Server-wide fallback OpenRouter key | No |
| `WORKBENCH_API__HOST` | Bind address (default `127.0.0.1`) | No |
| `WORKBENCH_API__PORT` | Listen port (default `8420`) | No |
| `WORKBENCH_API__CORS_ORIGINS` | JSON array of allowed origins (e.g. `["https://your-domain.com"]`) | For remote access |
| `WORKBENCH_API__STRICT_TRANSPORT_SECURITY` | HSTS header value (e.g. `max-age=31536000`) | For HTTPS deploy |

### Generate an Encryption Key

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### Full Config Reference

All settings in `config/default.toml` can be overridden via environment variables. See the file for every option.

---

## Agent Architecture

Every agent follows the same structure:

```
agents/{name}/agent.py          ->   FastAPI router with endpoints
services/{name}_service.py      ->   Pure business logic (SSE, state machines)
shared/llm/router.py            ->   Single LLM call path (OpenRouterClient)
```

Rules enforced across all agents:
1. All LLM calls go through `OpenRouterClient` -- no other code path exists.
2. All database models inherit from `workbench.shared.db.base.Base`.
3. All config uses `workbench.shared.config.loader` (deep_merge, read_env).
4. Every agent subclasses `AgentBase` and registers via `_BUILTIN_AGENTS` in `app.py`.
5. Every frontend tab is a lazy-loaded vanilla JS component in `webui/static/js/components/`.

### Adding a New Agent

1. Create `agents/{name}/agent.py` -- subclass `AgentBase`, set `name`, `display_name`, `description`, `version`, `icon`.
2. Implement `_build_router()` returning a FastAPI `APIRouter`.
3. Implement `get_frontend_tab()` returning tab metadata.
4. Register in `_BUILTIN_AGENTS` in `src/workbench/api/app.py`.
5. Create `webui/static/js/components/{name}-tab.js` using `Router.register(name, renderFn)`.

### SSE Streaming

Long-running agents (Research, Deliberation, Planning) stream progress via Server-Sent Events. The pattern: `asyncio.Queue` + `async generator` + `StreamingResponse(text/event-stream)` on the backend; `ReadableStream` on the frontend. All support stop via `POST /{id}/stop`.

---

## Frontend

The web UI is a vanilla JavaScript SPA at `src/workbench/webui/static/`. No framework, no build step.

| File | Role |
|---|---|
| `api.js` | Centralized HTTP client (Bearer token auth, JSON + SSE) |
| `app.js` | Boot sequence, auth flow, settings, agent list, tab rendering |
| `router.js` | Tab router with lazy script loading |
| `theme.js` | Light/dark toggle, persisted to localStorage |
| `utils.js` | HTML escaping and helpers |
| `css/base.css` | Layout, cards, buttons, forms, toggles |
| `css/theme-light.css` / `css/theme-dark.css` | CSS custom property theme variants |
| `components/chat-tab.js` | Chat agent UI |
| `components/news-tab.js` | News pipeline: interests CRUD, runs, status |
| `components/debate-tab.js` | Debate arena: polling, Director Mode, pause/resume |
| `components/research-tab.js` | SSE streaming research with live progress |
| `components/deliberation-tab.js` | Frame selection, SSE phase tracking |
| `components/planning-tab.js` | 9 plan types, SSE generation |
| `components/math-tutor-tab.js` | Math tutor with LaTeX equation builder |
| `components/knowledge-tab.js` | Knowledge base management: collections, uploads, queries |
| `components/history-tab.js` | Unified agent session history with filter, view, PDF export |
| `components/owui-tab.js` | Open WebUI health check + iframe |

---

## Development

```bash
pip install -e ".[dev]"
```

### Commands

```bash
pytest tests/ -v              # 46 tests, SQLite in-memory -- no external DB needed
ruff check src/workbench/ agents/    # Lint
mypy src/ agents/                   # Type check
```

### Lint Exceptions

* **B008** -- FastAPI's `Depends()` in function signatures is by-design, not a bug.
* **E501** -- some long string literals and template strings exceed 100 characters intentionally.

---

## Project Structure

```
workbench/
├── agents/                          # Agent implementations (one per directory)
│   ├── base.py                      # AgentBase -- shared ABC
│   ├── chat/    debate/    deliberation/    knowledge/
│   ├── math_tutor/    news/    planning/    research/
│
├── src/workbench/                   # Core infrastructure
│   ├── main.py                      # CLI entry point
│   ├── api/                         # FastAPI app, routes, dependency injection
│   │   └── routes/sessions.py       # Agent session history API
│   ├── core/                        # Config, DB, auth, models, encryption, agent registry
│   ├── shared/                      # Canonical shared primitives (LLM router, config loader, DB session)
│   ├── services/                    # Domain logic (debate engine, news pipeline, research orchestrator, etc.)
│   └── webui/static/                # Vanilla JS SPA frontend
│       ├── css/base.css             # Layout, cards, buttons, forms, toggles
│       ├── css/theme-light.css      # Light theme
│       ├── css/theme-dark.css       # Dark theme
│       ├── js/api.js                # HTTP + SSE client
│       ├── js/app.js                # Boot, auth, settings, tabs
│       ├── js/router.js             # Lazy tab loading
│       ├── js/theme.js              # Light/dark toggle
│       ├── js/utils.js              # Helpers
│       └── js/components/
│           ├── chat-tab.js          # Chat UI
│           ├── debate-tab.js        # Debate arena
│           ├── deliberation-tab.js  # Deliberation UI
│           ├── history-tab.js      # Unified agent session history
│           ├── knowledge-tab.js     # Knowledge base management
│           ├── math-tutor-tab.js    # Math tutor with LaTeX rendering
│           ├── news-tab.js          # News pipeline
│           ├── owui-tab.js          # Open WebUI iframe
│           ├── planning-tab.js      # Planning UI
│           └── research-tab.js      # Research UI
│
├── config/default.toml              # Default configuration
├── alembic/                         # Database migrations (9 versions)
├── tests/                           # pytest suite (46 tests)
├── docker-compose.yml               # Docker deployment (PG + Workbench + Open WebUI)
├── Dockerfile                       # python:3.12-slim, news+research extras
├── pyproject.toml                   # Build, dependencies, tool configs
└── DEPLOYMENT.md                    # Production deployment guide
```

---

## Troubleshooting

**"ENCRYPTION_KEY is required" in Docker logs**
Generate one: `python -c "import secrets; print(secrets.token_hex(32))"` and add it to `.env`.

**OpenRouter API returns 401**
Verify your key starts with `sk-or-v1-`. Check it in Settings. Re-save if needed.

**Database connection refused (Docker)**
Wait for PostgreSQL health check to pass. The workbench container waits for `pg_isready` before starting.

**Agent tab shows nothing**
Check that the agent is toggled on in Settings. Each agent only activates when enabled.

**Rate limited (429)**
Default limits are 5/min for auth, 60/min for agents, 120/min general. Adjust via `config/default.toml` or environment variables.

**PDF export fails or "tectonic command not found"**
On bare-metal, the tectonic LaTeX engine is not installed by pip. Install it manually — see the Troubleshooting section of [DEPLOYMENT.md](DEPLOYMENT.md) for instructions. If compilation fails after installing tectonic, pre-warm the package cache by running `tectonic -X compile` on a sample `.tex` file once (requires internet on first run; packages are cached at `~/.cache/Tectonic/`).

**PDF template compilation errors**
Tectonic auto-fetches LaTeX packages from CTAN. If a template fails, ensure
your server has internet access on first compilation (packages are cached after).
If you're behind a firewall, pre-warm the cache by running `tectonic -X compile`
on a sample `.tex` file once. To compile PDFs offline, ensure the tectonic user
cache at `~/.cache/Tectonic/` is populated.

**The server won't start on port 8420**
The port is already in use. Change it: `workbench serve --port 9000`.

---

## PDF Templates

Workbench ships with six professional LaTeX templates for PDF export, selectable per-export:

| Template | Key | Style |
|---|---|---|
| **Professional** | `professional` | Default — clean single-column, Linux Libertine fonts, TOC, accent color, professional layout |
| **Tufte** | `tufte` | Tufte-inspired elegance with wide margins, small caps, and generous whitespace |
| **Classic** | `classic` | Thesis-style with chapter openings, Bringhurst proportions, and elegant running headers |
| **Modern** | `modern` | Sans-serif, color-accented, clean institutional feel (McKinsey/Deutsche Bank style) |
| **Compact** | `compact` | Two-column dense technical layout for maximum information density |
| **Manuscript** | `manuscript` | Kaobook-inspired with wide outer margins and luxurious typography |

Templates are compiled via tectonic (XeTeX engine, auto-fetches LaTeX packages from CTAN).
They can be selected from the dropdown next to the Export PDF button in Research, Planning,
and History tabs.

### Fonts

All templates ship with [Linux Libertine](https://libertine-fonts.org/) (serif),
[Linux Biolinum](https://libertine-fonts.org/) (sans-serif), and
[Inconsolata](https://levien.com/type/myfonts/inconsolata.html) (monospace) for
consistent, high-quality typography across platforms. These are installed automatically
in the Docker image.

---

## Security

* **HTTPS enforced** in production via Let's Encrypt + nginx reverse proxy with HSTS and automatic certificate renewal.
* OpenRouter keys are encrypted at rest with AES-256-GCM (key derived from `ENCRYPTION_KEY`).
* API keys and session tokens are bcrypt-hashed. Sessions are httponly, samesite=strict cookies with 24-hour expiry.
* Rate limiting on all endpoints (configurable per category).
* Anti-SSRF validation on outbound URLs (blocks private/internal IP ranges).
* Content-Security-Policy and CORS headers configured by default.
* No telemetry, no analytics, no phoning home.

For production hardening, see the security checklist in [DEPLOYMENT.md](DEPLOYMENT.md).

---

## License

MIT -- see [LICENSE](LICENSE).
