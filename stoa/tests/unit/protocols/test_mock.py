import pytest

from caw.errors import ProviderError
from caw.protocols.mock import MockProvider
from caw.protocols.provider import ModelProvider
from caw.protocols.types import ProviderMessage


@pytest.mark.asyncio
async def test_mock_complete_default() -> None:
    provider = MockProvider()
    response = await provider.complete(
        [ProviderMessage(role="user", content="hello")], model="test"
    )
    assert isinstance(response.content, str)
    assert response.content == "Mock response."


@pytest.mark.asyncio
async def test_mock_complete_custom() -> None:
    provider = MockProvider(response_text="Custom")
    response = await provider.complete(
        [ProviderMessage(role="user", content="hello")], model="test"
    )
    assert response.content == "Custom"


@pytest.mark.asyncio
async def test_mock_streaming() -> None:
    provider = MockProvider(response_text="alpha beta")
    stream = await provider.complete(
        [ProviderMessage(role="user", content="hello")], model="test", stream=True
    )
    parts: list[str] = []
    async for chunk in stream:
        parts.append(chunk.delta_text)
    assert "".join(parts).strip() == "alpha beta"


@pytest.mark.asyncio
async def test_mock_failure() -> None:
    provider = MockProvider(fail=True)
    with pytest.raises(ProviderError):
        await provider.complete([ProviderMessage(role="user", content="hello")], model="test")


@pytest.mark.asyncio
async def test_mock_health_check() -> None:
    healthy = await MockProvider().health_check()
    unhealthy = await MockProvider(fail=True).health_check()
    assert healthy.available is True
    assert unhealthy.available is False


def test_mock_isinstance_protocol() -> None:
    assert isinstance(MockProvider(), ModelProvider)
