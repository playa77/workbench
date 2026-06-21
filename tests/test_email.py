"""Tests for core.email — SMTP email sending with mocked aiosmtplib."""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from workbench.core.email import (
    _send_email,
    send_email_change_verification,
    send_invite_accepted_email,
    send_invite_email,
    send_password_changed_email,
    send_reset_email,
    send_welcome_email,
)


def _make_config(**overrides):
    defaults = dict(
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_user="user@example.com",
        smtp_password="pass",
        smtp_from_address="noreply@example.com",
        smtp_use_tls=True,
    )
    defaults.update(overrides)
    cfg = MagicMock(spec=["smtp_host", "smtp_port", "smtp_user", "smtp_password", "smtp_from_address", "smtp_use_tls"])
    for k, v in defaults.items():
        setattr(cfg, k, v)
    return cfg


# ---- _send_email ----


@pytest.mark.asyncio
async def test_send_email_success():
    config = _make_config()
    with patch("aiosmtplib.send", new_callable=AsyncMock) as mock_send:
        result = await _send_email(config, "to@example.com", "Test Subject", "<b>html</b>", "plain text")
    assert result is True
    mock_send.assert_awaited_once()


@pytest.mark.asyncio
async def test_send_email_no_smtp_host():
    config = _make_config(smtp_host="")
    result = await _send_email(config, "to@example.com", "Subject", "<b>html</b>", "plain")
    assert result is False


@pytest.mark.asyncio
async def test_send_email_smtp_exception():
    config = _make_config()
    with patch("aiosmtplib.send", new_callable=AsyncMock, side_effect=Exception("SMTP fail")):
        result = await _send_email(config, "to@example.com", "Subject", "<b>html</b>", "plain")
    assert result is False


# ---- Template email functions ----


@pytest.mark.asyncio
async def test_send_invite_email():
    config = _make_config()
    with patch("aiosmtplib.send", new_callable=AsyncMock) as mock_send:
        coro = send_invite_email(config, "to@example.com", "alice", "https://example.com/setup?token=abc")
        result = await coro
    assert result is True
    call_args = mock_send.call_args
    msg = call_args[0][0]
    assert msg["Subject"] == "You've been invited to Workbench"
    assert msg["To"] == "to@example.com"


@pytest.mark.asyncio
async def test_send_reset_email():
    config = _make_config()
    with patch("aiosmtplib.send", new_callable=AsyncMock) as mock_send:
        coro = send_reset_email(config, "to@example.com", "https://example.com/reset?token=abc")
        result = await coro
    assert result is True
    msg = mock_send.call_args[0][0]
    assert "Reset" in msg["Subject"]


@pytest.mark.asyncio
async def test_send_welcome_email():
    config = _make_config()
    with patch("aiosmtplib.send", new_callable=AsyncMock) as mock_send:
        coro = send_welcome_email(config, "to@example.com", "bob", "https://example.com/login")
        result = await coro
    assert result is True
    msg = mock_send.call_args[0][0]
    assert "Welcome" in msg["Subject"]


@pytest.mark.asyncio
async def test_send_password_changed_email():
    config = _make_config()
    with patch("aiosmtplib.send", new_callable=AsyncMock) as mock_send:
        coro = send_password_changed_email(config, "to@example.com", "bob")
        result = await coro
    assert result is True
    msg = mock_send.call_args[0][0]
    assert "password" in msg["Subject"].lower()


@pytest.mark.asyncio
async def test_send_email_change_verification():
    config = _make_config()
    with patch("aiosmtplib.send", new_callable=AsyncMock) as mock_send:
        coro = send_email_change_verification(config, "to@example.com", "bob", "https://example.com/verify?token=abc")
        result = await coro
    assert result is True
    msg = mock_send.call_args[0][0]
    assert "Verify" in msg["Subject"]


@pytest.mark.asyncio
async def test_send_invite_accepted_email():
    config = _make_config()
    with patch("aiosmtplib.send", new_callable=AsyncMock) as mock_send:
        coro = send_invite_accepted_email(config, "admin@example.com", "admin", "newuser", "new@example.com")
        result = await coro
    assert result is True
    msg = mock_send.call_args[0][0]
    assert "accepted" in msg["Subject"].lower()
