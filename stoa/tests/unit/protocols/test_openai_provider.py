from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from caw.core.config import ProviderConfig
from caw.errors import ProviderError
from caw.protocols.openai_provider import OpenAIProvider
from caw.protocols.types import ProviderMessage, ToolDefinition


class _DummyOpenAIClient:
    def __init__(self, response: Any | None = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.last_kwargs: dict[str, Any] | None = None

        class _Completions:
            def __init__(self, outer: _DummyOpenAIClient) -> None:
                self.outer = outer

            async def create(self, **kwargs: Any) -> Any:
                self.outer.last_kwargs = kwargs
                if self.outer.error is not None:
                    raise self.outer.error
                if kwargs.get("stream"):

                    async def _iter() -> Any:
                        yield SimpleNamespace(
                            choices=[
                                SimpleNamespace(
                                    delta=SimpleNamespace(content="hi"), finish_reason=None
                                )
                            ]
                        )
                        yield SimpleNamespace(
                            choices=[
                                SimpleNamespace(
                                    delta=SimpleNamespace(content=None), finish_reason="stop"
                                )
                            ]
                        )

                    return _iter()
                return self.outer.response

        class _Chat:
            def __init__(self, outer: _DummyOpenAIClient) -> None:
                self.completions = _Completions(outer)

        self.chat = _Chat(self)


def _openai_config() -> ProviderConfig:
    return ProviderConfig(type="openai", default_model="gpt", api_key_env="TEST_OPENAI_KEY")


def _compatible_config() -> ProviderConfig:
    return ProviderConfig(
        type="openai_compatible",
        default_model="llm",
        api_key_env="TEST_OPENAI_KEY",
        base_url="http://localhost:1234/v1",
    )


def test_provider_id_openai() -> None:
    provider = OpenAIProvider(provider_key="openai", config=_openai_config())
    assert provider.provider_id == "openai"


def test_provider_id_compatible() -> None:
    provider = OpenAIProvider(provider_key="local", config=_compatible_config())
    assert provider.provider_id == "local"


@pytest.mark.asyncio
async def test_complete_maps_response(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_OPENAI_KEY", "k")
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="ok", tool_calls=[]), finish_reason="stop"
            )
        ],
        usage=SimpleNamespace(prompt_tokens=3, completion_tokens=5),
        model="gpt-test",
    )
    provider = OpenAIProvider(provider_key="openai", config=_openai_config())
    provider._client = _DummyOpenAIClient(response=response)

    mapped = await provider.complete([ProviderMessage(role="user", content="x")], model="gpt-test")
    assert mapped.content == "ok"
    assert mapped.input_tokens == 3
    assert mapped.output_tokens == 5


def test_tool_format_mapping() -> None:
    provider = OpenAIProvider(provider_key="openai", config=_openai_config())
    mapped = provider._map_tool(
        ToolDefinition(
            name="search",
            description="Search docs",
            parameters={"type": "object", "properties": {}},
            permission_level="read",
            server_id="local",
        )
    )
    assert mapped["type"] == "function"
    assert mapped["function"]["name"] == "search"


@pytest.mark.asyncio
async def test_streaming(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_OPENAI_KEY", "k")
    provider = OpenAIProvider(provider_key="openai", config=_openai_config())
    provider._client = _DummyOpenAIClient()

    stream = await provider.complete(
        [ProviderMessage(role="user", content="x")], model="gpt", stream=True
    )
    chunks = [chunk async for chunk in stream]
    assert chunks[0].delta_text == "hi"
    assert chunks[-1].done is True


@pytest.mark.asyncio
async def test_error_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_OPENAI_KEY", "k")

    class _ErrError(Exception):
        status_code = 429

    provider = OpenAIProvider(provider_key="openai", config=_openai_config())
    provider._client = _DummyOpenAIClient(error=_ErrError("rate"))

    with pytest.raises(ProviderError) as exc:
        await provider.complete([ProviderMessage(role="user", content="x")], model="gpt")
    assert exc.value.code == "provider_rate_limit"


def test_custom_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_OPENAI_KEY", "k")
    provider = OpenAIProvider(provider_key="local", config=_compatible_config())
    client = provider._get_client()
    assert str(client.base_url) == "http://localhost:1234/v1/"
