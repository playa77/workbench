"""Canonical OpenRouter LLM client with fallback chain, embeddings, and streaming.

This is the single LLM client implementation for all agents and services,
adapted from citizen's feature-rich router, enhanced with from_env() factory
and token usage logging.
"""

from __future__ import annotations

import asyncio
import json as _json
import logging
import os
import time
from collections.abc import AsyncGenerator, Sequence
from typing import Any

import httpx

from workbench.shared.errors import EmbeddingError, RouterExhaustedError

logger = logging.getLogger(__name__)


def _deduplicate_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


class OpenRouterClient:
    """HTTP client for the OpenRouter API with retry / fallback logic.

    Supports:
    - Multi-model fallback chain (primary -> fallback_1 -> fallback_2)
    - Per-call model overrides
    - Per-call timeout overrides
    - Per-call max_retries overrides
    - Streaming (SSE) chat completions
    - Single and batch embeddings with dimension validation
    - Configurable API base URL
    - Token usage logging
    - Async context manager support
    - ``from_env()`` factory for quick setup

    Parameters
    ----------
    api_key:
        OpenRouter API key.
    base_url:
        Base URL for the OpenRouter API.
    timeout:
        Request timeout in seconds.
    max_retries:
        Maximum retry attempts per model before falling through.
    default_model:
        Default model identifier.
    fallback_models:
        Additional fallback models (deduplicated with default_model).
    embed_model:
        Default embedding model.
    embed_dim:
        Expected embedding vector dimension.
    referer:
        HTTP-Referer header value.
    title:
        X-Title header value.
    """

    _CHAT_PATH = "/chat/completions"
    _EMBED_PATH = "/embeddings"

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://openrouter.ai/api/v1",
        timeout: float = 120.0,
        max_retries: int = 2,
        default_model: str = "deepseek/deepseek-v4-pro",
        fallback_models: list[str] | None = None,
        embed_model: str = "openai/text-embedding-3-small",
        embed_dim: int = 1536,
        referer: str = "https://workbench.local",
        title: str = "Workbench",
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._max_retries = max_retries
        self._embed_model = embed_model
        self._embed_dim = embed_dim
        self._referer = referer
        self._title = title

        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(timeout),
            headers={
                "Authorization": f"Bearer {api_key}",
                "HTTP-Referer": referer,
                "X-Title": title,
                "Content-Type": "application/json",
            },
        )
        self._owned = True

        chain = [default_model]
        if fallback_models:
            chain.extend(fallback_models)
        self.models: list[str] = _deduplicate_preserve_order(chain)

    @classmethod
    def from_env(
        cls,
        env_var: str = "OPENROUTER_API_KEY",
        base_url: str = "https://openrouter.ai/api/v1",
        timeout: float = 120.0,
        max_retries: int = 2,
        default_model: str = "deepseek/deepseek-v4-pro",
        fallback_models: list[str] | None = None,
        embed_model: str = "openai/text-embedding-3-small",
        embed_dim: int = 1536,
        referer: str = "https://workbench.local",
        title: str = "Workbench",
    ) -> OpenRouterClient:
        api_key = os.environ.get(env_var, "")
        if not api_key:
            raise RuntimeError(f"Missing {env_var}")
        return cls(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            default_model=default_model,
            fallback_models=fallback_models,
            embed_model=embed_model,
            embed_dim=embed_dim,
            referer=referer,
            title=title,
        )

    # ------------------------------------------------------------------
    # Public API — chat completions
    # ------------------------------------------------------------------

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.1,
        model: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        models: list[str] | None = None,
    ) -> str:
        """Return the assistant's final text response or raise on exhaustion.

        Args:
            messages: OpenAI-style message history.
            temperature: Sampling temperature (low = deterministic).
            model: Override the fallback chain with a single specific model.
            timeout: Per-call HTTP timeout in seconds.
            max_retries: Maximum attempts per model.
            models: Explicit fallback chain (deduplicated, order-preserving).

        Returns:
            The parsed ``content`` string from the response.

        Raises:
            RouterExhaustedError: If every model / retry attempt fails.
        """
        effective_max_retries = max_retries if max_retries is not None else self._max_retries
        timeout_config = httpx.Timeout(timeout) if timeout is not None else None

        if models is not None:
            effective_models = _deduplicate_preserve_order(models)
        elif model is not None:
            effective_models = [model]
        else:
            effective_models = self.models

        for current_model in effective_models:
            for attempt in range(1, effective_max_retries + 1):
                req_start = time.monotonic()
                try:
                    payload: dict[str, Any] = {
                        "model": current_model,
                        "messages": messages,
                        "temperature": temperature,
                    }
                    msg_chars = sum(len(m.get("content", "")) for m in messages)
                    logger.info(
                        "chat_completion -> sending (model=%s, attempt=%d/%d, msg_chars=%d)",
                        current_model, attempt, effective_max_retries, msg_chars,
                    )
                    resp = await self._client.post(
                        self._CHAT_PATH,
                        json=payload,
                        timeout=timeout_config,
                    )
                    elapsed = time.monotonic() - req_start
                    resp.raise_for_status()
                    body = resp.json()
                    content: str = body["choices"][0]["message"]["content"]
                    self._log_token_usage(body, current_model, elapsed)
                    logger.info(
                        "chat_completion OK (model=%s, attempt=%d/%d, elapsed=%.2fs, "
                        "prompt_chars=%d, response_chars=%d)",
                        current_model, attempt, effective_max_retries,
                        elapsed, msg_chars, len(content),
                    )
                    return content
                except (httpx.HTTPStatusError, httpx.TimeoutException, httpx.ConnectError) as exc:
                    self._log_failure(exc, current_model, attempt, effective_max_retries, req_start)
                    if attempt < effective_max_retries:
                        await asyncio.sleep(2 ** (attempt - 1))
                    continue
                except (KeyError, IndexError) as exc:
                    self._log_malformed(
                        exc, current_model, attempt, effective_max_retries, req_start
                    )
                    if attempt < effective_max_retries:
                        await asyncio.sleep(2 ** (attempt - 1))
                    continue

            logger.info(
                "Model %s exhausted after %d retries, trying next fallback.",
                current_model, effective_max_retries,
            )

        raise RouterExhaustedError(f"All models exhausted: {effective_models}")

    async def chat_completion_full(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float = 0.1,
        model: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        models: list[str] | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Full chat completion returning text, tool-calls, usage, finish-reason.

        Supports OpenAI-compatible function calling via the ``tools`` parameter.
        Message roles can include ``"tool"`` for sending function call results.

        Returns a dict with keys:
        - ``text`` (str): The assistant's text content (empty if tool_calls present).
        - ``tool_calls`` (list[dict] | None): Function call requests, if any.
        - ``usage`` (dict): ``{prompt_tokens, completion_tokens, total_tokens}``.
        - ``finish_reason`` (str): Reason the model stopped (e.g. ``"stop"``, ``"tool_calls"``).
        """
        effective_max_retries = max_retries if max_retries is not None else self._max_retries
        timeout_config = httpx.Timeout(timeout) if timeout is not None else None

        if models is not None:
            effective_models = _deduplicate_preserve_order(models)
        elif model is not None:
            effective_models = [model]
        else:
            effective_models = self.models

        for current_model in effective_models:
            for attempt in range(1, effective_max_retries + 1):
                req_start = time.monotonic()
                try:
                    payload: dict[str, Any] = {
                        "model": current_model,
                        "messages": messages,
                        "temperature": temperature,
                    }
                    if tools:
                        payload["tools"] = tools
                    if tool_choice is not None:
                        payload["tool_choice"] = tool_choice

                    msg_chars = sum(len(str(m.get("content", ""))) for m in messages)
                    logger.info(
                        "chat_completion_full -> sending "
                        "(model=%s, attempt=%d/%d, msg_chars=%d, tools=%d)",
                        current_model, attempt, effective_max_retries,
                        msg_chars, len(tools) if tools else 0,
                    )
                    resp = await self._client.post(
                        self._CHAT_PATH,
                        json=payload,
                        timeout=timeout_config,
                    )
                    elapsed = time.monotonic() - req_start
                    resp.raise_for_status()
                    body = resp.json()

                    choice = body["choices"][0]
                    message = choice.get("message", {})
                    finish_reason: str = choice.get("finish_reason", "stop")
                    content: str = message.get("content") or ""
                    raw_tool_calls = message.get("tool_calls")

                    self._log_token_usage(body, current_model, elapsed)
                    logger.info(
                        "chat_completion_full OK "
                        "(model=%s, attempt=%d/%d, elapsed=%.2fs, "
                        "text_chars=%d, tool_calls=%s, finish=%s)",
                        current_model, attempt, effective_max_retries,
                        elapsed, len(content),
                        len(raw_tool_calls) if raw_tool_calls else 0,
                        finish_reason,
                    )
                    return {
                        "text": content,
                        "tool_calls": raw_tool_calls if raw_tool_calls else None,
                        "usage": body.get("usage", {}),
                        "finish_reason": finish_reason,
                    }
                except (httpx.HTTPStatusError, httpx.TimeoutException, httpx.ConnectError) as exc:
                    self._log_failure(exc, current_model, attempt, effective_max_retries, req_start)
                    if attempt < effective_max_retries:
                        await asyncio.sleep(2 ** (attempt - 1))
                    continue
                except (KeyError, IndexError, _json.JSONDecodeError) as exc:
                    self._log_malformed(
                        exc, current_model, attempt, effective_max_retries, req_start
                    )
                    if attempt < effective_max_retries:
                        await asyncio.sleep(2 ** (attempt - 1))
                    continue

            logger.info(
                "Model %s exhausted after %d retries, trying next fallback.",
                current_model, effective_max_retries,
            )

        raise RouterExhaustedError(f"All models exhausted: {effective_models}")

    async def chat_completion_stream(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.1,
        model: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        models: list[str] | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream tokens from a chat completion via SSE.

        Args:
            messages: OpenAI-style message history.
            temperature: Sampling temperature.
            model: Override the fallback chain with a single model.
            timeout: Per-call HTTP timeout in seconds.
            max_retries: Maximum attempts per model.
            models: Explicit fallback chain.

        Yields:
            Content token strings from ``choices[0].delta.content``.

        Raises:
            RouterExhaustedError: If every model / retry attempt fails.
        """
        import json as _json

        effective_max_retries = max_retries if max_retries is not None else self._max_retries
        timeout_config = httpx.Timeout(timeout) if timeout is not None else None

        if models is not None:
            effective_models = _deduplicate_preserve_order(models)
        elif model is not None:
            effective_models = [model]
        else:
            effective_models = self.models

        for current_model in effective_models:
            for attempt in range(1, effective_max_retries + 1):
                req_start = time.monotonic()
                try:
                    payload: dict[str, Any] = {
                        "model": current_model,
                        "messages": messages,
                        "temperature": temperature,
                        "stream": True,
                    }
                    msg_chars = sum(len(m.get("content", "")) for m in messages)
                    logger.info(
                        "chat_completion_stream -> streaming "
                        "(model=%s, attempt=%d/%d, msg_chars=%d)",
                        current_model, attempt, effective_max_retries, msg_chars,
                    )
                    token_count = 0
                    async with self._client.stream(
                        "POST",
                        self._CHAT_PATH,
                        json=payload,
                        timeout=timeout_config,
                    ) as resp:
                        resp.raise_for_status()
                        async for line in resp.aiter_lines():
                            line = line.strip()
                            if not line:
                                continue
                            if line.startswith("data: "):
                                data_str = line[6:]
                                if data_str == "[DONE]":
                                    break
                                try:
                                    chunk = _json.loads(data_str)
                                    delta = chunk["choices"][0]["delta"]
                                    content = delta.get("content", "")
                                    if content:
                                        token_count += 1
                                        yield content
                                except (KeyError, IndexError, _json.JSONDecodeError):
                                    continue

                    elapsed = time.monotonic() - req_start
                    logger.info(
                        "chat_completion_stream OK "
                        "(model=%s, attempt=%d/%d, elapsed=%.2fs, tokens=%d)",
                        current_model, attempt, effective_max_retries,
                        elapsed, token_count,
                    )
                    return
                except (httpx.HTTPStatusError, httpx.TimeoutException, httpx.ConnectError) as exc:
                    self._log_failure(exc, current_model, attempt, effective_max_retries, req_start)
                    if attempt < effective_max_retries:
                        await asyncio.sleep(2 ** (attempt - 1))
                    continue

            logger.info(
                "Model %s exhausted after %d retries, trying next fallback.",
                current_model, effective_max_retries,
            )

        raise RouterExhaustedError(f"All models exhausted: {effective_models}")

    # ------------------------------------------------------------------
    # Public API — embeddings
    # ------------------------------------------------------------------

    async def get_embedding(self, text: str, *, model: str | None = None) -> list[float]:
        """Generate an embedding vector for *text*.

        Args:
            text: Input text.
            model: Override the default embedding model.

        Returns:
            A ``list[float]`` of length ``embed_dim``.

        Raises:
            EmbeddingError: On HTTP or parsing failure.
        """
        model_name = model or self._embed_model
        prompt_chars = len(text)
        req_start: float = 0.0

        logger.info("get_embedding -> sending (model=%s, input_chars=%d)", model_name, prompt_chars)
        try:
            payload: dict[str, Any] = {"model": model_name, "input": text}
            req_start = time.monotonic()
            resp = await self._client.post(self._EMBED_PATH, json=payload)
            elapsed = time.monotonic() - req_start
            resp.raise_for_status()
            body = resp.json()

            if "error" in body and "data" not in body:
                err_detail = body["error"]
                err_msg = (
                    err_detail.get("message", str(err_detail))
                    if isinstance(err_detail, dict)
                    else str(err_detail)
                )
                logger.error(
                    "get_embedding FAILED "
                    "(model=%s, elapsed=%.2fs, reason=api_error): "
                    "%s | body=%s",
                    model_name, elapsed, err_msg, str(body)[:500],
                )
                raise EmbeddingError(f"Embedding API returned error: {err_msg}") from None

            embedding: list[float] = body["data"][0]["embedding"]
            if len(embedding) != self._embed_dim:
                raise EmbeddingError(
                    f"Expected embedding dimension {self._embed_dim}, "
                    f"got {len(embedding)} from model {model_name!r}"
                )
            logger.info(
                "get_embedding OK (model=%s, elapsed=%.2fs, input_chars=%d, dim=%d)",
                model_name, elapsed, prompt_chars, len(embedding),
            )
            return embedding
        except (httpx.HTTPStatusError, httpx.TimeoutException, httpx.ConnectError) as exc:
            elapsed = time.monotonic() - req_start
            fail_reason = type(exc).__name__
            if isinstance(exc, httpx.HTTPStatusError):
                fail_reason = f"HTTP {exc.response.status_code}"
            logger.error(
                "get_embedding FAILED (model=%s, elapsed=%.2fs, reason=%s): %s",
                model_name, elapsed, fail_reason, exc,
            )
            raise EmbeddingError(f"Embedding API error: {exc}") from exc
        except (KeyError, IndexError) as exc:
            elapsed = time.monotonic() - req_start
            try:
                response_preview = str(body)[:500]
            except Exception:
                response_preview = "<unavailable>"
            logger.error(
                "get_embedding FAILED "
                "(model=%s, elapsed=%.2fs, reason=malformed_response): "
                "%s | body=%s",
                model_name, elapsed, exc, response_preview,
            )
            raise EmbeddingError(f"Malformed embedding response: {exc}") from exc

    async def get_embeddings_batch(
        self,
        texts: Sequence[str],
        *,
        model: str | None = None,
        concurrency: int = 8,
    ) -> list[list[float]]:
        """Generate embeddings for multiple texts with bounded concurrency.

        Args:
            texts: Sequence of input strings.
            model: Override the default embedding model.
            concurrency: Maximum number of simultaneous requests (default 8).

        Returns:
            A list of embedding vectors (same order as *texts*).
        """
        if not texts:
            return []

        semaphore = asyncio.Semaphore(concurrency)

        async def embed_one(text: str) -> list[float]:
            async with semaphore:
                return await self.get_embedding(text, model=model)

        tasks = [embed_one(t) for t in texts]
        results = await asyncio.gather(*tasks)
        return list(results)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        if self._owned:
            await self._client.aclose()

    async def __aenter__(self) -> OpenRouterClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _log_token_usage(body: dict[str, Any], model: str, elapsed: float) -> None:
        usage = body.get("usage", {})
        if usage:
            logger.info(
                "LLM tokens — model=%s prompt=%d completion=%d total=%d latency=%.3fs",
                model,
                usage.get("prompt_tokens", 0),
                usage.get("completion_tokens", 0),
                usage.get("total_tokens", 0),
                elapsed,
            )

    @staticmethod
    def _log_failure(
        exc: Exception,
        model: str,
        attempt: int,
        max_retries: int,
        req_start: float,
    ) -> None:
        elapsed = time.monotonic() - req_start
        fail_reason = type(exc).__name__
        if isinstance(exc, httpx.HTTPStatusError):
            fail_reason = f"HTTP {exc.response.status_code}"
        logger.warning(
            "LLM request FAILED (model=%s, attempt=%d/%d, elapsed=%.2fs, reason=%s): %s",
            model, attempt, max_retries, elapsed, fail_reason, exc,
        )

    @staticmethod
    def _log_malformed(
        exc: Exception,
        model: str,
        attempt: int,
        max_retries: int,
        req_start: float,
    ) -> None:
        elapsed = time.monotonic() - req_start
        logger.warning(
            "Malformed API response "
            "(model=%s, attempt=%d/%d, elapsed=%.2fs, "
            "reason=malformed_response): %s",
            model, attempt, max_retries, elapsed, exc,
        )
