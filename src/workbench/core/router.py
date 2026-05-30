"""OpenRouter provider routing — LLM API client with fallback.

Adapted from stoa's protocols and citizen's router.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from base64 import b64encode
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class RouterExhaustedError(Exception):
    pass


class OpenRouterClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://openrouter.ai/api/v1",
        timeout: float = 120.0,
    ) -> None:
        self._api_key = api_key
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(timeout),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://workbench.local",
                "X-Title": "Workbench",
            },
        )
        self._owned = True

    @classmethod
    def from_env(cls, env_var: str = "OPENROUTER_API_KEY", base_url: str = "https://openrouter.ai/api/v1", timeout: float = 120.0) -> "OpenRouterClient":
        api_key = os.environ.get(env_var, "")
        if not api_key:
            raise RuntimeError(f"Missing {env_var}")
        return cls(api_key=api_key, base_url=base_url, timeout=timeout)

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        *,
        model: str = "deepseek/deepseek-v4-flash",
        temperature: float = 0.1,
        max_tokens: int = 4096,
        max_retries: int = 2,
    ) -> str:
        for attempt in range(1, max_retries + 2):
            try:
                payload = {
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }
                start = time.monotonic()
                resp = await self._client.post("/chat/completions", json=payload)
                elapsed = time.monotonic() - start
                resp.raise_for_status()
                body = resp.json()
                content = body["choices"][0]["message"]["content"]
                logger.info("chat_completion OK (model=%s, elapsed=%.2fs)", model, elapsed)
                return content
            except httpx.HTTPStatusError as exc:
                logger.warning("HTTP %s from %s (attempt %d): %s", exc.response.status_code, model, attempt, exc)
                if exc.response.status_code in {400, 401, 402, 403}:
                    raise RuntimeError(f"Non-retryable HTTP {exc.response.status_code}: {exc}") from exc
                if attempt <= max_retries:
                    await asyncio.sleep(2 ** (attempt - 1))
            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                logger.warning("Network error from %s (attempt %d): %s", model, attempt, exc)
                if attempt <= max_retries:
                    await asyncio.sleep(2 ** (attempt - 1))
        raise RouterExhaustedError(f"All {max_retries + 1} attempts failed for model {model}")

    async def chat_completion_stream(
        self,
        messages: list[dict[str, str]],
        *,
        model: str = "deepseek/deepseek-v4-flash",
        temperature: float = 0.1,
        max_tokens: int = 4096,
        max_retries: int = 2,
    ):
        import json

        for attempt in range(1, max_retries + 2):
            try:
                payload = {
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "stream": True,
                }
                start = time.monotonic()
                async with self._client.stream("POST", "/chat/completions", json=payload) as resp:
                    resp.raise_for_status()
                    token_count = 0
                    async for line in resp.aiter_lines():
                        line = line.strip()
                        if not line or not line.startswith("data: "):
                            continue
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            content = chunk["choices"][0]["delta"].get("content", "")
                            if content:
                                token_count += 1
                                yield content
                        except (KeyError, IndexError, json.JSONDecodeError):
                            continue
                logger.info("stream OK (model=%s, elapsed=%.2fs, tokens=%d)", model, time.monotonic() - start, token_count)
                return
            except httpx.HTTPStatusError as exc:
                logger.warning("Stream HTTP %s from %s (attempt %d)", exc.response.status_code, model, attempt)
                if exc.response.status_code in {400, 401, 402, 403}:
                    raise RuntimeError(f"Non-retryable: {exc}") from exc
                if attempt <= max_retries:
                    await asyncio.sleep(2 ** (attempt - 1))
            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                logger.warning("Stream network error from %s (attempt %d): %s", model, attempt, exc)
                if attempt <= max_retries:
                    await asyncio.sleep(2 ** (attempt - 1))
        raise RouterExhaustedError(f"All stream attempts failed for {model}")

    async def get_embedding(self, text: str, model: str = "openai/text-embedding-3-small") -> list[float]:
        payload = {"model": model, "input": text}
        resp = await self._client.post("/embeddings", json=payload)
        resp.raise_for_status()
        body = resp.json()
        return body["data"][0]["embedding"]

    async def close(self) -> None:
        if self._owned:
            await self._client.aclose()

    async def __aenter__(self) -> "OpenRouterClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()
