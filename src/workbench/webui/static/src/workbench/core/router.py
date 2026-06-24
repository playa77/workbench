"""OpenRouter provider routing — LLM API client with fallback.

Now re-exports from workbench.shared.llm.router — the canonical implementation.
Kept as a compatibility shim for existing import paths.
"""

from workbench.shared.errors import RouterExhaustedError
from workbench.shared.llm.router import OpenRouterClient, RateLimitExceededError

__all__ = ["OpenRouterClient", "RateLimitExceededError", "RouterExhaustedError"]
