# PResearch

**Autonomous Deep Research Agent**

```
  ███████╗██████╗ ███████╗███████╗███████╗ █████╗ ██████╗  ██████╗██╗  ██╗
  ██║ ██╔╝██╔══██╗██╔════╝██╔════╝██╔════╝██╔══██╗██╔══██╗██╔════╝██║  ██║
  █████╔╝ ██████╔╝█████╗  ███████╗█████╗  ███████║██████╔╝██║     ███████║
  ██╔═╔╝  ██╔══██╗██╔══╝  ╚════██║██╔══╝  ██╔══██║██╔══██╗██║     ██╔══██║
  ██║     ██║  ██║███████╗███████║███████╗██║  ██║██║  ██║╚██████╗██║  ██║
  ╚═╝     ╚═╝  ╚═╝╚══════╝╚══════╝╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝╚═╝  ╚═╝
```

PResearch is an autonomous research agent that takes a plain-language question, conducts multi-source web research through an unrestricted reasoning loop, and produces a publication-quality report where **every factual claim is backed by an inline citation**. The agent is not a fixed pipeline — it freely decides what to search, what to read, when to verify, and when to stop. All tools (search, scraping, code execution) are implemented in Python and work through OpenRouter.

---

## Table of Contents

- [Key Principles](#key-principles)
- [Quick Start](#quick-start)
- [How the Agent Works](#how-the-agent-works)
- [Tools](#tools)
- [The Mind Map](#the-mind-map)
- [Provider Abstraction](#provider-abstraction)
- [Configuration Reference](#configuration-reference)
- [CLI Reference](#cli-reference)
- [Web UI](#web-ui)
- [Proxy Support](#proxy-support)
- [Output Format](#output-format)
- [Architecture](#architecture)
- [Dependencies](#dependencies)
- [License](#license)

---

## Key Principles

1. **No hardcoded models.** Model IDs are configuration defaults, fetched and validated against the OpenRouter API at runtime. The default model is `deepseek/deepseek-v4-pro`, but the user can override via CLI flags or environment variables.

2. **No hardcoded tools.** Web search uses the Brave Search API, page scraping uses `trafilatura` with an `httpx`/`beautifulsoup4` fallback, and code execution uses a subprocess sandbox. None of these are tied to any provider's built-in features. The LLM calls Python functions via standard function-calling; our code executes them and returns results.

3. **No forced behaviour.** The agent's system prompt gives it a four-phase research methodology (Decompose, Search-and-Read, Verify-and-Deepen, Synthesize), but it is not forced into any fixed order. It freely calls tools, revisits earlier phases, and decides when it has gathered enough evidence to write the report.

4. **Interruptible.** While the agent loop is running, a concurrent `asyncio` task monitors `stdin`. The user can type `stop` to force immediate synthesis, or type any other message (e.g., "focus more on the economic impact") which is injected into the conversation as a `[USER INTERRUPT]`.

5. **Every sentence cited.** The system prompt enforces that every factual claim in the final report carries an inline citation `[N]` linking to a numbered source at the bottom. The agent is instructed to omit any claim it cannot cite.

6. **Plain text copyable.** The Rich library is used only for the live progress panel in the terminal. The report itself is clean Markdown that can be copied, piped, or saved to a file without any formatting artifacts.

---

## Quick Start

### Prerequisites

- Python 3.10 or later
- An OpenRouter API key (get one at [openrouter.ai](https://openrouter.ai/keys))
- A Brave Search API key (get one at [brave.com/search/api](https://brave.com/search/api/))

### Installation

```bash
git clone https://github.com/playa77/PResearch.git
cd PResearch
pip install -e .

# For the Web UI:
pip install -e ".[web]"
```

### Set your API keys

```bash
export OPENROUTER_API_KEY=sk-or-v1-...
export BRAVE_API_KEY=BSA-...
```

Or create a `.env` file in the project root (see `.env.example`).

### Run a research query

```bash
# Default model (deepseek/deepseek-v4-pro via OpenRouter)
presearch "What are the latest breakthroughs in quantum computing?"

# Use a different model
presearch --model anthropic/claude-sonnet-4 "What are the latest breakthroughs in quantum computing?"
```

### Other common commands

```bash
# List all models available from OpenRouter
presearch --list-models

# Save the report to a file
presearch -o report.md "your query"

# Remove the iteration safety limit (agent runs until it decides to stop)
presearch --max-iterations 0 "your query"

# Run through a proxy
presearch --proxy http://127.0.0.1:7890 "your query"
```

---

## How the Agent Works

### The Autonomous Loop

```
User Query
     │
     ▼
┌──────────────────────────────────────────────────────────────┐
│                     AUTONOMOUS LOOP                          │
│                                                              │
│  The LLM sits in a multi-turn chat with function-calling     │
│  tools. It FREELY decides what to call and when.             │
│                                                              │
│  Loop:                                                       │
│  1. LLM receives: system prompt + current mind map state     │
│  2. LLM responds with either:                                │
│     a. Tool calls → orchestrator executes them →             │
│        all results sent back in one batch → repeat           │
│     b. Final text (after draft_report()) → this IS the       │
│        report → done                                         │
│                                                              │
│  Termination (checked in this order):                        │
│  1. Agent calls draft_report() → it decided to stop         │
│  2. User sends "stop" via stdin → forced synthesis           │
│  3. Safety limit reached (default 20 iterations,             │
│     configurable, set to 0 for unlimited)                    │
└──────────────────────────────────────────────────────────────┘
     │
     ▼
Final Report (Markdown with inline citations)
```

### The System Prompt

The system prompt (`src/presearch/prompts.py`) is a ~7,000-character document that gives the agent a four-phase research methodology:

| Phase | What the agent does |
|---|---|
| **1. Decompose** | Break the query into 5-8 sub-questions covering What, Why, How, Who, When, debates, and implications. |
| **2. Search and Read** | For each sub-question, run `web_search` with diverse queries, then `read_webpage` on 2-3 best results, immediately calling `update_findings`. Do 15-30 searches and read 10-20 pages minimum. |
| **3. Verify and Deepen** | Cross-reference claims across 2+ independent sources. Call `log_contradiction` for disagreements. Use `execute_python` for math/data verification. Assign confidence scores honestly. |
| **4. Synthesize** | Call `draft_report()`. Write the complete report as the next response. |

The prompt also contains strict citation rules (every factual claim must carry `[N]`), a required report structure (Executive Summary, thematic sections, Contradictions & Debates, Limitations, Sources), and quality standards (depth, specificity, balance, honesty).

### Batch Function Responses

When the LLM returns multiple tool calls in a single response, the orchestrator executes all of them concurrently, then sends **all results back in a single message**. This is the correct behaviour for the OpenAI-compatible API (and is handled by `ChatSession.send_function_responses()`).

### User Interrupts

While the agent loop runs, a separate `asyncio` task polls `stdin` using `select()` (non-blocking, 300ms intervals):

- **`stop` / `quit` / `done`** — The agent is told to call `draft_report()` and write the best report it can with current findings.
- **Any other text** — Injected into the conversation as `[USER INTERRUPT]: <message>`. The agent sees it and adjusts its research direction.

---

## Tools

All tools are provider-agnostic Python functions, registered via `ToolRegistry` and exposed to the LLM through standard function-calling declarations. The agent discovers tools automatically from the registry — adding a new tool requires zero changes to the agent loop.

| Tool | Implementation | Purpose |
|---|---|---|
| `web_search(query, max_results)` | Brave Search API | API-key web search. Returns `{title, url, snippet}` for each result. Max 20 results per call. |
| `read_webpage(url)` | `trafilatura` primary, `httpx` + `beautifulsoup4` fallback | Fetches a URL and extracts the main article content as clean Markdown. Strips navigation, scripts, ads. Truncates at 15,000 chars to protect context. |
| `execute_python(code, timeout)` | `subprocess.run()` in a restricted environment | Runs Python code in an isolated subprocess with a 30-second timeout and a restricted `PATH`. Used for math verification, data analysis, and fact-checking. |
| `update_findings(topic, content, sources, confidence)` | Writes to the `MindMap` data structure | Records a verified finding under a topic node with source URLs and a confidence score (0.0-1.0). The agent calls this frequently to build its working memory. |
| `log_contradiction(topic, claim_a, claim_b, source_a, source_b)` | Writes to the `MindMap` data structure | Records a conflict between two sources. The agent is instructed to never ignore contradictions — they must appear in the final report. |
| `spawn_subagent(query, context)` | Creates a new `ChatSession` with a focused system prompt | Launches an independent sub-agent that runs its own mini research loop (max 5 iterations, no further sub-spawning). Returns structured findings. Used for clearly independent sub-questions. |
| `draft_report()` | Sets `state.draft_requested = True`, returns mind map JSON | Signals the agent is ready to write the final report. Returns the complete mind map data so the agent can reference it while writing. The agent's next text response becomes the report. |

---

## The Mind Map

The mind map (`src/presearch/models/mind_map.py`) is the agent's **persistent epistemic state** — a hierarchical tree of everything it knows, structured by topic. Even if the LLM's conversation history gets long, the mind map retains all findings in a compact format that is included in the system prompt.

### Structure

```
MindMap
├── root: MindMapNode (topic = the original query)
│   ├── child: MindMapNode (topic = "Quantum Hardware")
│   │   ├── content: "IBM unveiled Nighthawk, a 120-qubit processor..."
│   │   ├── sources: [{url, title}, {url, title}]
│   │   ├── confidence: 0.95
│   │   └── contradictions: []
│   ├── child: MindMapNode (topic = "Error Correction")
│   │   ├── content: "Google's Willow chip operates below threshold..."
│   │   ├── sources: [{url, title}, {url, title}, {url, title}]
│   │   ├── confidence: 0.98
│   │   └── contradictions: [Contradiction(...)]
│   └── ...
└── query: "What are the latest breakthroughs in quantum computing?"
```

### Key methods

- `add_finding(topic, content, sources, confidence)` — Finds or creates a topic node and appends the finding. Content is accumulated (not replaced), sources are extended, confidence takes the max.
- `log_contradiction(topic, claim_a, claim_b, source_a, source_b)` — Attaches a `Contradiction` record to the topic node.
- `get_summary()` — Returns a compact text tree used in the system prompt so the agent knows its current state.
- `get_gaps()` — Returns topics with confidence below 0.3 (areas needing more research).
- `get_contradictions()` — Returns all unresolved contradictions across the entire tree.
- `source_count()` — Total number of sources across all nodes.

---

## Provider Abstraction

PResearch uses OpenRouter as the LLM inference provider, leveraging the OpenAI-compatible API. The provider layer (`src/presearch/providers/`) defines two abstract base classes:

### `ProviderInterface`

Every provider must implement:

| Method | Description |
|---|---|
| `generate(messages, system_instruction, tools, thinking_level)` | One-shot generation with optional tool declarations. |
| `generate_stream(messages, ...)` | Streaming generation (yields text chunks). |
| `create_chat(system_instruction, tools, thinking_level)` | Creates a multi-turn `ChatSession` — the primary interface used by the orchestrator. |
| `list_models()` | Fetches available models from the provider API. Returns `list[ModelInfo]`. |

### `ChatSession`

The multi-turn chat interface used by the agent loop:

| Method | Description |
|---|---|
| `send(message)` | Send a user message, returns `GenerateResponse` with text and/or function calls. |
| `send_function_response(name, response)` | Send a single tool result back to the model. |
| `send_function_responses(responses)` | Send multiple tool results in one batch. |
| `get_history()` | Return the conversation history. |

### Provider-agnostic types

All types are defined in `src/presearch/providers/types.py`:

- `Message` — role + content
- `FunctionCall` — name + args dict
- `GenerateResponse` — text, function_calls, thinking, usage, raw
- `ModelInfo` — id, name, context_window
- `ToolDeclaration` — name, description, parameters (JSON Schema)

---

## Configuration Reference

Configuration is handled by `PResearchConfig` (Pydantic Settings), loaded from environment variables, a `.env` file, and CLI overrides (CLI takes priority).

| Variable | CLI Flag | Default | Description |
|---|---|---|---|
| `OPENROUTER_API_KEY` | — | *(required)* | OpenRouter API key. Also settable as `PRESEARCH_CUSTOM_API_KEY`. |
| `BRAVE_API_KEY` | — | *(required)* | Brave Search API key. |
| `PRESEARCH_CUSTOM_API_BASE` | — | `https://openrouter.ai/api/v1` | Base URL for OpenRouter-compatible endpoint. |
| `PRESEARCH_MODEL` | `--model` | `deepseek/deepseek-v4-pro` | Primary model for the agent loop. |
| `PRESEARCH_FAST_MODEL` | `--fast-model` | `deepseek/deepseek-v4-pro` | Fast model for sub-agents. |
| `PRESEARCH_PROXY` | `--proxy` | — | Global HTTP proxy for all outbound requests. |
| `PRESEARCH_MAX_ITERATIONS` | `--max-iterations` | `20` | Safety limit on agent loop iterations. Set to `0` for unlimited. |
| `PRESEARCH_MAX_CONCURRENT_SUBAGENTS` | — | `3` | Maximum number of concurrent sub-agents. |
| `PRESEARCH_THINKING_LEVEL` | — | `high` | Thinking level passed to providers that support it. |
| `PRESEARCH_VERBOSE` | `--verbose` | `false` | Enable verbose logging. |
| `PRESEARCH_OUTPUT_DIR` | — | `.` | Default directory for saved reports. |

### Priority order

CLI flags > environment variables > `.env` file > defaults.

### Proxy resolution

When proxy is configured, it is applied to all outbound requests including API calls and web scraping.

---

## CLI Reference

```
presearch [OPTIONS] [QUERY]

Arguments:
  QUERY                    The research question (omit for usage info).

Options:
  --model TEXT              Override the primary model.
  --fast-model TEXT         Override the fast/sub-agent model.
  --provider TEXT           LLM provider (custom for OpenRouter).
  --proxy TEXT              HTTP proxy URL (e.g., http://127.0.0.1:7890).
  --list-models             Fetch and display available models from the API.
  --verbose                 Enable verbose logging.
  -o, --output PATH         Save the final report to a file.
  --max-iterations INTEGER  Agent loop safety limit (0 = unlimited).
  --web                     Launch the Web UI instead of CLI mode.
  --host TEXT               Web UI bind address (default: 127.0.0.1).
  --port INTEGER            Web UI port (default: 8000).
  --help                    Show usage and exit.
```

### Examples

```bash
# Basic research
presearch "Impact of AI on healthcare diagnostics"

# Use a different model via OpenRouter
presearch --model anthropic/claude-sonnet-4 "Compare monetary policy approaches of the Fed vs ECB"

# Save output and remove iteration limit
presearch --max-iterations 0 -o deep_dive.md "History and future of nuclear fusion energy"

# List models to see what's available via OpenRouter
presearch --list-models
```

---

## Web UI

PResearch includes an optional browser-based interface that streams research events in real time over WebSocket.

### Installation

```bash
pip install -e ".[web]"
```

### Launch

```bash
# Via CLI flag
presearch --web

# Or directly
presearch-web

# Custom host/port
presearch --web --host 0.0.0.0 --port 3000
```

Then open `http://127.0.0.1:8000` in your browser.

### Features

- **Real-time streaming** — tool calls, thinking, stats, and the final report stream over WebSocket as the agent works.
- **Settings panel** — override model, max iterations, and other config fields from the browser.
- **User interrupts** — type a message or click Stop to redirect or halt the agent mid-research.
- **Past reports** — completed reports are stored in SQLite (`~/.presearch/reports.db`) and can be browsed, viewed, or deleted.
- **Concurrent sessions** — each browser tab gets its own independent Orchestrator instance.

### Architecture

The Web UI uses the same `UIProtocol` interface as the CLI's `ConsoleUI`. A `WebUI` class implements this protocol by serializing events as JSON and sending them over WebSocket, rather than printing to the terminal. The Orchestrator itself is unchanged.

```
Browser  <──WebSocket──>  Starlette  ──>  Orchestrator (existing)
                                           ├── WebUI (replaces ConsoleUI)
                                           ├── Provider (OpenRouter)
                                           ├── ToolRegistry (existing)
                                           └── ResearchState (existing)
```

### Configuration

| Variable | Default | Description |
|---|---|---|
| `PRESEARCH_WEB_HOST` | `127.0.0.1` | Web server bind address |
| `PRESEARCH_WEB_PORT` | `8000` | Web server port |
| `PRESEARCH_WEB_DB_PATH` | `~/.presearch/reports.db` | SQLite database path for past reports |

---

## Proxy Support

PResearch supports HTTP and SOCKS proxies for all outbound traffic.

```bash
# Global proxy (applies to all API calls AND web scraping)
export PRESEARCH_PROXY=http://127.0.0.1:7890

# CLI override
presearch --proxy http://proxy.example.com:8080 "your query"
```

---

## Output Format

The final report is plain Markdown with this structure:

```markdown
# Research Report: {Descriptive Title}

## Executive Summary
4-6 dense sentences: what was investigated, key findings with data,
conclusions, and caveats.

## {Thematic Section 1}
3-5 substantive paragraphs with inline citations [N] for every
factual claim. Specific data, statistics, expert opinions.

## {Thematic Section 2}
...

## Contradictions & Debates
Where sources disagree, both sides presented with citations.
Assessment of which has stronger evidence and why.

## Limitations
Gaps in available sources, unverifiable claims, areas needing
further investigation.

## Sources
[1] Source Title - https://source-url.com/path
[2] Source Title - https://source-url.com/path
...
```

The report is printed to `stdout` as plain text and can optionally be saved to a file with `-o`.

---

## Architecture

```
src/presearch/
├── __init__.py              # Package version
├── __main__.py              # python -m presearch entry point
├── cli.py                   # Click CLI (argument parsing, provider init, orchestrator launch)
├── config.py                # PResearchConfig (Pydantic Settings from env/.env/CLI)
├── prompts.py               # SYSTEM_TEMPLATE — the 7K-char agent system prompt
├── orchestrator.py          # Orchestrator class — the autonomous agent loop
│
├── models/
│   ├── mind_map.py          # MindMap, MindMapNode, Source, Contradiction
│   ├── task_graph.py        # TaskGraph, TaskNode, TaskStatus (sub-task tracking)
│   └── state.py             # ResearchState, ActionLog, TokenUsage (session state)
│
├── providers/
│   ├── __init__.py          # get_provider() factory + PROVIDER_REGISTRY
│   ├── base.py              # ProviderInterface (ABC), ChatSession (ABC)
│   ├── types.py             # Message, GenerateResponse, FunctionCall, ModelInfo, ToolDeclaration
│   ├── openai/
│   │   ├── provider.py      # OpenaiProvider — OpenAI-compatible API integration
│   │   └── chat.py          # OpenaiChatSession — multi-turn chat with tool_call_id tracking
│   └── custom/
│       └── provider.py      # CustomProvider — subclass of OpenaiProvider (default: OpenRouter)
│
├── tools/
│   ├── registry.py          # ToolRegistry + create_default_registry()
│   ├── web_search.py        # Brave Search API
│   ├── web_reader.py        # trafilatura extraction + httpx/bs4 fallback
│   ├── code_executor.py     # Sandboxed subprocess Python execution
│   ├── research_tools.py    # update_findings, log_contradiction, draft_report
│   └── subagent_tool.py     # spawn_subagent (mini research loop)
│
└── output/
    ├── console.py           # ConsoleUI — Rich banner, live panel, model table
    ├── protocol.py          # UIProtocol — async display contract (ConsoleUI & WebUI)
    └── markdown.py          # ensure_citations, format_source_list, save_report

├── web/                     # Optional Web UI (pip install -e ".[web]")
│   ├── __init__.py          # Exports create_app
│   ├── app.py               # Starlette ASGI app factory + presearch-web entry point
│   ├── models.py            # Pydantic models: WSEvent, ConfigResponse, ReportSummary
│   ├── webui.py             # WebUI — UIProtocol over WebSocket
│   ├── db.py                # Async SQLite storage for past reports
│   ├── session.py           # ResearchSession + SessionManager
│   ├── routes.py            # REST endpoints (config, reports, health)
│   ├── ws.py                # WebSocket endpoint for real-time streaming
│   └── static/
│       └── index.html       # Single-page frontend (vanilla JS, dark theme)
```

### Data flow

```
CLI (cli.py)
 │  Parses args, builds PResearchConfig, creates provider via get_provider()
 ▼
Orchestrator (orchestrator.py)
 │  Builds system prompt from SYSTEM_TEMPLATE + current ResearchState
 │  Creates a ChatSession via provider.create_chat()
 │  Enters the agent loop
 ▼
Agent Loop
 │  Sends query to LLM → gets response
 │  If response has function_calls:
 │    Execute ALL calls via ToolRegistry.execute()
 │    Send ALL results back via chat.send_function_responses()
 │    Process the next response (may recurse if more calls)
 │  If response has text + draft_requested:
 │    Return text as the final report
 │  If over budget:
 │    Force synthesis via _finalize()
 ▼
Tools (tools/*.py)
 │  Each tool is an async function: (args, **ctx) -> dict
 │  ctx contains: state (ResearchState), provider, config
 │  Tools modify state.mind_map via add_finding(), log_contradiction()
 ▼
ConsoleUI (output/console.py)
 │  Rich Live panel updated after each tool call
 │  Shows: tool actions log, mind map tree, iteration/source/token stats
 ▼
Final Report → stdout and optionally → file
```

---

## Dependencies

| Package | Purpose |
|---|---|
| `openai` | OpenAI SDK — used for OpenRouter API compatibility |
| `pydantic` | Data models (MindMap, ResearchState, provider types) |
| `pydantic-settings` | Configuration from environment, `.env`, CLI |
| `rich` | Terminal UI — banner, live progress panel, model table |
| `click` | CLI argument parsing |
| `trafilatura` | Article/webpage content extraction |
| `httpx` | Async HTTP client (Brave Search API, fallback scraping) |
| `beautifulsoup4` | HTML parsing (fallback scraping) |
| `lxml` | Fast HTML/XML parser (used by trafilatura and bs4) |

### Dev dependencies

`pytest`, `pytest-asyncio`, `ruff`, `mypy`

### Optional dependencies

`starlette`, `uvicorn`, `aiosqlite` (for the Web UI)

---

## License

MIT — see [LICENSE](LICENSE).
