"""FastAPI dependency injection helpers.

Provides reusable dependencies for authentication, database sessions,
and per-user resource access.
"""

from workbench.core.auth import get_current_user
from workbench.core.db import get_session

__all__ = ["get_current_user", "get_session"]
