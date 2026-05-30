"""Tests for workbench.core.agents."""

from uuid import uuid4

import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from workbench.core.agents import (
    AgentBase,
    AgentRegistry,
    get_registry,
    get_user_agent_settings,
    set_user_agent_setting,
)
from workbench.core.models import User


class _DummyAgent(AgentBase):
    name = "dummy"
    display_name = "Dummy Agent"
    description = "A test agent"
    version = "1.0.0"
    icon = "box"


class _SettingsAgent(AgentBase):
    name = "custom"
    display_name = "Custom Agent"

    def _build_router(self):
        from fastapi import APIRouter
        router = APIRouter()
        router.add_api_route("/info", lambda: {"status": "ok"}, methods=["GET"])
        return router

    def get_settings_schema(self):
        return {"type": "object", "properties": {"temperature": {"type": "number"}}}

    def get_default_settings(self):
        return {"temperature": 0.7}


def test_agent_registry_register():
    registry = AgentRegistry()
    agent = _DummyAgent()
    registry.register(agent)

    assert registry.get("dummy") is agent
    assert registry.get("nonexistent") is None


def test_agent_registry_list_all():
    registry = AgentRegistry()
    registry.register(_DummyAgent())
    registry.register(_SettingsAgent())

    agents = registry.list_all()
    assert len(agents) == 2
    names = {a.name for a in agents}
    assert names == {"dummy", "custom"}


def test_agent_registry_duplicate_register():
    registry = AgentRegistry()
    agent = _DummyAgent()
    registry.register(agent)
    registry.register(agent)

    assert len(registry.list_all()) == 1


def test_agent_registry_get_tabs():
    registry = AgentRegistry()
    registry.register(_DummyAgent())

    tabs = registry.get_tabs()
    assert len(tabs) == 1
    assert tabs[0]["id"] == "dummy"
    assert tabs[0]["displayName"] == "Dummy Agent"


def test_agent_registry_mount_all():
    app = FastAPI()
    registry = AgentRegistry()
    registry.register(_SettingsAgent())
    registry.mount_all(app)

    routes = [r.path for r in app.routes]
    assert any("/api/v1/agents/custom" in r for r in routes)


def test_get_registry_singleton():
    r1 = get_registry()
    r2 = get_registry()
    assert r1 is r2


def test_agent_base_defaults():
    agent = AgentBase.__new__(AgentBase)
    assert agent.get_settings_schema() == {
        "type": "object", "properties": {}, "additionalProperties": False
    }
    assert agent.get_default_settings() == {}


@pytest.mark.asyncio
async def test_get_user_agent_settings_empty(db_session: AsyncSession):
    user = User(id=uuid4(), username="settings_agent_user")
    db_session.add(user)
    await db_session.commit()

    settings = await get_user_agent_settings(str(user.id), db_session)
    assert settings == {}


@pytest.mark.asyncio
async def test_set_and_get_user_agent_setting(db_session: AsyncSession):
    user = User(id=uuid4(), username="settings_user2")
    db_session.add(user)
    await db_session.commit()

    await set_user_agent_setting(
        user_id=str(user.id),
        agent_name="chat",
        enabled=True,
        settings={"model": "deepseek"},
        session=db_session,
    )

    settings = await get_user_agent_settings(str(user.id), db_session)
    assert "chat" in settings
    assert settings["chat"]["enabled"] is True
    assert settings["chat"]["settings"] == {"model": "deepseek"}


@pytest.mark.asyncio
async def test_set_user_agent_setting_update(db_session: AsyncSession):
    user = User(id=uuid4(), username="settings_user3")
    db_session.add(user)
    await db_session.commit()

    await set_user_agent_setting(
        user_id=str(user.id), agent_name="chat", enabled=True, settings={}, session=db_session
    )
    await set_user_agent_setting(
        user_id=str(user.id), agent_name="chat", enabled=False, session=db_session
    )

    settings = await get_user_agent_settings(str(user.id), db_session)
    assert settings["chat"]["enabled"] is False


@pytest.mark.asyncio
async def test_set_user_agent_setting_no_session_raises():
    with pytest.raises(RuntimeError, match="Session required"):
        await set_user_agent_setting(
            user_id="some-id", agent_name="chat", enabled=True, session=None
        )
