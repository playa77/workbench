"""Application configuration via environment variables and CLI."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings


class PResearchConfig(BaseSettings):
    """Configuration loaded from env vars, .env file, and CLI overrides."""

    model_config = {
        "env_prefix": "PRESEARCH_", "env_file": ".env",
        "extra": "ignore", "populate_by_name": True,
    }

    # Provider selection
    provider: str = "custom"

    # Model defaults (validated against API at runtime)
    model: str = "deepseek/deepseek-v4-pro"
    fast_model: str = "deepseek/deepseek-v4-pro"

    # API keys (loaded from env)
    custom_api_key: str = Field(default="", alias="OPENROUTER_API_KEY")
    custom_api_base: str = "https://openrouter.ai/api/v1"

    # Brave Search
    brave_api_key: str = Field(default="", alias="BRAVE_API_KEY")

    # Proxy settings
    proxy: str | None = None
    custom_proxy: str | None = None

    # Agent behaviour
    max_iterations: int = 20  # 0 = unlimited
    max_concurrent_subagents: int = 3
    thinking_level: str = "high"

    # Output
    verbose: bool = False
    output_dir: str = "."

    # Web UI
    web_host: str = "127.0.0.1"
    web_port: int = 8000
    web_db_path: str = ""

    def get_proxy(self, provider: str | None = None) -> str | None:
        """Return the most specific proxy for the given provider."""
        provider_proxy = getattr(self, f"{provider}_proxy", None) if provider else None
        return provider_proxy or self.proxy
