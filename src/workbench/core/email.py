"""SMTP email sending for Workbench.

Uses aiosmtplib for async delivery. Requires SMTP config.
SMTP settings come from WorkbenchConfig, overridable via server_config DB table (editable in Settings by admin).
"""

from __future__ import annotations

import logging

from workbench.core.models import ServerConfig

LOGGER = logging.getLogger(__name__)

_PLAIN_SIGNATURE = "\n\n--\nWorkbench"

_HTML_WRAPPER = """<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,sans-serif;color:#e4e6eb;background:#0f1117;padding:24px">
<div style="max-width:560px;margin:0 auto">
{body}
<div style="margin-top:32px;font-size:11px;color:#6b6e7d;border-top:1px solid #252839;padding-top:16px">
Workbench
</div>
</div>
</body></html>"""


async def _send_email(config, to_address: str, subject: str, html_body: str, plain_body: str,
                      smtp_overrides: dict | None = None) -> bool:
    """Send an email via SMTP. config is WorkbenchConfig. smtp_overrides are key-value pairs
    from the server_config DB table that override SMTP fields (host, port, user, password,
    from_address, use_tls)."""
    overrides = smtp_overrides or {}

    host = overrides.get("smtp_host") or config.smtp_host
    port = int(overrides.get("smtp_port", 0)) or config.smtp_port
    user = overrides.get("smtp_user") or config.smtp_user
    password = overrides.get("smtp_password") or config.smtp_password
    from_addr = overrides.get("smtp_from_address") or config.smtp_from_address
    tls_str = overrides.get("smtp_use_tls", "")
    use_tls = tls_str.lower() != "false" if tls_str else config.smtp_use_tls

    if not host:
        LOGGER.error("SMTP host not configured — cannot send email to %s", to_address)
        return False

    import aiosmtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    msg = MIMEMultipart("alternative")
    msg["From"] = from_addr or "playa77@gmail.com"
    msg["To"] = to_address
    msg["Subject"] = subject
    msg.attach(MIMEText(plain_body + _PLAIN_SIGNATURE, "plain", "utf-8"))
    msg.attach(MIMEText(_HTML_WRAPPER.format(body=html_body), "html", "utf-8"))

    try:
        await aiosmtplib.send(
            msg,
            hostname=host,
            port=port,
            username=user or None,
            password=password or None,
            use_tls=use_tls,
        )
        LOGGER.info("Email sent to %s: %s", to_address, subject)
        return True
    except Exception:
        LOGGER.exception("Failed to send email to %s", to_address)
        return False


async def get_smtp_overrides_from_db(session, verbose: bool = False) -> dict:
    """Read SMTP/server config overrides from the server_config DB table."""
    try:
        from sqlalchemy import select
        result = await session.execute(select(ServerConfig))
        rows = result.scalars().all()
        return {row.key: row.value for row in rows if row.key.startswith("smtp_")}
    except Exception:
        if verbose:
            LOGGER.exception("Failed to read server_config from DB, using config defaults")
        return {}



def send_invite_email(config, to_address: str, username: str, setup_url: str, smtp_overrides: dict | None = None):
    subject = "You've been invited to Workbench"
    html = (
        f'<h2 style="font-weight:600;font-size:18px;margin-bottom:16px">You&rsquo;ve been invited</h2>'
        f"<p>{username}, you&rsquo;ve been invited to join Workbench.</p>"
        f'<p><a href="{setup_url}" style="display:inline-block;background:#60a5fa;color:#0f1117;padding:10px 20px;border-radius:4px;text-decoration:none;font-weight:600;margin:16px 0">Set up your account</a></p>'
        f'<p style="font-size:12px;color:#6b6e7d">This link expires in 7 days.</p>'
    )
    plain = (
        f"You've been invited to Workbench.\n\n"
        f"Username: {username}\n"
        f"Set up your account: {setup_url}\n\n"
        f"This link expires in 7 days."
    )
    return _send_email(config, to_address, subject, html, plain, smtp_overrides)


def send_reset_email(config, to_address: str, reset_url: str, smtp_overrides: dict | None = None):
    subject = "Reset your Workbench password"
    html = (
        f'<h2 style="font-weight:600;font-size:18px;margin-bottom:16px">Password reset</h2>'
        f"<p>Click the button below to reset your Workbench password.</p>"
        f'<p><a href="{reset_url}" style="display:inline-block;background:#60a5fa;color:#0f1117;padding:10px 20px;border-radius:4px;text-decoration:none;font-weight:600;margin:16px 0">Reset password</a></p>'
        f'<p style="font-size:12px;color:#6b6e7d">This link expires in 1 hour. If you didn&rsquo;t request this, you can ignore this email.</p>'
    )
    plain = (
        f"Reset your Workbench password:\n\n"
        f"{reset_url}\n\n"
        f"This link expires in 1 hour."
    )
    return _send_email(config, to_address, subject, html, plain, smtp_overrides)


def send_welcome_email(config, to_address: str, username: str, login_url: str, smtp_overrides: dict | None = None):
    subject = f"Welcome to Workbench, {username}"
    html = (
        f'<h2 style="font-weight:600;font-size:18px;margin-bottom:16px">Welcome, {username}</h2>'
        f"<p>Your Workbench account is ready.</p>"
        f'<p><a href="{login_url}" style="display:inline-block;background:#60a5fa;color:#0f1117;padding:10px 20px;border-radius:4px;text-decoration:none;font-weight:600;margin:16px 0">Sign in</a></p>'
    )
    plain = (
        f"Welcome to Workbench, {username}.\n\n"
        f"Your account is ready. Sign in at: {login_url}"
    )
    return _send_email(config, to_address, subject, html, plain, smtp_overrides)


def send_password_changed_email(config, to_address: str, username: str, smtp_overrides: dict | None = None):
    subject = "Your Workbench password was changed"
    html = (
        f'<h2 style="font-weight:600;font-size:18px;margin-bottom:16px">Password changed</h2>'
        f"<p>Hi {username}, your Workbench password was just changed.</p>"
        f'<p style="font-size:12px;color:#6b6e7d">If this wasn&rsquo;t you, contact your administrator immediately.</p>'
    )
    plain = (
        f"Hi {username}, your Workbench password was just changed.\n"
        f"If this wasn't you, contact your administrator immediately."
    )
    return _send_email(config, to_address, subject, html, plain, smtp_overrides)


def send_email_change_verification(config, to_address: str, username: str, verify_url: str, smtp_overrides: dict | None = None):
    subject = "Verify your new email address"
    html = (
        f'<h2 style="font-weight:600;font-size:18px;margin-bottom:16px">Verify your email</h2>'
        f"<p>Hi {username}, click the button below to confirm your new email address for Workbench.</p>"
        f'<p><a href="{verify_url}" style="display:inline-block;background:#60a5fa;color:#0f1117;padding:10px 20px;border-radius:4px;text-decoration:none;font-weight:600;margin:16px 0">Verify email</a></p>'
        f'<p style="font-size:12px;color:#6b6e7d">This link expires in 1 hour.</p>'
    )
    plain = (
        f"Hi {username}, verify your new email address:\n\n"
        f"{verify_url}\n\n"
        f"This link expires in 1 hour."
    )
    return _send_email(config, to_address, subject, html, plain, smtp_overrides)


def send_invite_accepted_email(config, to_address: str, admin_username: str, invited_username: str, invited_email: str, smtp_overrides: dict | None = None):
    subject = f"{invited_username} accepted your Workbench invitation"
    html = (
        f'<h2 style="font-weight:600;font-size:18px;margin-bottom:16px">Invitation accepted</h2>'
        f"<p>Hi {admin_username},</p>"
        f"<p><strong>{invited_username}</strong> ({invited_email}) has accepted your invitation and joined Workbench.</p>"
    )
    plain = (
        f"Hi {admin_username},\n\n"
        f"{invited_username} ({invited_email}) has accepted your invitation and joined Workbench."
    )
    return _send_email(config, to_address, subject, html, plain, smtp_overrides)
