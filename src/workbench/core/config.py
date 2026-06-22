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

from workbench.shared.config.loader import deep_merge
from workbench.shared.config.loader import read_env as _read_env_prefix

LOGGER = logging.getLogger(__name__)


class WorkbenchConfig(BaseModel):
    """Unified configuration for the Workbench application."""

    model_config = ConfigDict(extra="ignore")

    log_level: str = "INFO"
    data_dir: str = "data"
    api_host: str = "127.0.0.1"
    api_port: int = 8420
    api_cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:8420"])
    database_url: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_api_key_env: str = "OPENROUTER_API_KEY"
    openrouter_default_model: str = "deepseek/deepseek-v4-pro"
    openrouter_timeout_seconds: int = 120
    openrouter_max_retries: int = 2
    encryption_key: str = ""
    encryption_encrypt_reports: bool = False
    auth_api_key_prefix: str = "wb"
    auth_max_keys_per_user: int = 5
    auth_session_expiry_hours: int = 24
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from_address: str = ""
    smtp_use_tls: bool = True
    rate_limit_enabled: bool = True
    rate_limit_auth: str = "5/minute"
    rate_limit_agents: str = "60/minute"
    rate_limit_general: str = "120/minute"
    inference_provider_url: str = "https://openrouter.ai/api/v1"
    inference_strong_model: str = "deepseek/deepseek-v4-pro"
    inference_quick_model: str = "deepseek/deepseek-v4-flash"
    inference_requests_per_minute: int = 0
    api_csp_header: str = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "frame-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )
    api_strict_transport_security: str = ""

    @field_validator("api_cors_origins")
    @classmethod
    def _validate_cors_origins(cls, v: list[str]) -> list[str]:
        universal = "*"
        if universal in v:
            logger = logging.getLogger(__name__)
            logger.warning(
                "CORS origin set to '*' — this allows requests from any origin. "
                "For production, set specific origins via WORKBENCH_API__CORS_ORIGINS."
            )
        return v

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
        "api.csp_header": "api_csp_header",
        "api.strict_transport_security": "api_strict_transport_security",
        "database.url_env": None,
        "openrouter.base_url": "openrouter_base_url",
        "openrouter.api_key_env": "openrouter_api_key_env",
        "openrouter.default_model": "openrouter_default_model",
        "openrouter.timeout_seconds": "openrouter_timeout_seconds",
        "openrouter.max_retries": "openrouter_max_retries",
        "encryption.key_env": None,
        "encryption.encrypt_reports": "encryption_encrypt_reports",
        "auth.api_key_prefix": "auth_api_key_prefix",
        "auth.max_keys_per_user": "auth_max_keys_per_user",
        "auth.session_expiry_hours": "auth_session_expiry_hours",
        "smtp.host": "smtp_host",
        "smtp.port": "smtp_port",
        "smtp.user": "smtp_user",
        "smtp.password": "smtp_password",
        "smtp.from_address": "smtp_from_address",
        "smtp.use_tls": "smtp_use_tls",
        "rate_limit.enabled": "rate_limit_enabled",
        "rate_limit.auth": "rate_limit_auth",
        "rate_limit.agents": "rate_limit_agents",
        "rate_limit.general": "rate_limit_general",
        "inference.provider_url": "inference_provider_url",
        "inference.strong_model": "inference_strong_model",
        "inference.quick_model": "inference_quick_model",
        "inference.requests_per_minute": "inference_requests_per_minute",
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
    resolved_default = default_path
    if resolved_default is None:
        # Primary: relative to the source tree (useful in editable installs)
        source_tree = Path(__file__).resolve().parents[3] / "config" / "default.toml"
        # Fallback: relative to the current working directory (Docker / pip install)
        cwd_config = Path("config") / "default.toml"
        if source_tree.exists():
            resolved_default = source_tree
        elif cwd_config.exists():
            resolved_default = cwd_config
        else:
            resolved_default = source_tree  # will fail below but preserves original behavior

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
        if isinstance(raw.get("encryption"), dict):
            raw["encryption_encrypt_reports"] = raw["encryption"].get("encrypt_reports", False)

    flat: dict[str, Any] = {}
    for key in WorkbenchConfig.model_fields:
        if key in raw:
            flat[key] = raw[key]
    for section_name in ("general", "api", "openrouter", "auth", "rate_limit", "smtp", "inference"):
        if section_name in raw and isinstance(raw[section_name], dict):
            section = raw[section_name]
            section_to_flat = {
                "general": {"log_level": "log_level", "data_dir": "data_dir"},
                "api": {"host": "api_host", "port": "api_port", "cors_origins": "api_cors_origins", "csp_header": "api_csp_header", "strict_transport_security": "api_strict_transport_security"},
                "openrouter": {
                    "base_url": "openrouter_base_url",
                    "api_key_env": "openrouter_api_key_env",
                    "default_model": "openrouter_default_model",
                    "timeout_seconds": "openrouter_timeout_seconds",
                    "max_retries": "openrouter_max_retries",
                },
                "auth": {"api_key_prefix": "auth_api_key_prefix", "max_keys_per_user": "auth_max_keys_per_user", "session_expiry_hours": "auth_session_expiry_hours"},
                "rate_limit": {"enabled": "rate_limit_enabled", "auth": "rate_limit_auth", "agents": "rate_limit_agents", "general": "rate_limit_general"},
                "smtp": {"host": "smtp_host", "port": "smtp_port", "user": "smtp_user", "password": "smtp_password", "from_address": "smtp_from_address", "use_tls": "smtp_use_tls"},
                "inference": {
                    "provider_url": "inference_provider_url",
                    "strong_model": "inference_strong_model",
                    "quick_model": "inference_quick_model",
                    "requests_per_minute": "inference_requests_per_minute",
                },
            }
            mapping = section_to_flat.get(section_name, {})
            for src, dst in mapping.items():
                if src in section and dst not in flat:
                    flat[dst] = section[src]

    return WorkbenchConfig.model_validate(flat)
