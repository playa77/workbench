import pytest

from caw.core.config import CAWConfig
from caw.errors import ProviderError
from caw.protocols.anthropic_provider import AnthropicProvider
from caw.protocols.openai_provider import OpenAIProvider
from caw.protocols.registry import ProviderRegistry


def _config() -> CAWConfig:
    return CAWConfig.model_validate(
        {
            "providers": {
                "anthropic": {"type": "anthropic", "default_model": "claude", "api_key_env": "X"},
                "openai": {"type": "openai", "default_model": "gpt", "api_key_env": "Y"},
                "local": {
                    "type": "openai_compatible",
                    "default_model": "llm",
                    "api_key_env": "Z",
                    "base_url": "http://localhost:11434/v1",
                },
            }
        }
    )


def test_registry_creates_providers() -> None:
    registry = ProviderRegistry(_config())
    assert set(registry.list_providers()) == {"anthropic", "openai", "local"}


def test_registry_get_valid() -> None:
    registry = ProviderRegistry(_config())
    assert isinstance(registry.get("anthropic"), AnthropicProvider)
    assert isinstance(registry.get("openai"), OpenAIProvider)


def test_registry_get_invalid() -> None:
    registry = ProviderRegistry(_config())
    with pytest.raises(ProviderError):
        registry.get("nonexistent")
