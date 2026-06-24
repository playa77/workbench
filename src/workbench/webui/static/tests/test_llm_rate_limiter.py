"""Tests for workbench.core.llm_rate_limiter — LLMRateLimiter class."""

import time

import pytest

from workbench.core.llm_rate_limiter import LLMRateLimiter, get_llm_rate_limiter


@pytest.mark.asyncio
async def test_check_unlimited():
    """rpm=0 or user_id=None should always return True without recording."""
    limiter = LLMRateLimiter()
    assert await limiter.check(None, 10) is True
    assert await limiter.check("user1", 0) is True
    # Confirm no timestamps were recorded
    assert len(limiter._timestamps) == 0


@pytest.mark.asyncio
async def test_check_allows_when_under_limit():
    """Calling with rpm=5, three times should all return True."""
    limiter = LLMRateLimiter()
    for _ in range(3):
        assert await limiter.check("user1", 5) is True


@pytest.mark.asyncio
async def test_check_blocks_when_over_limit():
    """rpm=2 — first two calls succeed, third is blocked."""
    limiter = LLMRateLimiter()
    assert await limiter.check("user1", 2) is True
    assert await limiter.check("user1", 2) is True
    assert await limiter.check("user1", 2) is False


@pytest.mark.asyncio
async def test_check_purges_expired():
    """Old timestamps older than 60s are purged before checking."""
    limiter = LLMRateLimiter()
    old_time = time.monotonic() - 120  # 2 minutes ago — well outside the 60s window
    limiter._timestamps["user1"] = [old_time, old_time + 1]

    # rpm=2 with two expired entries → purge both, then record a new one → True
    assert await limiter.check("user1", 2) is True
    # Only the new timestamp should remain
    assert len(limiter._timestamps["user1"]) == 1


@pytest.mark.asyncio
async def test_clear_specific_user():
    """Clearing one user resets only that user's rate limit."""
    limiter = LLMRateLimiter()

    # Exhaust user_a (rpm=2)
    assert await limiter.check("user_a", 2) is True
    assert await limiter.check("user_a", 2) is True
    assert await limiter.check("user_a", 2) is False

    # Exhaust user_b (rpm=2)
    assert await limiter.check("user_b", 2) is True
    assert await limiter.check("user_b", 2) is True
    assert await limiter.check("user_b", 2) is False

    # Clear only user_a
    await limiter.clear("user_a")

    # user_a should be reset — next two calls allowed
    assert await limiter.check("user_a", 2) is True
    assert await limiter.check("user_a", 2) is True
    assert await limiter.check("user_a", 2) is False

    # user_b should still be blocked
    assert await limiter.check("user_b", 2) is False


@pytest.mark.asyncio
async def test_clear_all_users():
    """Clearing without user_id resets every user."""
    limiter = LLMRateLimiter()

    # Exhaust both users at rpm=2
    assert await limiter.check("user1", 2) is True
    assert await limiter.check("user1", 2) is True
    assert await limiter.check("user1", 2) is False
    assert await limiter.check("user2", 2) is True
    assert await limiter.check("user2", 2) is True
    assert await limiter.check("user2", 2) is False

    # Clear all
    await limiter.clear()

    # Both users should be reset
    assert await limiter.check("user1", 2) is True
    assert await limiter.check("user2", 2) is True


@pytest.mark.asyncio
async def test_get_llm_rate_limiter_returns_singleton():
    """get_llm_rate_limiter() always returns the same instance."""
    instance1 = get_llm_rate_limiter()
    instance2 = get_llm_rate_limiter()
    assert instance1 is instance2
    assert isinstance(instance1, LLMRateLimiter)
