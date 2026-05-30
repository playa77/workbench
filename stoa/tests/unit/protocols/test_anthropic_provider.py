from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from caw.core.config import ProviderConfig
from caw.errors import ProviderError
from caw.protocols.anthropic_provider import AnthropicProvider
from caw.protocols.types import ProviderMessage


class _DummyAnthropicClient:
    def __init__(self, response: Any | None = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.last_kwargs: dict[str, Any] | None = None

        class _Messages:
            def __init__(self, outer: _DummyAnthropicClient) -> None:
                self.outer = outer

            async def create(self, **kwargs: Any) -> Any:
                self.outer.last_kwargs = kwargs
                if self.outer.error is not None:
                    raise self.outer.error
                if kwargs.get("stream"):

                    async def _iter() -> Any:
                        yield SimpleNamespace(
                            type="content_block_delta",
                            delta=SimpleNamespace(type="text_delta", text="hello"),
                        )
                        yield SimpleNamespace(type="message_stop")

                    return _iter()
                return self.outer.response

        self.messages = _Messages(self)


def _config() -> ProviderConfig:
    return ProviderConfig(
        type="anthropic", default_model="claude", api_key_env="TEST_ANTHROPIC_KEY"
    )


def test_provider_id() -> None:
    provider = AnthropicProvider(_config())
    assert provider.provider_id == "anthropic"


@pytest.mark.asyncio
async def test_system_message_extraction(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_ANTHROPIC_KEY", "k")
    response = SimpleNamespace(
        content=[], usage=SimpleNamespace(input_tokens=1, output_tokens=1), model="m"
    )
    dummy = _DummyAnthropicClient(response=response)

    provider = AnthropicProvider(_config())
    provider._client = dummy

    await provider.complete(
        messages=[
            ProviderMessage(role="system", content="sys one"),
            ProviderMessage(role="user", content="hello"),
        ],
        model="claude",
    )

    assert dummy.last_kwargs is not None
    assert dummy.last_kwargs["system"] == "sys one"
    assert dummy.last_kwargs["messages"][0]["role"] == "user"


@pytest.mark.asyncio
async def test_complete_maps_response(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_ANTHROPIC_KEY", "k")
    response = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="hello")],
        usage=SimpleNamespace(input_tokens=11, output_tokens=22),
        model="claude",
        stop_reason="end_turn",
    )
    provider = AnthropicProvider(_config())
    provider._client = _DummyAnthropicClient(response=response)

    mapped = await provider.complete([ProviderMessage(role="user", content="x")], model="claude")

    assert mapped.content == "hello"
    assert mapped.input_tokens == 11
    assert mapped.output_tokens == 22


@pytest.mark.asyncio
async def test_streaming_yields_chunks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_ANTHROPIC_KEY", "k")
    provider = AnthropicProvider(_config())
    provider._client = _DummyAnthropicClient()

    stream = await provider.complete(
        [ProviderMessage(role="user", content="x")],
        model="claude",
        stream=True,
    )
    chunks = [chunk async for chunk in stream]
    assert chunks[0].delta_text == "hello"
    assert chunks[-1].done is True


@pytest.mark.asyncio
async def test_auth_error_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_ANTHROPIC_KEY", "k")

    class _ErrError(Exception):
        status_code = 401

    provider = AnthropicProvider(_config())
    provider._client = _DummyAnthropicClient(error=_ErrError("auth"))

    with pytest.raises(ProviderError, match="auth") as exc:
        await provider.complete([ProviderMessage(role="user", content="x")], model="claude")
    assert exc.value.code == "provider_auth"


@pytest.mark.asyncio
async def test_rate_limit_error_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_ANTHROPIC_KEY", "k")

    class _ErrError(Exception):
        status_code = 429

    provider = AnthropicProvider(_config())
    provider._client = _DummyAnthropicClient(error=_ErrError("rate"))

    with pytest.raises(ProviderError) as exc:
        await provider.complete([ProviderMessage(role="user", content="x")], model="claude")
    assert exc.value.code == "provider_rate_limit"


@pytest.mark.asyncio
async def test_timeout_error_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_ANTHROPIC_KEY", "k")
    provider = AnthropicProvider(_config())
    provider._client = _DummyAnthropicClient(error=TimeoutError("slow"))

    with pytest.raises(ProviderError) as exc:
        await provider.complete([ProviderMessage(role="user", content="x")], model="claude")
    assert exc.value.code == "provider_timeout"


@pytest.mark.asyncio
async def test_missing_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TEST_ANTHROPIC_KEY", raising=False)
    provider = AnthropicProvider(_config())

    with pytest.raises(ProviderError) as exc:
        await provider.complete([ProviderMessage(role="user", content="x")], model="claude")
    assert exc.value.code == "provider_auth"
