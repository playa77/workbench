"""Agent management routes — list, enable/disable, get/set settings."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from workbench.core.auth import get_current_user
from workbench.core.db import get_session
from workbench.core.models import User
from workbench.core.plugins import get_registry, get_user_plugin_settings, set_user_plugin_setting

router = APIRouter()


class AgentInfo(BaseModel):
    name: str
    display_name: str
    description: str
    version: str
    icon: str
    enabled: bool = False


class AgentSettingsUpdate(BaseModel):
    enabled: bool | None = None
    settings: dict | None = None


@router.get("/agents", response_model=list[AgentInfo])
async def list_agents(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    registry = get_registry()
    user_settings = await get_user_plugin_settings(str(user.id), session)
    agents = []
    for agent in registry.list_all():
        agent_config = user_settings.get(agent.name, {})
        agents.append(
            AgentInfo(
                name=agent.name,
                display_name=agent.display_name,
                description=agent.description,
                version=agent.version,
                icon=agent.icon,
                enabled=agent_config.get("enabled", False),
            )
        )
    return agents


@router.get("/agents/{agent_name}/settings")
async def get_agent_settings(
    agent_name: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    registry = get_registry()
    agent = registry.get(agent_name)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    user_settings = await get_user_plugin_settings(str(user.id), session)
    agent_config = user_settings.get(agent_name, {})

    return {
        "agent_name": agent_name,
        "enabled": agent_config.get("enabled", False),
        "settings_schema": agent.get_settings_schema(),
        "current_settings": agent_config.get("settings", agent.get_default_settings()),
    }


@router.put("/agents/{agent_name}/settings")
async def update_agent_settings(
    agent_name: str,
    body: AgentSettingsUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    registry = get_registry()
    agent = registry.get(agent_name)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    updated = await set_user_plugin_setting(
        user_id=str(user.id),
        plugin_name=agent_name,
        enabled=body.enabled,
        settings=body.settings,
        session=session,
    )

    if body.enabled is True:
        await agent.on_enable(str(user.id), session)
    elif body.enabled is False:
        await agent.on_disable(str(user.id), session)

    return {"enabled": updated.enabled, "settings": updated.settings}
