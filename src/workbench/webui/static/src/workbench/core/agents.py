"""Agent system — registration, lifecycle, settings.

Every agent subclasses AgentBase. Agents register API routes under
/api/v1/agents/{name}, provide settings schemas, and define frontend tabs.
"""

from __future__ import annotations

import logging
from abc import ABC
from pathlib import Path
from typing import Any

from fastapi import APIRouter, FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from workbench.core.models import UserAgentSettings

logger = logging.getLogger(__name__)


class AgentBase(ABC):
    """Abstract base class for all Workbench agents."""

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

    def get_static_dir(self) -> Path | None:
        return None

    async def on_enable(self, user_id: str, session: AsyncSession) -> None:
        pass

    async def on_disable(self, user_id: str, session: AsyncSession) -> None:
        pass


class AgentRegistry:
    """Central registry for all loaded agents."""

    def __init__(self) -> None:
        self._agents: dict[str, AgentBase] = {}

    def register(self, agent: AgentBase) -> None:
        if agent.name in self._agents:
            logger.debug("Agent '%s' already registered — skipping", agent.name)
            return
        self._agents[agent.name] = agent
        logger.info("Registered agent: %s v%s", agent.name, agent.version)

    def get(self, name: str) -> AgentBase | None:
        return self._agents.get(name)

    def list_all(self) -> list[AgentBase]:
        return list(self._agents.values())

    def mount_all(self, app: FastAPI) -> None:
        for agent in self._agents.values():
            agent.register_routes(app)

    def get_tabs(self) -> list[dict[str, Any]]:
        return [a.get_frontend_tab() for a in self._agents.values()]


_registry: AgentRegistry | None = None


def get_registry() -> AgentRegistry:
    global _registry
    if _registry is None:
        _registry = AgentRegistry()
    return _registry


async def get_user_agent_settings(user_id: str, session: AsyncSession) -> dict[str, dict[str, Any]]:
    from uuid import UUID

    result = await session.execute(
        select(UserAgentSettings).where(UserAgentSettings.user_id == UUID(user_id))
    )
    rows = result.scalars().all()
    return {
        row.agent_name: {"enabled": row.enabled, "settings": row.settings}
        for row in rows
    }


async def set_user_agent_setting(
    user_id: str,
    agent_name: str,
    enabled: bool | None = None,
    settings: dict[str, Any] | None = None,
    session: AsyncSession | None = None,
) -> UserAgentSettings:
    from uuid import UUID
    if session is None:
        raise RuntimeError("Session required")

    result = await session.execute(
        select(UserAgentSettings).where(
            UserAgentSettings.user_id == UUID(user_id) if isinstance(user_id, str) else user_id,
            UserAgentSettings.agent_name == agent_name,
        )
    )
    row = result.scalar_one_or_none()

    if row is None:
        row = UserAgentSettings(
            user_id=UUID(user_id) if isinstance(user_id, str) else user_id,
            agent_name=agent_name,
            enabled=enabled if enabled is not None else True,
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
