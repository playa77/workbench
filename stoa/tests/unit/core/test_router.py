import pytest

from caw.core.config import CAWConfig
from caw.core.router import Router
from caw.errors import ProviderError
from caw.protocols.registry import ProviderRegistry


def _config() -> CAWConfig:
    return CAWConfig.model_validate(
        {
            "providers": {
                "primary": {
                    "type": "openai",
                    "api_key_env": "OPENAI_API_KEY",
                    "default_model": "gpt-4o-mini",
                },
                "backup": {
                    "type": "openai",
                    "api_key_env": "OPENAI_API_KEY",
                    "default_model": "gpt-4o",
                },
            },
            "routing": {"strategy": "config", "fallback_chain": ["backup", "missing"]},
        }
    )


@pytest.mark.asyncio
async def test_route_explicit() -> None:
    config = _config()
    router = Router(config, ProviderRegistry(config))
    selection = await router.route(explicit_provider="backup", explicit_model="x")
    assert selection.provider_key == "backup"
    assert selection.model == "x"


@pytest.mark.asyncio
async def test_route_skill_preference() -> None:
    config = _config()
    router = Router(config, ProviderRegistry(config))
    selection = await router.route(skill_preference="backup")
    assert selection.provider_key == "backup"


@pytest.mark.asyncio
async def test_route_config_default() -> None:
    config = _config()
    router = Router(config, ProviderRegistry(config))
    selection = await router.route()
    assert selection.provider_key == "primary"
    assert selection.model == "gpt-4o-mini"


@pytest.mark.asyncio
async def test_route_fallback_chain() -> None:
    config = _config()
    router = Router(config, ProviderRegistry(config))
    selection = await router.route()
    assert selection.fallback_chain == ["backup"]


@pytest.mark.asyncio
async def test_route_unknown_provider() -> None:
    config = _config()
    router = Router(config, ProviderRegistry(config))
    with pytest.raises(ProviderError):
        await router.route(explicit_provider="ghost")
