"""Tests for core.router — re-exports from shared."""

from workbench.core.router import OpenRouterClient, RouterExhaustedError
from workbench.shared.llm.router import OpenRouterClient as SharedClient
from workbench.shared.errors import RouterExhaustedError as SharedError


def test_reexports_openrouter_client():
    assert OpenRouterClient is SharedClient


def test_reexports_router_exhausted_error():
    assert RouterExhaustedError is SharedError
