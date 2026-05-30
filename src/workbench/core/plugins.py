"""Agent system — registration, lifecycle, settings.

Every agent subclasses AgentBase (defined as PluginBase in the core for model compat).
Agents register API routes under /api/v1/agents/{name}, provide settings schemas,
and define frontend tabs. Each agent maps to a dedicated browser tab.
"""

from __future__ import annotations

import logging
from abc import ABC
from typing import Any

from fastapi import APIRouter, FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from workbench.core.models import UserPluginSettings

logger = logging.getLogger(__name__)

_LAZY_IMPORT_LOCK = False


class PluginBase(ABC):
    """Abstract base class for all Workbench agents (PluginBase for DB model compat)."""

    name: str = ""
    display_name: str = ""
    description: str = ""
    version: str = "0.1.0"
    icon: str = "puzzle"

    def register_routes(self, app: FastAPI) -> None:
        router = self._build_router()
        if router is not None:
            app.include_router(
                router,
                prefix=f"/api/v1/agents/{self.name}",
                tags=[f"agent:{self.name}"],
            )

    def _build_router(self) -> APIRouter | None:
        return None

    def get_settings_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}, "additionalProperties": False}

    def get_default_settings(self) -> dict[str, Any]:
        return {}

    def get_frontend_tab(self) -> dict[str, Any]:
        return {
            "id": self.name,
            "displayName": self.display_name,
            "icon": self.icon,
            "component": f"agent-{self.name}",
        }

    async def on_enable(self, user_id: str, session: AsyncSession) -> None:
        pass

    async def on_disable(self, user_id: str, session: AsyncSession) -> None:
        pass


AgentBase = PluginBase


class PluginRegistry:
    """Central registry for all loaded agents (retains 'PluginRegistry' for compat)."""

    def __init__(self) -> None:
        self._plugins: dict[str, PluginBase] = {}

    def register(self, plugin: PluginBase) -> None:
        if plugin.name in self._plugins:
            logger.debug("Agent '%s' already registered — skipping", plugin.name)
            return
        self._plugins[plugin.name] = plugin
        logger.info("Registered agent: %s v%s", plugin.name, plugin.version)

    def get(self, name: str) -> PluginBase | None:
        return self._plugins.get(name)

    def list_all(self) -> list[PluginBase]:
        return list(self._plugins.values())

    def mount_all(self, app: FastAPI) -> None:
        for plugin in self._plugins.values():
            plugin.register_routes(app)

    def get_tabs(self) -> list[dict[str, Any]]:
        return [p.get_frontend_tab() for p in self._plugins.values()]


_registry: PluginRegistry | None = None


def get_registry() -> PluginRegistry:
    global _registry
    if _registry is None:
        _registry = PluginRegistry()
    return _registry


async def get_user_plugin_settings(user_id: str, session: AsyncSession) -> dict[str, dict[str, Any]]:
    result = await session.execute(
        select(UserPluginSettings).where(UserPluginSettings.user_id == user_id)
    )
    rows = result.scalars().all()
    return {
        row.plugin_name: {"enabled": row.enabled, "settings": row.settings}
        for row in rows
    }


async def set_user_plugin_setting(
    user_id: str,
    plugin_name: str,
    enabled: bool | None = None,
    settings: dict[str, Any] | None = None,
    session: AsyncSession | None = None,
) -> UserPluginSettings:
    from uuid import UUID
    if session is None:
        raise RuntimeError("Session required")

    result = await session.execute(
        select(UserPluginSettings).where(
            UserPluginSettings.user_id == UUID(user_id) if isinstance(user_id, str) else user_id,
            UserPluginSettings.plugin_name == plugin_name,
        )
    )
    row = result.scalar_one_or_none()

    if row is None:
        row = UserPluginSettings(
            user_id=UUID(user_id) if isinstance(user_id, str) else user_id,
            plugin_name=plugin_name,
            enabled=enabled if enabled is not None else False,
            settings=settings or {},
        )
        session.add(row)
    else:
        if enabled is not None:
            row.enabled = enabled
        if settings is not None:
            row.settings = settings
    await session.commit()
    await session.refresh(row)
    return row
