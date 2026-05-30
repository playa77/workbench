# Workbench

**Unified BYOK AI Workbench** — agent-driven infrastructure for LLM-powered tools.

Bring your own OpenRouter key. Run locally. No telemetry.

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688)](https://fastapi.tiangolo.com)

---

## Architecture

Workbench is a single FastAPI server that hosts multiple AI agents behind a web UI. Each agent occupies its own browser tab — a dedicated sandbox with isolated state, lazy-loaded code, and shared compute resources.

```
Browser                   FastAPI Server
┌──────────────────┐      ┌─────────────────────────────────┐
│  [Chat] [News]   │      │  /api/v1/agents/{name}/...      │
│  [Debate][Research]│    │                                 │
│  [Plan][Delib]   │      │  Agent Registry (lazy-load)     │
│                  │      │  OpenRouter Client Pool         │
│  ┌────────────┐  │      │  Auth / Encryption / DB        │
│  │ Agent Tab  │──┼──────│                                 │
│  └────────────┘  │      └─────────────────────────────────┘
└──────────────────┘
```

## Agents

| Agent | Capability | Tab |
|-------|-----------|-----|
| **Chat** | LLM chat with your OpenRouter key | message-circle |
| **Deep Research** | Multi-source web research with plan+synthesize | search |
| **Debate Arena** | Multi-agent debate (9 roles) | users |
| **Deliberation** | Multi-frame analysis (Pro/Con, SWOT, Forces) | scale |
| **News Pipeline** | RSS scraping, AI theme analysis, daily briefs | newspaper |
| **Strategic Planning** | Goal-to-plan generation with SWOT, WBS, Gantt | target |

Each agent is a self-contained Python package under `agents/`. Agents register their own FastAPI routes, define frontend tabs, and manage per-user settings — all through a shared registry.

## BYOK

Bring Your Own Key. You supply an OpenRouter API key through the Settings panel. Keys are encrypted at rest with AES-256-GCM. Your key never leaves your server — Workbench makes no external calls except to OpenRouter on your behalf.

Supported models include DeepSeek V3, Claude, GPT-4o, Gemini, Llama 4, and 250+ others through OpenRouter's unified API.

## Quick Start

### Prerequisites

- Python 3.11 or later
- An [OpenRouter](https://openrouter.ai) API key

### Install

```bash
git clone https://github.com/your-org/workbench.git
cd workbench
python -m venv .venv
source .venv/bin/activate
pip install -e .

# Optional: install agent-specific dependencies
pip install -e ".[news,research,planning]"
```

### Run

```bash
# Initialize database
workbench init-db

# Start server
workbench serve
```

Open `http://localhost:8420` in your browser. Register a username, paste your OpenRouter key in Settings, and start using agents.

### Docker

```bash
docker compose up -d
```

The compose file starts PostgreSQL 16 (with pgvector), Workbench on port 8420, and optionally OpenWebUI on port 3000.

## Configuration

| Source | Priority | Example |
|--------|----------|---------|
| `config/default.toml` | lowest | `api.port = 8420` |
| `.env` file | medium | `DATABASE_URL=...` |
| `WORKBENCH_*` env vars | highest | `WORKBENCH_API__PORT=9000` |

### Key settings

```
# In .env
DATABASE_URL=sqlite+aiosqlite:///data/workbench.db   # SQLite (default)
# DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/workbench  # PostgreSQL
ENCRYPTION_KEY=your-64-char-hex-key
OPENROUTER_API_KEY=sk-or-v1-...   # Optional server-wide fallback
```

Generate an encryption key:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

## Development

```bash
pip install -e ".[dev]"

# Lint
ruff check .

# Type check
mypy src/ agents/

# Tests
pytest
```

### Adding a new agent

1. Create `agents/{name}/__init__.py` and `agents/{name}/agent.py`
2. Subclass `AgentBase` from `agents.base`
3. Define `name`, `display_name`, `description`, `icon`, `_build_router()`
4. Register it in `src/workbench/api/app.py` in `_auto_register_agents()`
5. Optionally create a frontend tab component in `src/workbench/webui/static/js/components/{name}-tab.js`

```python
# agents/myagent/agent.py
from agents.base import AgentBase
from fastapi import APIRouter

class MyAgent(AgentBase):
    name = "myagent"
    display_name = "My Agent"
    description = "Does something useful"
    icon = "zap"

    def _build_router(self) -> APIRouter:
        router = APIRouter()
        router.add_api_route("/run", self.run, methods=["POST"])
        return router

    async def run(self, ...):
        ...
```

## Project Structure

```
workbench/
├── agents/               # Agent packages (one per tab)
│   ├── base.py           # AgentBase class
│   ├── chat/             # Chat agent
│   ├── research/         # Deep research agent
│   ├── debate/           # Debate arena agent
│   ├── deliberation/     # Multi-frame analysis agent
│   ├── news/             # News pipeline agent
│   ├── planning/         # Strategic planning agent
│   └── legal/            # Legal agent (planned)
├── src/workbench/        # Core infrastructure
│   ├── core/             # Config, DB, models, auth, router, registry
│   ├── api/              # FastAPI app, routes, deps
│   ├── services/         # Business logic (news pipeline, store)
│   └── webui/static/     # Frontend SPA (vanilla JS)
├── config/default.toml   # Default configuration
├── alembic/              # Database migrations
├── docker-compose.yml    # Docker deployment
└── pyproject.toml        # Build & dependency configuration
```

## License

MIT — see [LICENSE](LICENSE).
