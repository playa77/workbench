"""Shared exception hierarchy for Workbench infrastructure."""

from __future__ import annotations


class RouterExhaustedError(Exception):
    """Raised when all models in the fallback chain have been exhausted."""


class EmbeddingError(Exception):
    """Raised when the embedding API fails."""


class ConfigError(Exception):
    """Configuration loading or validation error."""

    def __init__(self, message: str, code: str = "config_error") -> None:
        self.message = message
        self.code = code
        super().__init__(message)


class DatabaseError(Exception):
    """Database connection or session error."""

