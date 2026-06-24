"""Workbench shared infrastructure — canonical primitives for all agents and services.

This package provides the single source of truth for:
- LLM API client (OpenRouterClient)
- Database session factories (shared async engine pattern)
- SQLAlchemy declarative base (Base)
- Configuration loading utilities (layered TOML merge, env var expansion)
- Shared exception hierarchy
"""

