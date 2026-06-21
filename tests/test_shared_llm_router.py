"""Tests for shared.llm.router — OpenRouterClient with mocked HTTP."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from workbench.shared.errors import EmbeddingError, RouterExhaustedError
from workbench.shared.llm.router import OpenRouterClient, _deduplicate_preserve_order


# ---- _deduplicate_preserve_order ----


def test_deduplicate_preserve_order():
    assert _deduplicate_preserve_order(["a", "b", "a", "c", "b"]) == ["a", "b", "c"]


def test_deduplicate_preserve_order_empty():
    assert _deduplicate_preserve_order([]) == []


def test_deduplicate_preserve_order_no_dupes():
    assert _deduplicate_preserve_order(["a", "b", "c"]) == ["a", "b", "c"]


# ---- OpenRouterClient.__init__ ----


def test_init_defaults():
    client = OpenRouterClient(api_key="sk-test")
    assert client._api_key == "sk-test"
    assert client._base_url == "https://openrouter.ai/api/v1"
    assert client._timeout == 120.0
    assert client._max_retries == 2
    assert client.models == ["deepseek/deepseek-v4-pro"]


def test_init_custom():
    client = OpenRouterClient(
        api_key="sk-test",
        base_url="https://custom.api/v1/",
        timeout=60.0,
        max_retries=3,
        default_model="model-a",
        fallback_models=["model-b", "model-a"],
    )
    assert client._base_url == "https://custom.api/v1"
    assert client._timeout == 60.0
    assert client.models == ["model-a", "model-b"]  # deduplicated


# ---- from_env ----


def test_from_env(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-env-test")
    client = OpenRouterClient.from_env()
    assert client._api_key == "sk-env-test"


def test_from_env_missing_raises(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="Missing"):
        OpenRouterClient.from_env()


# ---- chat_completion ----


@pytest.mark.asyncio
async def test_chat_completion_success():
    client = OpenRouterClient(api_key="sk-test", max_retries=1)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "Hello!"}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }

    with patch.object(client._client, "post", new_callable=AsyncMock, return_value=mock_response):
        result = await client.chat_completion(
            messages=[{"role": "user", "content": "Hi"}],
            model="test-model",
        )
    assert result == "Hello!"
    await client.close()


@pytest.mark.asyncio
async def test_chat_completion_exhausted():
    client = OpenRouterClient(api_key="sk-test", max_retries=1)

    with patch.object(
        client._client, "post", new_callable=AsyncMock,
        side_effect=httpx.ConnectError("fail"),
    ):
        with pytest.raises(RouterExhaustedError):
            await client.chat_completion(
                messages=[{"role": "user", "content": "Hi"}],
                model="test-model",
            )
    await client.close()


@pytest.mark.asyncio
async def test_chat_completion_malformed_response():
    client = OpenRouterClient(api_key="sk-test", max_retries=1)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {}  # missing "choices"

    with patch.object(client._client, "post", new_callable=AsyncMock, return_value=mock_response):
        with pytest.raises(RouterExhaustedError):
            await client.chat_completion(
                messages=[{"role": "user", "content": "Hi"}],
                model="test-model",
            )
    await client.close()


# ---- chat_completion_full ----


@pytest.mark.asyncio
async def test_chat_completion_full_success():
    client = OpenRouterClient(api_key="sk-test", max_retries=1)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "Full response"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }

    with patch.object(client._client, "post", new_callable=AsyncMock, return_value=mock_response):
        result = await client.chat_completion_full(
            messages=[{"role": "user", "content": "Hi"}],
            model="test-model",
        )
    assert result["text"] == "Full response"
    assert result["finish_reason"] == "stop"
    await client.close()


@pytest.mark.asyncio
async def test_chat_completion_full_with_tool_calls():
    client = OpenRouterClient(api_key="sk-test", max_retries=1)

    tool_calls = [{"id": "tc1", "function": {"name": "get_weather", "arguments": "{}"}}]
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "choices": [{"message": {"content": None, "tool_calls": tool_calls}, "finish_reason": "tool_calls"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }

    with patch.object(client._client, "post", new_callable=AsyncMock, return_value=mock_response):
        result = await client.chat_completion_full(
            messages=[{"role": "user", "content": "Weather?"}],
            model="test-model",
        )
    assert result["tool_calls"] == tool_calls
    assert result["finish_reason"] == "tool_calls"
    await client.close()


# ---- get_embedding ----


@pytest.mark.asyncio
async def test_get_embedding_success():
    client = OpenRouterClient(api_key="sk-test", embed_dim=3)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "data": [{"embedding": [0.1, 0.2, 0.3]}],
    }

    with patch.object(client._client, "post", new_callable=AsyncMock, return_value=mock_response):
        result = await client.get_embedding("test text")
    assert result == [0.1, 0.2, 0.3]
    await client.close()


@pytest.mark.asyncio
async def test_get_embedding_wrong_dimension():
    client = OpenRouterClient(api_key="sk-test", embed_dim=5)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "data": [{"embedding": [0.1, 0.2, 0.3]}],
    }

    with patch.object(client._client, "post", new_callable=AsyncMock, return_value=mock_response):
        with pytest.raises(EmbeddingError, match="Expected embedding dimension"):
            await client.get_embedding("test text")
    await client.close()


@pytest.mark.asyncio
async def test_get_embedding_api_error():
    client = OpenRouterClient(api_key="sk-test")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "error": {"message": "Rate limited"},
    }

    with patch.object(client._client, "post", new_callable=AsyncMock, return_value=mock_response):
        with pytest.raises(EmbeddingError, match="Rate limited"):
            await client.get_embedding("test text")
    await client.close()


@pytest.mark.asyncio
async def test_get_embedding_http_error():
    client = OpenRouterClient(api_key="sk-test")

    with patch.object(
        client._client, "post", new_callable=AsyncMock,
        side_effect=httpx.HTTPStatusError(
            "error", request=MagicMock(), response=MagicMock(status_code=500)
        ),
    ):
        with pytest.raises(EmbeddingError):
            await client.get_embedding("test text")
    await client.close()


# ---- get_embeddings_batch ----


@pytest.mark.asyncio
async def test_get_embeddings_batch():
    client = OpenRouterClient(api_key="sk-test", embed_dim=3)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "data": [{"embedding": [0.1, 0.2, 0.3]}],
    }

    with patch.object(client._client, "post", new_callable=AsyncMock, return_value=mock_response):
        result = await client.get_embeddings_batch(["text1", "text2"])
    assert len(result) == 2
    await client.close()


@pytest.mark.asyncio
async def test_get_embeddings_batch_empty():
    client = OpenRouterClient(api_key="sk-test")
    result = await client.get_embeddings_batch([])
    assert result == []
    await client.close()


# ---- close / context manager ----


@pytest.mark.asyncio
async def test_close():
    client = OpenRouterClient(api_key="sk-test")
    with patch.object(client._client, "aclose", new_callable=AsyncMock) as mock_close:
        await client.close()
    mock_close.assert_awaited_once()


@pytest.mark.asyncio
async def test_async_context_manager():
    client = OpenRouterClient(api_key="sk-test")
    with patch.object(client._client, "aclose", new_callable=AsyncMock):
        async with client as c:
            assert c is client


# ---- _log_token_usage / _log_failure / _log_malformed ----


def test_log_token_usage_with_usage(caplog):
    import logging
    with caplog.at_level(logging.INFO, logger="workbench.shared.llm.router"):
        OpenRouterClient._log_token_usage(
            {"usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}},
            "test-model",
            0.5,
        )
    assert any("LLM tokens" in r.message for r in caplog.records)


def test_log_token_usage_no_usage(caplog):
    import logging
    with caplog.at_level(logging.INFO, logger="workbench.shared.llm.router"):
        OpenRouterClient._log_token_usage({}, "test-model", 0.5)
    assert not any("LLM tokens" in r.message for r in caplog.records)


def test_log_failure(caplog):
    import logging
    with caplog.at_level(logging.WARNING, logger="workbench.shared.llm.router"):
        exc = httpx.ConnectError("fail")
        OpenRouterClient._log_failure(exc, "test-model", 1, 2, 0.0)
    assert any("FAILED" in r.message for r in caplog.records)


def test_log_failure_http_status(caplog):
    import logging
    with caplog.at_level(logging.WARNING, logger="workbench.shared.llm.router"):
        mock_resp = MagicMock(status_code=429)
        exc = httpx.HTTPStatusError("rate limited", request=MagicMock(), response=mock_resp)
        OpenRouterClient._log_failure(exc, "test-model", 1, 2, 0.0)
    assert any("HTTP 429" in r.message for r in caplog.records)


def test_log_malformed(caplog):
    import logging
    with caplog.at_level(logging.WARNING, logger="workbench.shared.llm.router"):
        OpenRouterClient._log_malformed(KeyError("key"), "test-model", 1, 2, 0.0)
    assert any("Malformed" in r.message for r in caplog.records)
