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


def test_agent_build_router_override():
    """Test that _build_router returning a router gets registered."""
    class _RouterAgent(AgentBase):
        name = "router_agent"
        def _build_router(self):
            from fastapi import APIRouter
            r = APIRouter()
            r.add_api_route("/custom", lambda: {"ok": True}, methods=["GET"])
            return r

    app = FastAPI()
    agent = _RouterAgent()
    agent.register_routes(app)
    routes = [r.path for r in app.routes]
    assert any("/custom" in r for r in routes)


def test_agent_get_static_dir_override():
    """Test that get_static_dir can be overridden."""
    from pathlib import Path
    class _StaticAgent(AgentBase):
        name = "static_agent"
        def get_static_dir(self):
            return Path("/fake/path")

    agent = _StaticAgent()
    assert agent.get_static_dir() == Path("/fake/path")


def test_agent_get_static_dir_default():
    """Test that get_static_dir default returns None (line 59)."""
    agent = _DummyAgent()
    assert agent.get_static_dir() is None


def test_agent_build_router_default():
    """Test that _build_router default returns None (line 42)."""
    agent = _DummyAgent()
    assert agent._build_router() is None


@pytest.mark.asyncio
async def test_agent_on_enable_default():
    """Test that on_enable default is a no-op (line 62)."""
    agent = _DummyAgent()
    # Should not raise
    await agent.on_enable("user1", None)


@pytest.mark.asyncio
async def test_agent_on_disable_default():
    """Test that on_disable default is a no-op (line 65)."""
    agent = _DummyAgent()
    # Should not raise
    await agent.on_disable("user1", None)


@pytest.mark.asyncio
async def test_agent_on_enable_override():
    """Test lifecycle hook on_enable is callable and can be overridden."""
    calls = []
    class _LifecycleAgent(AgentBase):
        name = "lifecycle"
        async def on_enable(self, user_id, session):
            calls.append(("enable", user_id))

    agent = _LifecycleAgent()
    await agent.on_enable("user1", None)
    assert calls == [("enable", "user1")]


@pytest.mark.asyncio
async def test_agent_on_disable_override():
    """Test lifecycle hook on_disable is callable and can be overridden."""
    calls = []
    class _LifecycleAgent(AgentBase):
        name = "lifecycle"
        async def on_disable(self, user_id, session):
            calls.append(("disable", user_id))

    agent = _LifecycleAgent()
    await agent.on_disable("user1", None)
    assert calls == [("disable", "user1")]


@pytest.mark.asyncio
async def test_set_user_agent_setting_update_settings_only(db_session: AsyncSession):
    """Settings update when row already exists (hits line 149)."""
    user = User(id=uuid4(), username="settings_user4")
    db_session.add(user)
    await db_session.commit()

    # Create with initial settings
    await set_user_agent_setting(
        user_id=str(user.id), agent_name="chat", enabled=True,
        settings={"model": "old"}, session=db_session
    )

    # Update only settings
    await set_user_agent_setting(
        user_id=str(user.id), agent_name="chat",
        settings={"model": "new", "temp": 0.5}, session=db_session
    )

    settings = await get_user_agent_settings(str(user.id), db_session)
    assert settings["chat"]["enabled"] is True  # unchanged
    assert settings["chat"]["settings"] == {"model": "new", "temp": 0.5}
