"""Tests for shared.llm.__init__ — re-export."""

from workbench.shared.llm import OpenRouterClient
from workbench.shared.llm.router import OpenRouterClient as RouterClient


def test_reexports_openrouter_client():
    assert OpenRouterClient is RouterClient
