"""Workbench core configuration.

Layered config: default.toml -> .env -> WORKBENCH_* env vars -> per-user DB overrides.

Now uses shared config loader primitives from workbench.shared.config.loader.
"""

from __future__ import annotations

import logging
import os
import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from workbench.shared.config.loader import deep_merge, read_env as _read_env_prefix

LOGGER = logging.getLogger(__name__)


class WorkbenchConfig(BaseModel):
    """Unified configuration for the Workbench application."""

    model_config = ConfigDict(extra="ignore")

    log_level: str = "INFO"
    data_dir: str = "data"
    api_host: str = "0.0.0.0"
    api_port: int = 8420
    api_cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:8420"])
    database_url: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_api_key_env: str = "OPENROUTER_API_KEY"
    openrouter_default_model: str = "deepseek/deepseek-v4-pro"
    openrouter_timeout_seconds: int = 120
    openrouter_max_retries: int = 2
    encryption_key: str = ""
    auth_api_key_prefix: str = "wb"
    auth_max_keys_per_user: int = 5

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, v: str) -> str:
        if v.upper() not in {"DEBUG", "INFO", "WARNING", "ERROR"}:
            raise ValueError(f"Invalid log_level: {v}")
        return v.upper()


def _read_env() -> dict[str, Any]:
    return _read_env_prefix("WORKBENCH_")


def _flatten_env_overrides(env_overrides: dict[str, Any]) -> dict[str, Any]:
    root_map = {
        "general.log_level": "log_level",
        "general.data_dir": "data_dir",
        "api.host": "api_host",
        "api.port": "api_port",
        "api.cors_origins": "api_cors_origins",
        "database.url_env": None,
        "openrouter.base_url": "openrouter_base_url",
        "openrouter.api_key_env": "openrouter_api_key_env",
        "openrouter.default_model": "openrouter_default_model",
        "openrouter.timeout_seconds": "openrouter_timeout_seconds",
        "openrouter.max_retries": "openrouter_max_retries",
        "encryption.key_env": None,
        "auth.api_key_prefix": "auth_api_key_prefix",
        "auth.max_keys_per_user": "auth_max_keys_per_user",
    }
    flat: dict[str, Any] = {}
    for section_key, section in env_overrides.items():
        if not isinstance(section, dict):
            continue
        for key, value in section.items():
            path = f"{section_key}.{key}"
            target = root_map.get(path)
            if target is not None:
                flat[target] = value
            else:
                LOGGER.warning("Unknown WORKBENCH_* override: %s", path)
    return flat


def load_config(default_path: Path | None = None) -> WorkbenchConfig:
    """Load configuration from default.toml and env vars."""
    resolved_default = default_path or (
        Path(__file__).resolve().parents[3] / "config" / "default.toml"
    )

    raw: dict[str, Any] = {}
    if resolved_default.exists():
        raw = tomllib.loads(resolved_default.read_text())

    env_raw = _read_env()
    raw = deep_merge(raw, env_raw)

    flat_overrides = _flatten_env_overrides(raw)
    raw.update(flat_overrides)

    if "database" in raw and "url_env" in raw.get("database", {}):
        url_env = raw["database"]["url_env"]
        raw["database_url"] = os.environ.get(url_env, raw.get("database_url", ""))
    else:
        raw["database_url"] = os.environ.get("DATABASE_URL", raw.get("database_url", ""))

    if "encryption" in raw:
        key_env = raw["encryption"].get("key_env", "ENCRYPTION_KEY") if isinstance(raw.get("encryption"), dict) else "ENCRYPTION_KEY"
        raw["encryption_key"] = os.environ.get(key_env, raw.get("encryption_key", ""))

    flat: dict[str, Any] = {}
    for key in WorkbenchConfig.model_fields:
        if key in raw:
            flat[key] = raw[key]
    for section_name in ("general", "api", "openrouter", "auth"):
        if section_name in raw and isinstance(raw[section_name], dict):
            section = raw[section_name]
            section_to_flat = {
                "general": {"log_level": "log_level", "data_dir": "data_dir"},
                "api": {"host": "api_host", "port": "api_port", "cors_origins": "api_cors_origins"},
                "openrouter": {
                    "base_url": "openrouter_base_url",
                    "api_key_env": "openrouter_api_key_env",
                    "default_model": "openrouter_default_model",
                    "timeout_seconds": "openrouter_timeout_seconds",
                    "max_retries": "openrouter_max_retries",
                },
                "auth": {"api_key_prefix": "auth_api_key_prefix", "max_keys_per_user": "auth_max_keys_per_user"},
            }
            mapping = section_to_flat.get(section_name, {})
            for src, dst in mapping.items():
                if src in section and dst not in flat:
                    flat[dst] = section[src]

    return WorkbenchConfig.model_validate(flat)
