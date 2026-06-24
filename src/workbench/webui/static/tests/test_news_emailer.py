"""Tests for workbench.services.news_emailer — SMTP email dispatch."""

import os
import smtplib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from workbench.services.news_emailer import (
    EmailerError,
    _send_email,
    send_failure_alert,
    send_pipeline_results,
    send_success_brief,
    send_success_theme,
)


# ---------------------------------------------------------------------------
# _send_email
# ---------------------------------------------------------------------------

@patch("smtplib.SMTP")
def test_send_email_ok(mock_smtp_cls):
    """Happy path — SMTP connects, logs in, sends, and returns."""
    mock_server = MagicMock()
    mock_smtp_cls.return_value.__enter__.return_value = mock_server

    _send_email(
        smtp_host="smtp.test.com",
        smtp_port=587,
        smtp_user="user@test.com",
        smtp_password="secret",
        sender="sender@test.com",
        recipient="recip@test.com",
        subject="Test Subject",
        body="Hello!",
    )

    mock_smtp_cls.assert_called_once_with("smtp.test.com", 587)
    mock_server.starttls.assert_called_once()
    mock_server.login.assert_called_once_with("user@test.com", "secret")
    mock_server.send_message.assert_called_once()
    msg = mock_server.send_message.call_args[0][0]
    assert msg["Subject"] == "Test Subject"
    assert msg["From"] == "sender@test.com"
    assert msg["To"] == "recip@test.com"


@patch("smtplib.SMTP")
def test_send_email_retry_then_raise(mock_smtp_cls):
    """SMTPException on all attempts raises EmailerError."""
    mock_server = MagicMock()
    mock_server.send_message.side_effect = smtplib.SMTPException("fail")
    mock_smtp_cls.return_value.__enter__.return_value = mock_server

    with pytest.raises(EmailerError, match="Failed to send email after 3 attempts"):
        _send_email(
            smtp_host="smtp.test.com",
            smtp_port=587,
            smtp_user="u",
            smtp_password="p",
            sender="s",
            recipient="r",
            subject="S",
            body="B",
        )

    assert mock_server.send_message.call_count == 3  # _SMTP_MAX_RETRIES + 1


@patch("smtplib.SMTP")
def test_send_email_retry_on_oserror(mock_smtp_cls):
    """OSError is also retried."""
    mock_server = MagicMock()
    mock_server.send_message.side_effect = OSError("connection lost")
    mock_smtp_cls.return_value.__enter__.return_value = mock_server

    with pytest.raises(EmailerError):
        _send_email(
            smtp_host="h", smtp_port=587, smtp_user="u", smtp_password="p",
            sender="s", recipient="r", subject="S", body="B",
        )

    assert mock_server.send_message.call_count == 3


@patch("smtplib.SMTP")
def test_send_email_recovers_on_second_attempt(mock_smtp_cls):
    """First attempt fails, second succeeds."""
    mock_server = MagicMock()
    mock_server.send_message.side_effect = [smtplib.SMTPException("fail"), None]
    mock_smtp_cls.return_value.__enter__.return_value = mock_server

    _send_email(
        smtp_host="h", smtp_port=587, smtp_user="u", smtp_password="p",
        sender="s", recipient="r", subject="S", body="B",
    )

    assert mock_server.send_message.call_count == 2


# ---------------------------------------------------------------------------
# send_failure_alert
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@patch("workbench.services.news_emailer._send_email")
async def test_send_failure_alert(mock_send):
    """send_failure_alert builds correct subject/body and delegates."""
    await send_failure_alert(
        smtp_host="h", smtp_port=587, smtp_user="u", smtp_password="p",
        sender="s", recipient="r",
        interest_name="TestInterest",
        stage_name="scrape",
        error_message="Something broke",
        traceback_str="Traceback (most recent call last):\n  ...",
    )

    mock_send.assert_called_once()
    kwargs = mock_send.call_args[1]
    assert kwargs["smtp_host"] == "h"
    assert "TestInterest Pipeline FAILURE — scrape" in kwargs["subject"]
    assert "Something broke" in kwargs["body"]
    assert "Traceback" in kwargs["body"]


# ---------------------------------------------------------------------------
# send_success_brief
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@patch("workbench.services.news_emailer._send_email")
async def test_send_success_brief(mock_send):
    """send_success_brief builds correct subject/body."""
    await send_success_brief(
        smtp_host="h", smtp_port=587, smtp_user="u", smtp_password="p",
        sender="s", recipient="r",
        interest_name="MyInterest",
        run_date="2025-06-01",
        brief_content="Daily brief content here.",
    )

    mock_send.assert_called_once()
    kwargs = mock_send.call_args[1]
    assert kwargs["subject"] == "MyInterest Daily Brief — 2025-06-01"
    assert kwargs["body"] == "Daily brief content here."


# ---------------------------------------------------------------------------
# send_success_theme
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@patch("workbench.services.news_emailer._send_email")
async def test_send_success_theme_full(mock_send):
    """send_success_theme with summary, script, script_de."""
    await send_success_theme(
        smtp_host="h", smtp_port=587, smtp_user="u", smtp_password="p",
        sender="s", recipient="r",
        interest_name="AI",
        run_date="2025-06-01",
        theme_title="LLM Advances",
        summary="Great progress.",
        script="[Intro] Hello!",
        script_de="[Einleitung] Hallo!",
    )

    mock_send.assert_called_once()
    kwargs = mock_send.call_args[1]
    assert kwargs["subject"] == "AI Theme: LLM Advances — 2025-06-01"
    assert "=== SUMMARY ===" in kwargs["body"]
    assert "=== SCRIPT (EN) ===" in kwargs["body"]
    assert "=== SCRIPT (DE) ===" in kwargs["body"]


@pytest.mark.asyncio
@patch("workbench.services.news_emailer._send_email")
async def test_send_success_theme_summary_only(mock_send):
    """send_success_theme with only summary."""
    await send_success_theme(
        smtp_host="h", smtp_port=587, smtp_user="u", smtp_password="p",
        sender="s", recipient="r",
        interest_name="AI",
        run_date="2025-06-01",
        theme_title="LLM",
        summary="Only summary.",
    )

    mock_send.assert_called_once()
    assert "=== SUMMARY ===" in mock_send.call_args[1]["body"]
    assert "SCRIPT (EN)" not in mock_send.call_args[1]["body"]
    assert "SCRIPT (DE)" not in mock_send.call_args[1]["body"]


@pytest.mark.asyncio
@patch("workbench.services.news_emailer._send_email")
async def test_send_success_theme_none(mock_send):
    """All parts None → returns early without sending."""
    await send_success_theme(
        smtp_host="h", smtp_port=587, smtp_user="u", smtp_password="p",
        sender="s", recipient="r",
        interest_name="AI", run_date="2025-06-01",
        theme_title="LLM",
    )

    mock_send.assert_not_called()


# ---------------------------------------------------------------------------
# send_pipeline_results
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_pipeline_results_no_password():
    """Missing SMTP password -> returns 0."""
    store = AsyncMock()
    store.get_run.return_value = {"run_date": "2025-06-01"}

    with patch.dict(os.environ, {}, clear=True):
        count = await send_pipeline_results(
            run_id=1, store=store,
            interest={"name": "Test"},
            smtp_config={"host": "smtp.gmail.com"},
        )

    assert count == 0
    store.get_run.assert_awaited_once_with(1)


@pytest.mark.asyncio
async def test_send_pipeline_results_run_none():
    """get_run returns None -> run_date defaults to empty."""
    store = AsyncMock()
    store.get_run.return_value = None
    store.get_daily_brief_for_run.return_value = None
    store.get_themes_for_run.return_value = []

    with patch.dict(os.environ, {"WORKBENCH_NEWS_SMTP_PASSWORD": "secret"}):
        count = await send_pipeline_results(
            run_id=2, store=store,
            interest={"name": "Test", "enable_brief": True},
            smtp_config={},
        )

    # No brief since get_daily_brief_for_run returns None (no brief stored)
    # No themes
    assert count == 0


@pytest.mark.asyncio
async def test_send_pipeline_results_with_brief():
    """enable_brief=True, brief exists -> sends brief email."""
    store = AsyncMock()
    store.get_run.return_value = {"run_date": "2025-06-01"}
    store.get_daily_brief_for_run.return_value = {"content": "Brief content"}
    store.get_themes_for_run.return_value = []

    with patch.dict(os.environ, {"WORKBENCH_NEWS_SMTP_PASSWORD": "secret"}):
        with patch("workbench.services.news_emailer.send_success_brief", new_callable=AsyncMock) as mock_brief:
            count = await send_pipeline_results(
                run_id=1, store=store,
                interest={"name": "AI", "enable_brief": True},
                smtp_config={"host": "smtp.gmail.com", "port": 587, "user": "u", "sender": "s", "recipient": "r"},
            )

    assert count == 1
    mock_brief.assert_awaited_once()
    assert mock_brief.call_args[1]["interest_name"] == "AI"
    assert mock_brief.call_args[1]["brief_content"] == "Brief content"


@pytest.mark.asyncio
async def test_send_pipeline_results_brief_disabled():
    """enable_brief=False -> skips brief."""
    store = AsyncMock()
    store.get_run.return_value = {"run_date": "2025-06-01"}
    store.get_themes_for_run.return_value = []

    with patch.dict(os.environ, {"WORKBENCH_NEWS_SMTP_PASSWORD": "secret"}):
        with patch("workbench.services.news_emailer.send_success_brief", new_callable=AsyncMock) as mock_brief:
            count = await send_pipeline_results(
                run_id=1, store=store,
                interest={"name": "AI", "enable_brief": False},
                smtp_config={},
            )

    assert count == 0
    mock_brief.assert_not_called()


@pytest.mark.asyncio
async def test_send_pipeline_results_brief_enabled_no_brief():
    """enable_brief=True but no brief stored -> no email for brief."""
    store = AsyncMock()
    store.get_run.return_value = {"run_date": "2025-06-01"}
    store.get_daily_brief_for_run.return_value = None
    store.get_themes_for_run.return_value = []

    with patch.dict(os.environ, {"WORKBENCH_NEWS_SMTP_PASSWORD": "secret"}):
        with patch("workbench.services.news_emailer.send_success_brief", new_callable=AsyncMock) as mock_brief:
            count = await send_pipeline_results(
                run_id=1, store=store,
                interest={"name": "AI", "enable_brief": True},
                smtp_config={},
            )

    assert count == 0
    mock_brief.assert_not_called()


@pytest.mark.asyncio
async def test_send_pipeline_results_with_themes():
    """Themes with various deliverable types get sent."""
    store = AsyncMock()
    store.get_run.return_value = {"run_date": "2025-06-01"}
    store.get_themes_for_run.return_value = [
        {"id": 10, "title": "Theme A"},
        {"id": 11, "title": "Theme B"},
    ]

    # Theme 10: has summary and script; Theme 11: has script_de
    async def _deliverables_for_theme(theme_id):
        if theme_id == 10:
            return [
                {"deliverable_type": "summary", "content": "Summary A"},
                {"deliverable_type": "script", "content": "Script A"},
            ]
        elif theme_id == 11:
            return [
                {"deliverable_type": "script_de", "content": "Script DE B"},
            ]
        return []
    store.get_deliverables_for_theme = _deliverables_for_theme

    with patch.dict(os.environ, {"WORKBENCH_NEWS_SMTP_PASSWORD": "secret"}):
        with patch("workbench.services.news_emailer.send_success_theme", new_callable=AsyncMock) as mock_theme:
            count = await send_pipeline_results(
                run_id=1, store=store,
                interest={"name": "AI", "enable_summary": True, "enable_script": True, "enable_script_de": True},
                smtp_config={},
            )

    assert count == 2
    assert mock_theme.await_count == 2


@pytest.mark.asyncio
async def test_send_pipeline_results_skips_disabled_deliverables():
    """Disable summary and script -> only script_de sent."""
    store = AsyncMock()
    store.get_run.return_value = {"run_date": "2025-06-01"}
    store.get_themes_for_run.return_value = [{"id": 10, "title": "Theme"}]
    store.get_deliverables_for_theme.return_value = [
        {"deliverable_type": "summary", "content": "Sum"},
        {"deliverable_type": "script", "content": "Scr"},
        {"deliverable_type": "script_de", "content": "DE"},
    ]

    with patch.dict(os.environ, {"WORKBENCH_NEWS_SMTP_PASSWORD": "secret"}):
        with patch("workbench.services.news_emailer.send_success_theme", new_callable=AsyncMock) as mock_theme:
            count = await send_pipeline_results(
                run_id=1, store=store,
                interest={"name": "AI", "enable_summary": False, "enable_script": False, "enable_script_de": True},
                smtp_config={},
            )

    assert count == 1
    call_kwargs = mock_theme.call_args[1]
    assert call_kwargs["summary"] is None
    assert call_kwargs["script"] is None
    assert call_kwargs["script_de"] == "DE"


@pytest.mark.asyncio
async def test_send_pipeline_results_no_deliverables_for_theme():
    """Theme with no matching deliverables -> skipped."""
    store = AsyncMock()
    store.get_run.return_value = {"run_date": "2025-06-01"}
    store.get_themes_for_run.return_value = [{"id": 10, "title": "Theme"}]
    store.get_deliverables_for_theme.return_value = []

    with patch.dict(os.environ, {"WORKBENCH_NEWS_SMTP_PASSWORD": "secret"}):
        with patch("workbench.services.news_emailer.send_success_theme", new_callable=AsyncMock) as mock_theme:
            count = await send_pipeline_results(
                run_id=1, store=store,
                interest={"name": "AI", "enable_summary": True, "enable_script": True},
                smtp_config={},
            )

    assert count == 0
    mock_theme.assert_not_called()
