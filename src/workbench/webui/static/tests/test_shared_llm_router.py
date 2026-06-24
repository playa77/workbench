"""Tests for shared.llm.router — OpenRouterClient with mocked HTTP."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from workbench.shared.errors import EmbeddingError, RouterExhaustedError
from workbench.shared.llm.router import (
    OpenRouterClient,
    RateLimitExceededError,
    _deduplicate_preserve_order,
)


# ---- helpers ----

def _streaming_resp(lines: list[str]) -> MagicMock:
    """Build a mock streaming response that yields *lines* via aiter_lines()."""
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.aiter_lines = MagicMock(return_value=AsyncMock())
    resp.aiter_lines.return_value.__aiter__ = lambda _: _aiter_over(lines)
    resp.aiter_lines.return_value.__anext__ = _make_anext(lines)
    return resp


async def _aiter_over(items):
    for item in items:
        yield item


def _make_anext(items):
    it = iter(items)

    async def anext():
        try:
            return next(it)
        except StopIteration:
            raise StopAsyncIteration

    return anext


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


# ---- _check_rate_limit / RateLimitExceededError ----


@patch("workbench.shared.llm.router._get_rate_limiter")
@pytest.mark.asyncio
async def test_check_rate_limit_blocks(mock_get_limiter):
    """RateLimitExceededError raised when rate limiter returns False."""
    limiter = AsyncMock()
    limiter.check.return_value = False
    mock_get_limiter.return_value = limiter

    client = OpenRouterClient(api_key="sk-test")
    with pytest.raises(RateLimitExceededError, match="rate limit"):
        await client.chat_completion(
            messages=[{"role": "user", "content": "Hi"}],
            model="test",
        )
    await client.close()


@patch("workbench.shared.llm.router._get_rate_limiter")
@pytest.mark.asyncio
async def test_check_rate_limit_full_blocks(mock_get_limiter):
    """Rate limit blocks chat_completion_full."""
    limiter = AsyncMock()
    limiter.check.return_value = False
    mock_get_limiter.return_value = limiter

    client = OpenRouterClient(api_key="sk-test")
    with pytest.raises(RateLimitExceededError, match="rate limit"):
        await client.chat_completion_full(
            messages=[{"role": "user", "content": "Hi"}],
            model="test",
        )
    await client.close()


@patch("workbench.shared.llm.router._get_rate_limiter")
@pytest.mark.asyncio
async def test_check_rate_limit_stream_blocks(mock_get_limiter):
    """Rate limit blocks chat_completion_stream."""
    limiter = AsyncMock()
    limiter.check.return_value = False
    mock_get_limiter.return_value = limiter

    client = OpenRouterClient(api_key="sk-test")
    with pytest.raises(RateLimitExceededError, match="rate limit"):
        async for _ in client.chat_completion_stream(
            messages=[{"role": "user", "content": "Hi"}],
            model="test",
        ):
            pass
    await client.close()


@patch("workbench.shared.llm.router._get_rate_limiter")
@pytest.mark.asyncio
async def test_rate_limit_logged_in_embeddings_batch(mock_get_limiter):
    """Rate limit in get_embeddings_batch also raises."""
    limiter = AsyncMock()
    limiter.check.return_value = False
    mock_get_limiter.return_value = limiter

    client = OpenRouterClient(api_key="sk-test")
    with pytest.raises(RateLimitExceededError, match="rate limit"):
        await client.get_embeddings_batch(["text"])
    await client.close()


# ---- chat_completion — additional coverage ----


@pytest.mark.asyncio
async def test_chat_completion_with_models_override():
    """chat_completion with explicit models list."""
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
            models=["custom-a", "custom-b"],
        )
    assert result == "Hello!"
    await client.close()


@pytest.mark.asyncio
async def test_chat_completion_default_models():
    """chat_completion with no model or models override — uses self.models."""
    client = OpenRouterClient(api_key="sk-test", max_retries=1, default_model="default-model")

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
        )
    assert result == "Hello!"
    await client.close()


@pytest.mark.asyncio
async def test_chat_completion_retry_then_success():
    """First attempt fails with HTTPStatusError, retry succeeds."""
    client = OpenRouterClient(api_key="sk-test", max_retries=2)

    mock_success = MagicMock()
    mock_success.status_code = 200
    mock_success.raise_for_status = MagicMock()
    mock_success.json.return_value = {
        "choices": [{"message": {"content": "Retry OK!"}}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
    }

    mock_fail = MagicMock()
    mock_fail.raise_for_status.side_effect = httpx.HTTPStatusError(
        "error", request=MagicMock(), response=MagicMock(status_code=502)
    )

    with patch.object(
        client._client, "post", new_callable=AsyncMock,
        side_effect=[mock_fail, mock_success],
    ):
        result = await client.chat_completion(
            messages=[{"role": "user", "content": "Hi"}],
            model="test-model",
        )
    assert result == "Retry OK!"
    await client.close()


@pytest.mark.asyncio
async def test_chat_completion_retry_malformed_then_success():
    """First attempt malformed (IndexError), retry succeeds."""
    client = OpenRouterClient(api_key="sk-test", max_retries=2)

    mock_success = MagicMock()
    mock_success.status_code = 200
    mock_success.raise_for_status = MagicMock()
    mock_success.json.return_value = {
        "choices": [{"message": {"content": "Retry OK!"}}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
    }

    mock_bad = MagicMock()
    mock_bad.status_code = 200
    mock_bad.raise_for_status = MagicMock()
    mock_bad.json.return_value = {"choices": []}  # IndexError on [0]

    with patch.object(
        client._client, "post", new_callable=AsyncMock,
        side_effect=[mock_bad, mock_success],
    ):
        result = await client.chat_completion(
            messages=[{"role": "user", "content": "Hi"}],
            model="test-model",
        )
    assert result == "Retry OK!"
    await client.close()


@pytest.mark.asyncio
async def test_chat_completion_fallback_chain():
    """Primary model exhausted, fallback model succeeds."""
    client = OpenRouterClient(
        api_key="sk-test",
        max_retries=1,
        default_model="model-a",
        fallback_models=["model-b"],
    )

    mock_success = MagicMock()
    mock_success.status_code = 200
    mock_success.raise_for_status = MagicMock()
    mock_success.json.return_value = {
        "choices": [{"message": {"content": "Fallback OK!"}}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
    }

    with patch.object(
        client._client, "post", new_callable=AsyncMock,
        side_effect=httpx.ConnectError("fail") if True else mock_success,
    ) as mock_post:
        # Use side_effect that fails for model-a, succeeds for model-b
        # We need to control the behavior per-call
        mock_post.side_effect = [
            httpx.ConnectError("fail"),  # model-a attempt 1
            mock_success,  # model-b attempt 1
        ]
        result = await client.chat_completion(
            messages=[{"role": "user", "content": "Hi"}],
            models=["model-a", "model-b"],
        )
    assert result == "Fallback OK!"
    await client.close()


@pytest.mark.asyncio
async def test_chat_completion_timeout_override():
    """chat_completion with per-call timeout and max_retries overrides."""
    client = OpenRouterClient(api_key="sk-test", max_retries=3)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "OK"}}],
        "usage": {},
    }

    with patch.object(client._client, "post", new_callable=AsyncMock, return_value=mock_response):
        result = await client.chat_completion(
            messages=[{"role": "user", "content": "Hi"}],
            model="test-model",
            timeout=30.0,
            max_retries=1,
        )
    assert result == "OK"
    await client.close()


# ---- chat_completion_full — additional coverage ----


@pytest.mark.asyncio
async def test_chat_completion_full_with_tools_and_tool_choice():
    """chat_completion_full with tools and tool_choice parameters."""
    client = OpenRouterClient(api_key="sk-test", max_retries=1)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
            "choices": [{
                "message": {
                    "content": "Using tool",
                    "tool_calls": [{"id": "tc1", "function": {"name": "fn", "arguments": "{}"}}],
                },
                "finish_reason": "tool_calls",
            }],
            "usage": {},
        }

    with patch.object(client._client, "post", new_callable=AsyncMock, return_value=mock_response):
        result = await client.chat_completion_full(
            messages=[{"role": "user", "content": "Hi"}],
            model="test-model",
            tools=[{"type": "function", "function": {"name": "fn"}}],
            tool_choice={"type": "function", "function": {"name": "fn"}},
        )
    assert result["text"] == "Using tool"
    assert result["tool_calls"] is not None
    await client.close()


@pytest.mark.asyncio
async def test_chat_completion_full_with_models_override():
    """chat_completion_full with explicit models list."""
    client = OpenRouterClient(api_key="sk-test", max_retries=1)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "Full"}, "finish_reason": "stop"}],
        "usage": {},
    }

    with patch.object(client._client, "post", new_callable=AsyncMock, return_value=mock_response):
        result = await client.chat_completion_full(
            messages=[{"role": "user", "content": "Hi"}],
            models=["custom-a", "custom-b"],
        )
    assert result["text"] == "Full"
    await client.close()


@pytest.mark.asyncio
async def test_chat_completion_full_default_models():
    """chat_completion_full with no model override — uses self.models."""
    client = OpenRouterClient(api_key="sk-test", max_retries=1, default_model="def-m")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "Default"}, "finish_reason": "stop"}],
        "usage": {},
    }

    with patch.object(client._client, "post", new_callable=AsyncMock, return_value=mock_response):
        result = await client.chat_completion_full(
            messages=[{"role": "user", "content": "Hi"}],
        )
    assert result["text"] == "Default"
    await client.close()


@pytest.mark.asyncio
async def test_chat_completion_full_http_retry():
    """HTTP error on first attempt, success on retry."""
    client = OpenRouterClient(api_key="sk-test", max_retries=2)

    mock_ok = MagicMock()
    mock_ok.status_code = 200
    mock_ok.raise_for_status = MagicMock()
    mock_ok.json.return_value = {
        "choices": [{"message": {"content": "After retry"}, "finish_reason": "stop"}],
        "usage": {},
    }

    with patch.object(
        client._client, "post", new_callable=AsyncMock,
        side_effect=[
            httpx.TimeoutException("timeout"),
            mock_ok,
        ],
    ):
        result = await client.chat_completion_full(
            messages=[{"role": "user", "content": "Hi"}],
            model="test-model",
        )
    assert result["text"] == "After retry"
    await client.close()


@pytest.mark.asyncio
async def test_chat_completion_full_json_decode_error():
    """Malformed JSON in response triggers retry."""
    client = OpenRouterClient(api_key="sk-test", max_retries=2)

    mock_ok = MagicMock()
    mock_ok.status_code = 200
    mock_ok.raise_for_status = MagicMock()
    mock_ok.json.return_value = {
        "choices": [{"message": {"content": "OK"}, "finish_reason": "stop"}],
        "usage": {},
    }

    mock_bad = MagicMock()
    mock_bad.status_code = 200
    mock_bad.raise_for_status = MagicMock()
    mock_bad.json.side_effect = json.JSONDecodeError("bad json", "", 0)

    with patch.object(
        client._client, "post", new_callable=AsyncMock,
        side_effect=[mock_bad, mock_ok],
    ):
        result = await client.chat_completion_full(
            messages=[{"role": "user", "content": "Hi"}],
            model="test-model",
        )
    assert result["text"] == "OK"
    await client.close()


@pytest.mark.asyncio
async def test_chat_completion_full_exhaustion():
    """All retries on single model exhausted."""
    client = OpenRouterClient(api_key="sk-test", max_retries=2)

    with patch.object(
        client._client, "post", new_callable=AsyncMock,
        side_effect=httpx.ConnectError("fail"),
    ):
        with pytest.raises(RouterExhaustedError):
            await client.chat_completion_full(
                messages=[{"role": "user", "content": "Hi"}],
                model="test-model",
            )
    await client.close()


@pytest.mark.asyncio
async def test_chat_completion_full_fallback_chain():
    """Primary model exhausted, fallback model succeeds in full completions."""
    client = OpenRouterClient(api_key="sk-test", max_retries=1)

    mock_ok = MagicMock()
    mock_ok.status_code = 200
    mock_ok.raise_for_status = MagicMock()
    mock_ok.json.return_value = {
        "choices": [{"message": {"content": "Fallback"}, "finish_reason": "stop"}],
        "usage": {},
    }

    with patch.object(
        client._client, "post", new_callable=AsyncMock,
        side_effect=[
            httpx.ConnectError("fail"),  # model-a
            mock_ok,  # model-b
        ],
    ):
        result = await client.chat_completion_full(
            messages=[{"role": "user", "content": "Hi"}],
            models=["model-a", "model-b"],
        )
    assert result["text"] == "Fallback"
    await client.close()


@pytest.mark.asyncio
async def test_chat_completion_full_key_error_retry():
    """KeyError parsing response triggers retry."""
    client = OpenRouterClient(api_key="sk-test", max_retries=2)

    mock_ok = MagicMock()
    mock_ok.status_code = 200
    mock_ok.raise_for_status = MagicMock()
    mock_ok.json.return_value = {
        "choices": [{"message": {"content": "OK"}, "finish_reason": "stop"}],
        "usage": {},
    }

    mock_bad = MagicMock()
    mock_bad.status_code = 200
    mock_bad.raise_for_status = MagicMock()
    mock_bad.json.return_value = {"no_choices": True}  # KeyError

    with patch.object(
        client._client, "post", new_callable=AsyncMock,
        side_effect=[mock_bad, mock_ok],
    ):
        result = await client.chat_completion_full(
            messages=[{"role": "user", "content": "Hi"}],
            model="test-model",
        )
    assert result["text"] == "OK"
    await client.close()


# ---- chat_completion_stream ----


@pytest.mark.asyncio
async def test_stream_success():
    """Basic streaming with two content tokens."""
    client = OpenRouterClient(api_key="sk-test", max_retries=1)
    sse_lines = [
        'data: {"choices":[{"delta":{"content":"Hello"}}]}',
        'data: {"choices":[{"delta":{"content":" world"}}]}',
        "data: [DONE]",
    ]
    mock_resp = _streaming_resp(sse_lines)

    with patch.object(
        client._client, "stream", new_callable=MagicMock
    ) as mock_stream:
        mock_stream.return_value.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_stream.return_value.__aexit__ = AsyncMock(return_value=None)

        tokens = []
        async for token in client.chat_completion_stream(
            messages=[{"role": "user", "content": "Hi"}],
            model="test-model",
        ):
            tokens.append(token)

    assert tokens == ["Hello", " world"]
    await client.close()


@pytest.mark.asyncio
async def test_stream_skips_empty_delta():
    """Streaming lines with empty or missing delta.content are skipped."""
    client = OpenRouterClient(api_key="sk-test", max_retries=1)
    sse_lines = [
        'data: {"choices":[{"delta":{"content":""}}]}',
        'data: {"choices":[{"delta":{}}]}',
        'data: {"choices":[{"delta":{"content":"real"}}]}',
        "data: [DONE]",
    ]
    mock_resp = _streaming_resp(sse_lines)

    with patch.object(
        client._client, "stream", new_callable=MagicMock
    ) as mock_stream:
        mock_stream.return_value.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_stream.return_value.__aexit__ = AsyncMock(return_value=None)

        tokens = []
        async for token in client.chat_completion_stream(
            messages=[{"role": "user", "content": "Hi"}],
            model="test-model",
        ):
            tokens.append(token)

    assert tokens == ["real"]
    await client.close()


@pytest.mark.asyncio
async def test_stream_ignores_bad_json():
    """Lines with invalid JSON are skipped."""
    client = OpenRouterClient(api_key="sk-test", max_retries=1)
    sse_lines = [
        "data: not-json",
        'data: {"choices":[{"delta":{"content":"ok"}}]}',
        "data: [DONE]",
    ]
    mock_resp = _streaming_resp(sse_lines)

    with patch.object(
        client._client, "stream", new_callable=MagicMock
    ) as mock_stream:
        mock_stream.return_value.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_stream.return_value.__aexit__ = AsyncMock(return_value=None)

        tokens = []
        async for token in client.chat_completion_stream(
            messages=[{"role": "user", "content": "Hi"}],
            model="test-model",
        ):
            tokens.append(token)

    assert tokens == ["ok"]
    await client.close()


@pytest.mark.asyncio
async def test_stream_skips_non_data_lines():
    """Lines without 'data: ' prefix and blank lines are skipped."""
    client = OpenRouterClient(api_key="sk-test", max_retries=1)
    sse_lines = [
        "",
        ": comment",
        'data: {"choices":[{"delta":{"content":"only"}}]}',
        "data: [DONE]",
    ]
    mock_resp = _streaming_resp(sse_lines)

    with patch.object(
        client._client, "stream", new_callable=MagicMock
    ) as mock_stream:
        mock_stream.return_value.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_stream.return_value.__aexit__ = AsyncMock(return_value=None)

        tokens = []
        async for token in client.chat_completion_stream(
            messages=[{"role": "user", "content": "Hi"}],
            model="test-model",
        ):
            tokens.append(token)

    assert tokens == ["only"]
    await client.close()


@pytest.mark.asyncio
async def test_stream_http_error():
    """HTTP error during streaming triggers retry then exhaustion."""
    client = OpenRouterClient(api_key="sk-test", max_retries=1)

    with patch.object(
        client._client, "stream", new_callable=MagicMock
    ) as mock_stream:
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=MagicMock(status_code=429)
        )
        mock_stream.return_value.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_stream.return_value.__aexit__ = AsyncMock(return_value=None)

        with pytest.raises(RouterExhaustedError):
            async for _ in client.chat_completion_stream(
                messages=[{"role": "user", "content": "Hi"}],
                model="test-model",
            ):
                pass
    await client.close()


@pytest.mark.asyncio
async def test_stream_retry_then_success():
    """Streaming retries after HTTP error."""
    client = OpenRouterClient(api_key="sk-test", max_retries=2)

    sse_lines = [
        'data: {"choices":[{"delta":{"content":"retried"}}]}',
        "data: [DONE]",
    ]
    good_resp = _streaming_resp(sse_lines)

    bad_resp = MagicMock()
    bad_resp.raise_for_status.side_effect = httpx.ConnectError("fail")

    with patch.object(
        client._client, "stream", new_callable=MagicMock
    ) as mock_stream:
        mock_stream.return_value.__aenter__ = AsyncMock(
            side_effect=[bad_resp, good_resp]
        )
        mock_stream.return_value.__aexit__ = AsyncMock(return_value=None)

        tokens = []
        async for token in client.chat_completion_stream(
            messages=[{"role": "user", "content": "Hi"}],
            model="test-model",
        ):
            tokens.append(token)

    assert tokens == ["retried"]
    await client.close()


@pytest.mark.asyncio
async def test_stream_exhaustion():
    """All retries exhausted in streaming."""
    client = OpenRouterClient(api_key="sk-test", max_retries=2)

    with patch.object(
        client._client, "stream", new_callable=MagicMock
    ) as mock_stream:
        bad_resp = MagicMock()
        bad_resp.raise_for_status.side_effect = httpx.TimeoutException("timeout")
        mock_stream.return_value.__aenter__ = AsyncMock(return_value=bad_resp)
        mock_stream.return_value.__aexit__ = AsyncMock(return_value=None)

        with pytest.raises(RouterExhaustedError):
            async for _ in client.chat_completion_stream(
                messages=[{"role": "user", "content": "Hi"}],
                model="test-model",
            ):
                pass
    await client.close()


@pytest.mark.asyncio
async def test_stream_with_models_override():
    """Streaming with explicit models list."""
    client = OpenRouterClient(api_key="sk-test", max_retries=1)

    sse_lines = [
        'data: {"choices":[{"delta":{"content":"hi"}}]}',
        "data: [DONE]",
    ]
    mock_resp = _streaming_resp(sse_lines)

    with patch.object(
        client._client, "stream", new_callable=MagicMock
    ) as mock_stream:
        mock_stream.return_value.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_stream.return_value.__aexit__ = AsyncMock(return_value=None)

        tokens = []
        async for token in client.chat_completion_stream(
            messages=[{"role": "user", "content": "Hi"}],
            models=["custom-a", "custom-b"],
        ):
            tokens.append(token)

    assert tokens == ["hi"]
    await client.close()


@pytest.mark.asyncio
async def test_stream_default_models():
    """Streaming with no model override — uses self.models."""
    client = OpenRouterClient(api_key="sk-test", max_retries=1, default_model="def-m")

    sse_lines = [
        'data: {"choices":[{"delta":{"content":"ok"}}]}',
        "data: [DONE]",
    ]
    mock_resp = _streaming_resp(sse_lines)

    with patch.object(
        client._client, "stream", new_callable=MagicMock
    ) as mock_stream:
        mock_stream.return_value.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_stream.return_value.__aexit__ = AsyncMock(return_value=None)

        tokens = []
        async for token in client.chat_completion_stream(
            messages=[{"role": "user", "content": "Hi"}],
        ):
            tokens.append(token)

    assert tokens == ["ok"]
    await client.close()


@pytest.mark.asyncio
async def test_stream_fallback_chain():
    """Streaming: primary model fails, fallback succeeds."""
    client = OpenRouterClient(api_key="sk-test", max_retries=1)

    sse_lines = [
        'data: {"choices":[{"delta":{"content":"fb"}}]}',
        "data: [DONE]",
    ]
    good_resp = _streaming_resp(sse_lines)
    bad_resp = MagicMock()
    bad_resp.raise_for_status.side_effect = httpx.ConnectError("fail")

    with patch.object(
        client._client, "stream", new_callable=MagicMock
    ) as mock_stream:
        mock_stream.return_value.__aenter__ = AsyncMock(
            side_effect=[bad_resp, good_resp]
        )
        mock_stream.return_value.__aexit__ = AsyncMock(return_value=None)

        tokens = []
        async for token in client.chat_completion_stream(
            messages=[{"role": "user", "content": "Hi"}],
            models=["model-a", "model-b"],
        ):
            tokens.append(token)

    assert tokens == ["fb"]
    await client.close()


@pytest.mark.asyncio
async def test_stream_timeout_override():
    """Streaming with per-call timeout and max_retries override."""
    client = OpenRouterClient(api_key="sk-test", max_retries=3)

    sse_lines = [
        'data: {"choices":[{"delta":{"content":"ok"}}]}',
        "data: [DONE]",
    ]
    mock_resp = _streaming_resp(sse_lines)

    with patch.object(
        client._client, "stream", new_callable=MagicMock
    ) as mock_stream:
        mock_stream.return_value.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_stream.return_value.__aexit__ = AsyncMock(return_value=None)

        tokens = []
        async for token in client.chat_completion_stream(
            messages=[{"role": "user", "content": "Hi"}],
            model="test-model",
            timeout=30.0,
            max_retries=1,
        ):
            tokens.append(token)

    assert tokens == ["ok"]
    await client.close()


# ---- get_embedding — additional coverage ----


@pytest.mark.asyncio
async def test_get_embedding_malformed_response_key_error():
    """Response missing 'data' key triggers KeyError handler."""
    client = OpenRouterClient(api_key="sk-test")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"unexpected": True}

    with patch.object(client._client, "post", new_callable=AsyncMock, return_value=mock_response):
        with pytest.raises(EmbeddingError, match="Malformed embedding response"):
            await client.get_embedding("test text")
    await client.close()


@pytest.mark.asyncio
async def test_get_embedding_malformed_response_index_error():
    """Empty data array triggers IndexError handler."""
    client = OpenRouterClient(api_key="sk-test")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"data": []}

    with patch.object(client._client, "post", new_callable=AsyncMock, return_value=mock_response):
        with pytest.raises(EmbeddingError, match="Malformed embedding response"):
            await client.get_embedding("test text")
    await client.close()


@pytest.mark.asyncio
async def test_get_embedding_malformed_str_body_fallback():
    """KeyError handler when str(body) itself raises — hits <unavailable> branch."""
    client = OpenRouterClient(api_key="sk-test")

    class BadStrDict(dict):
        def __str__(self):
            raise RuntimeError("cannot str")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = BadStrDict({"unexpected": True})

    with patch.object(client._client, "post", new_callable=AsyncMock, return_value=mock_response):
        with pytest.raises(EmbeddingError, match="Malformed embedding response"):
            await client.get_embedding("test text")
    await client.close()


@pytest.mark.asyncio
async def test_get_embedding_timeout():
    """TimeoutException in embedding."""
    client = OpenRouterClient(api_key="sk-test")

    with patch.object(
        client._client, "post", new_callable=AsyncMock,
        side_effect=httpx.TimeoutException("timeout"),
    ):
        with pytest.raises(EmbeddingError):
            await client.get_embedding("test text")
    await client.close()


@pytest.mark.asyncio
async def test_get_embedding_custom_model():
    """Embedding with custom model override."""
    client = OpenRouterClient(api_key="sk-test", embed_dim=2)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "data": [{"embedding": [0.5, 0.5]}],
    }

    with patch.object(client._client, "post", new_callable=AsyncMock, return_value=mock_response):
        result = await client.get_embedding("test", model="custom-embed-model")
    assert result == [0.5, 0.5]
    await client.close()


# ---- get_embeddings_batch — additional coverage ----


@pytest.mark.asyncio
async def test_get_embeddings_batch_one_fails():
    """One embedding fails — exception propagates from gather."""
    client = OpenRouterClient(api_key="sk-test", embed_dim=2)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "data": [{"embedding": [0.1, 0.2]}],
    }

    with patch.object(
        client._client, "post", new_callable=AsyncMock,
        side_effect=[
            mock_response,
            httpx.HTTPStatusError(
                "error", request=MagicMock(), response=MagicMock(status_code=500)
            ),
        ],
    ):
        with pytest.raises(EmbeddingError):
            await client.get_embeddings_batch(["text1", "text2"])
    await client.close()


# ---- close — edge cases ----


@pytest.mark.asyncio
async def test_close_not_owned():
    """When _owned is False, close does nothing."""
    client = OpenRouterClient(api_key="sk-test")
    client._owned = False
    with patch.object(client._client, "aclose", new_callable=AsyncMock) as mock_close:
        await client.close()
    mock_close.assert_not_called()
    await client.close()


# ---- from_env edge cases ----


def test_from_env_custom_env_var(monkeypatch):
    monkeypatch.setenv("CUSTOM_KEY", "sk-custom")
    client = OpenRouterClient.from_env(env_var="CUSTOM_KEY")
    assert client._api_key == "sk-custom"


# ---- _get_rate_limiter lazy init ----


@patch("workbench.shared.llm.router._get_rate_limiter")
@pytest.mark.asyncio
async def test_get_rate_limiter_returns_limiter(mock_get_limiter):
    """_get_rate_limiter is called from _check_rate_limit."""
    from workbench.shared.llm.router import _get_rate_limiter as get_rl
    limiter = AsyncMock()
    limiter.check.return_value = True
    mock_get_limiter.return_value = limiter

    client = OpenRouterClient(api_key="sk-test")
    # Trigger _check_rate_limit via a chat call
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "OK"}}],
        "usage": {},
    }

    with patch.object(client._client, "post", new_callable=AsyncMock, return_value=mock_response):
        result = await client.chat_completion(
            messages=[{"role": "user", "content": "Hi"}],
            model="test",
        )
    assert result == "OK"
    mock_get_limiter.assert_called()
    await client.close()
