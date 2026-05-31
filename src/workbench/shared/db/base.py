"""Shared SQLAlchemy declarative base.

All domain models across agents and services inherit from this single Base
to ensure consistent metadata and enable cross-agent relationship queries.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base for all Workbench SQLAlchemy models."""
