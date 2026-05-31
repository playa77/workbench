# Workbench

**Unified BYOK AI Workbench** — agent-driven infrastructure for LLM-powered tools.

Bring your own OpenRouter key. Run locally. No telemetry. One server, six agents, one web UI.

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688)](https://fastapi.tiangolo.com)

---

## What It Does

Workbench gives you a local, self-hosted web dashboard where each AI capability lives in its own browser tab. You supply your OpenRouter API key (encrypted at rest, never shared), and the agents do the rest.

**Six agents, one interface:**

| Tab | Agent | What You Get |
|-----|-------|--------------|
| Chat | Chat | LLM chat with any OpenRouter model — plain conversation, no setup |
| News Pipeline | News | RSS feed monitoring with AI theme extraction, multi-format briefs, scheduled runs, email delivery |
| Debate Arena | Debate | Multi-agent debates with 12 persona roles, Director Mode for injecting interventions, pause/resume |
| Deep Research | Research | Autonomous web research — multi-iteration search, source gathering, contradiction detection, cited reports |
| Deliberation | Deliberation | Multi-frame reasoning with 8 analysis frames (Pro/Con, SWOT, Stakeholder, Forces...), pair-wise critique, rhetoric analysis, disagreement surface mapping, synthesis |
| Strategic Planning | Planning | 9 plan types — project plans, SWOT, WBS, schedules, RCA, pitch decks, governance frameworks, team compositions, executive summaries |

Plus a **seventh tab** for **Open WebUI** — an iframe embed that connects to a local/remote Open WebUI instance (launched separately via the Electron desktop wrapper or Docker).

---

## BYOK — Bring Your Own Key

- You supply an **OpenRouter API key** in Settings (stored encrypted with AES-256-GCM).
- Every API call flows through `workbench.shared.llm.router.OpenRouterClient` — there is no other LLM path.
- 250+ models supported: DeepSeek V3, Claude 4, GPT-4o, Gemini 2.5, Llama 4, and more.
- OpenRouter acts as a unified frontend — you get one key to many providers.
- Workbench makes zero external calls except to OpenRouter on your behalf.

---

## Quick Start

### Prerequisites

- Python 3.11 or later
- An [OpenRouter](https://openrouter.ai) API key (free signup, pay-per-token)

### Install

```bash
git clone https://github.com/your-org/workbench.git
cd workbench

# Core install
pip install -e . --break-system-packages

# Run-time dependencies for specific agents
pip install feedparser trafilatura --break-system-packages

# Or install everything at once
pip install -e ".[news,research,planning]" --break-system-packages
```

> On macOS/Linux outside containers, omit `--break-system-packages` or use a virtual environment.

### Run

```bash
# Initialize the database (runs Alembic migrations)
workbench init-db

# Start the server
workbench serve
```

Open **http://localhost:8420** in your browser.

1. Register a username (creates an account and gives you an API key — save it).
2. Go to **Settings**, paste your OpenRouter key (`sk-or-v1-...`), and click Save.
3. Toggle agents on/off in the Settings panel.
4. Click any agent tab to start using it.

### CLI Reference

```
workbench serve       Start the API server (default: 0.0.0.0:8420)
workbench serve --port 9000   Bind to a different port
workbench init-db     Create/migrate database schema
workbench version     Print version and exit
```

---

## Docker

```bash
docker compose up -d
```

Starts:
- **PostgreSQL 16** with pgvector (port 5432)
- **Workbench** on port 8420
- **Open WebUI** on port 3000 (disabled by default — add `--profile openwebui`)

```bash
# With Open WebUI
docker compose --profile openwebui up -d
```

---

## Configuration

Workbench loads configuration from three sources in priority order:

| Priority | Source | Example |
|----------|--------|---------|
| Lowest | `config/default.toml` | `api.port = 8420` |
| Medium | `.env` file | `DATABASE_URL=...` |
| Highest | `WORKBENCH_*` env vars | `WORKBENCH_API__PORT=9000` |

### Environment Variables

```bash
# Database (defaults to SQLite at data/workbench.db)
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/workbench

# Encryption key for at-rest secrets (generate with: python -c "import secrets; print(secrets.token_hex(32))")
ENCRYPTION_KEY=your-64-char-hex-key

# Optional server-wide OpenRouter fallback key
OPENROUTER_API_KEY=sk-or-v1-...

# Bind address and port (override via CLI or env)
WORKBENCH_API__HOST=0.0.0.0
WORKBENCH_API__PORT=8420
```

---

## Agent Architecture

Every agent follows the same pattern:

```
Agent (agents/{name}/agent.py)    Service (src/workbench/services/{name}_service.py)
┌─────────────────────────────┐    ┌──────────────────────────────────────┐
│ name, display_name, icon     │    │ Pure business logic                   │
│ _build_router() → endpoints  │────│ Called by agent endpoints             │
│ get_frontend_tab() → tab     │    │ SSE event generation                  │
└─────────────────────────────┘    └──────────────────────────────────────┘
              │                                      │
              ▼                                      ▼
     OpenRouterClient (shared LLM router)     Pydantic v2 models
```

**Rules:**
1. All LLM calls go through `workbench.shared.llm.router.OpenRouterClient`
2. All DB models inherit from `workbench.shared.db.base.Base`
3. Config loading uses `workbench.shared.config.loader` (deep_merge, read_env)
4. Agents subclass `AgentBase` from `agents/base.py`
5. Agents are registered in `src/workbench/api/app.py` under `_BUILTIN_AGENTS`
6. Each frontend tab has a lazy-loaded JS component in `src/workbench/webui/static/js/components/`

### Adding a New Agent

1. Create `agents/{name}/agent.py` with a class that extends `AgentBase`
2. Set `name`, `display_name`, `description`, `version`, `icon`
3. Define `_build_router()` returning a FastAPI `APIRouter` with your endpoints
4. Define `get_frontend_tab()` returning tab metadata (including JS path)
5. Register it in `_BUILTIN_AGENTS` in `src/workbench/api/app.py`
6. Create `src/workbench/webui/static/js/components/{name}-tab.js` — a self-registering component using `Router.register(name, renderFn)`

```python
# agents/myagent/agent.py
from agents.base import AgentBase
from fastapi import APIRouter

class MyAgent(AgentBase):
    name = "myagent"
    display_name = "My Agent"
    description = "Does something useful"
    version = "0.1.0"
    icon = "zap"

    def _build_router(self) -> APIRouter:
        router = APIRouter()
        router.add_api_route("/run", self.run, methods=["POST"])
        return router

    async def run(self, ...):
        ...
```

### SSE Streaming

Agents that run long operations (research, deliberation, planning) use SSE (Server-Sent Events). The pattern:

1. Service class has an `asyncio.Queue` for events and an `event_stream()` async generator
2. Agent endpoint returns `StreamingResponse(media_type="text/event-stream")`
3. Frontend tab reads the response body with `ReadableStream` and dispatches events
4. Stop support via a separate `POST /{id}/stop` endpoint + `asyncio.Event`

---

## Frontend

The web UI is a **vanilla JavaScript SPA** at `src/workbench/webui/static/`. No framework, no build step.

| Component | Purpose |
|-----------|---------|
| `api.js` | Centralized HTTP client with Bearer token auth |
| `utils.js` | HTML escaping and helpers |
| `theme.js` | Light/dark toggle, persisted to localStorage |
| `router.js` | Tab router with lazy script loading |
| `app.js` | Boot sequence, auth flow, settings, agent list, tab rendering |
| `components/chat-tab.js` | Chat agent UI |
| `components/news-tab.js` | News pipeline with interests CRUD, runs, status |
| `components/debate-tab.js` | Debate arena with polling, Director Mode, pause/resume |
| `components/research-tab.js` | SSE streaming research with live progress and markdown report |
| `components/deliberation-tab.js` | Frame selection, SSE phase tracking, multi-section results |
| `components/planning-tab.js` | 9 plan types, SSE generation, rendered output |
| `components/owui-tab.js` | Open WebUI health check + iframe embed |
| `css/base.css` | Layout, cards, buttons, forms, toggles, status indicators |
| `css/theme-dark.css` | Dark theme CSS custom properties |
| `css/theme-light.css` | Light theme CSS custom properties |

---

## Project Structure

```
workbench/
├── agents/                    # Agent packages (one directory per agent)
│   ├── base.py                # AgentBase — shared base class
│   ├── chat/agent.py          # Chat agent
│   ├── news/agent.py          # News pipeline agent
│   ├── debate/agent.py        # Debate arena agent
│   ├── research/agent.py      # Deep research agent
│   ├── deliberation/agent.py  # Multi-frame deliberation agent
│   └── planning/agent.py      # Strategic planning agent
│
├── src/workbench/             # Core infrastructure
│   ├── main.py                # CLI entry point (workbench serve|init-db|version)
│   ├── api/app.py             # FastAPI application factory, agent registry, middleware
│   ├── core/                  # Config, DB, auth, models, encryption, agent registry
│   ├── shared/                # Canonical shared primitives
│   │   ├── llm/router.py      # OpenRouterClient (all LLM calls, SSE, embeddings)
│   │   ├── config/loader.py   # deep_merge, read_env, expand_paths
│   │   ├── db/session.py      # PG + SQLite, DatabaseConfig, lazy init_db
│   │   ├── db/base.py         # Single DeclarativeBase
│   │   └── errors.py          # RouterExhaustedError, EmbeddingError, etc.
│   ├── services/              # Domain logic (one file per concern)
│   │   ├── debate_engine.py
│   │   ├── deliberation_service.py
│   │   ├── news_emailer.py
│   │   ├── news_pipeline.py
│   │   ├── news_scheduler.py
│   │   ├── news_store.py
│   │   ├── planning_service.py
│   │   └── research_orchestrator.py
│   └── webui/static/          # Frontend SPA (vanilla JS + CSS)
│       ├── index.html
│       ├── js/ (api.js, app.js, router.js, theme.js, utils.js)
│       ├── js/components/ (7 tab components)
│       └── css/ (base.css, theme-dark.css, theme-light.css)
│
├── config/default.toml        # Default configuration
├── alembic/                   # Database migrations (current: 002)
├── alembic.ini
├── tests/                     # Test suite (46 tests, pytest)
├── docker-compose.yml         # Docker deployment (PG + Workbench + optional Open WebUI)
├── Dockerfile
├── pyproject.toml             # Build config, dependencies, tool settings
│
├── citizen/                   # EXCLUDED ARCHIVE — German legal reasoning engine
│                               # (pgvector RAG, 9-stage pipeline, SGB II arithmetic)
│                               # DO NOT TOUCH — precision would be destroyed by integration
│
├── ai_news_scraper/           # Original sub-project (now integrated as news agent)
├── MADS/                      # Original sub-project (now integrated as debate agent)
├── PResearch/                 # Original sub-project (now integrated as research agent)
├── stoa/                      # Original sub-project (now integrated as deliberation agent)
├── PlanExe/                   # Original sub-project (now integrated as planning agent)
└── open-webui-wrapper/        # Electron desktop wrapper for Open WebUI (separate app)
```

---

## Sub-Project Origins

Each agent was adapted from a standalone project. The originals remain in the repo as reference:

| Agent | Origin | Key Adaptation |
|-------|--------|----------------|
| Debate | MADS/ | State machine extracted from CLI to `debate_engine.py` service |
| News | ai_news_scraper/ | Flask server replaced with FastAPI endpoints, scheduler integrated |
| Research | PResearch/ | WebSocket replaced with SSE streaming, tools preserved |
| Deliberation | stoa/ | SkillRegistry removed, 8 skill bodies embedded directly |
| Planning | PlanExe/ | Luigi DAG + llama-index + subprocess model replaced with single-LLM-call pipeline |
| citizen | citizen/ | **Excluded** — pgvector RAG + legal pipeline would lose precision if flattened to LLM prompts |

---

## Development

```bash
pip install -e ".[dev]" --break-system-packages
```

### Commands

```bash
# Run tests (46 tests, SQLite in-memory)
pytest tests/ -v

# Lint
ruff check src/workbench/ agents/

# Type check
mypy src/ agents/
```

### Notes

- Tests use SQLite in-memory — no external database needed.
- Ruff has two intentional rule exceptions at project level:
  - **B008** (FastAPI `Depends()` in signatures) — FastAPI's documented pattern, not a bug
  - **E501** (line length) — some string literals and template strings exceed 100 chars

---

## License

MIT — see [LICENSE](LICENSE).
