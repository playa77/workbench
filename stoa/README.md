# Canonical Agent Workbench

A human-directed platform for high-fidelity compression, analysis, deliberation, and action across information and real workspaces.

## Installation

```bash
uv sync --all-extras
```

## Quickstart

1. Copy and edit config: `cp config/example.toml config/local.toml`
2. Export provider API key env vars used in config.
3. Start the API server:
   ```bash
   uv run python -m caw.cli.main serve --host 127.0.0.1 --port 8420
   ```
4. Create a session and call capability endpoints under `/api/v1`.

See [docs/quickstart.md](docs/quickstart.md) for a step-by-step first run.

## Architecture

- Design overview: [docs/design_doc.md](docs/design_doc.md)
- Technical specification: [docs/tech_spec.md](docs/tech_spec.md)
- Roadmap and milestones: [docs/roadmap.md](docs/roadmap.md)

## Development

```bash
uv run pre-commit install
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```
