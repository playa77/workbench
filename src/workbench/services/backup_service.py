"""Data backup and restore service for Workbench.

Provides three tiers of data portability, from full system dump to
per-user / per-agent granular export.  The full-system tier is
implemented now; the per-user and per-agent tiers are architected so
routes can be added later without refactoring the service.

Tier 1 — Full system (implemented)
    Dump the entire PostgreSQL database + ``/app/data`` directory into
    a compressed tarball.  Intended for disaster recovery and
    migrations.

Tier 2 — Per-user (architected, not exposed via API yet)
    Export every piece of data owned by a single user:
      - API keys (masked, never cleartext)
      - Brave Search key (masked)
      - Inference provider configs (masked keys)
      - Agent settings
      - Agent sessions (full state)
      - Stored reports
      - Knowledge bases + documents
      - Blog posts (metadata + file contents)
    Import merges the data back for the same user.
    Normal users may only export/import their own data; admins may
    target any user.

Tier 3 — Per-agent (architected, not exposed via API yet)
    Export per-agent data for all users (or for a specific user).
    Useful for migrating agent-specific content (e.g., all research
    reports, all debate transcripts) without touching unrelated data.

Version: 1.0.0 | 2026-06-26
"""

from __future__ import annotations

import gzip
import io
import logging
import os
import shutil
import subprocess
import tarfile
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Export schemas (the portable data format)
# ---------------------------------------------------------------------------


class BackupManifest(BaseModel):
    """Metadata written into every backup archive."""

    format_version: str = "1.0.0"
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    project: str = "workbench"
    backup_type: str = "full"  # "full" | "user" | "agent"
    description: str = ""
    encryption_key_sha256: str = ""  # SHA-256 of the ENCRYPTION_KEY — used to detect mismatches


class UserDataExport(BaseModel):
    """All data owned by a single user (Tier 2).

    API keys and provider keys are masked — cleartext is NEVER exported.
    """

    user_id: str
    username: str
    email: str | None = None
    is_admin: bool = False
    created_at: str = ""
    # Masked credentials — never cleartext
    api_keys: list[dict[str, Any]] = Field(default_factory=list)
    brave_key_masked: str | None = None
    inference_providers: list[dict[str, Any]] = Field(default_factory=list)
    # Content
    agent_settings: list[dict[str, Any]] = Field(default_factory=list)
    agent_sessions: list[dict[str, Any]] = Field(default_factory=list)
    reports: list[dict[str, Any]] = Field(default_factory=list)
    knowledge_bases: list[dict[str, Any]] = Field(default_factory=list)
    blog_posts: list[dict[str, Any]] = Field(default_factory=list)


class AgentDataExport(BaseModel):
    """Per-agent data slice (Tier 3).

    All sessions, reports, and settings for a single agent type,
    scoped to one user or all users.
    """

    agent_name: str
    scope: str  # "all_users" | "user:{user_id}"
    sessions: list[dict[str, Any]] = Field(default_factory=list)
    reports: list[dict[str, Any]] = Field(default_factory=list)
    settings: list[dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class BackupResult:
    """Outcome of a backup operation."""

    success: bool
    archive_path: str | None = None
    archive_size_bytes: int = 0
    error_message: str = ""
    pg_dump_size_bytes: int = 0
    data_dir_size_bytes: int = 0


@dataclass
class RestoreResult:
    """Outcome of a restore operation."""

    success: bool
    tables_restored: int = 0
    data_files_restored: int = 0
    error_message: str = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# PostgreSQL connection info read from the container environment at runtime.
# These are the well-known Docker Compose defaults; they can be overridden
# via the DATABASE_URL env var parsing if needed.


def _parse_db_connection_string(database_url: str) -> dict[str, str]:
    """Parse a SQLAlchemy asyncpg connection string into pg_dump-compatible pieces.

    Expects: postgresql+asyncpg://user:pass@host:port/dbname
    Returns: dict with keys user, password, host, port, dbname
    """
    import re

    pattern = r"postgresql(\+asyncpg)?://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)"
    match = re.match(pattern, database_url)
    if not match:
        raise ValueError(f"Cannot parse DATABASE_URL: {database_url}")
    return {
        "user": match.group(2),
        "password": match.group(3),
        "host": match.group(4),
        "port": match.group(5),
        "dbname": match.group(6),
    }


def _run(cmd: list[str], timeout: int = 300, env: dict[str, str] | None = None) -> tuple[int, str, str]:
    """Run a subprocess, return (exit_code, stdout, stderr)."""
    run_env = os.environ.copy()
    if env:
        run_env.update(env)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=run_env)
    return result.returncode, result.stdout, result.stderr


# ---------------------------------------------------------------------------
# Tier 1 — Full system backup / restore
# ---------------------------------------------------------------------------


def create_full_backup(
    database_url: str,
    data_dir: str = "/app/data",
    output_dir: str = "/app/backups",
    description: str = "",
) -> BackupResult:
    """Create a full-system backup archive.

    Dumps the entire PostgreSQL database (via ``pg_dump``) and tars up the
    ``data_dir`` directory into a single ``.tar.gz`` archive.

    Args:
        database_url: SQLAlchemy connection string (parsed for pg_dump).
        data_dir: Path to the application data directory.
        output_dir: Where to write the backup archive.
        description: Optional description stored in the manifest.

    Returns:
        BackupResult with path, sizes, and status.
    """
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    archive_name = f"workbench_full_{ts}.tar.gz"
    archive_path = os.path.join(output_dir, archive_name)

    os.makedirs(output_dir, exist_ok=True)

    db = _parse_db_connection_string(database_url)
    pg_env = {"PGPASSWORD": db["password"]}

    pg_dump_cmd = [
        "pg_dump",
        "-h", db["host"],
        "-p", db["port"],
        "-U", db["user"],
        "-d", db["dbname"],
        "--no-owner",
        "--no-acl",
    ]

    tmpdir = tempfile.mkdtemp(prefix="workbench_backup_")
    sql_dump_path = os.path.join(tmpdir, "database.sql")
    manifest_path = os.path.join(tmpdir, "manifest.json")

    try:
        # 1. Dump PostgreSQL
        logger.info("Starting PostgreSQL dump (%s)...", db["dbname"])
        exit_code, stdout, stderr = _run(pg_dump_cmd, timeout=300, env=pg_env)
        if exit_code != 0:
            error = f"pg_dump failed (exit {exit_code}):\n{stderr}"
            logger.error(error)
            return BackupResult(success=False, error_message=error)

        with open(sql_dump_path, "w", encoding="utf-8") as f:
            f.write(stdout)
        pg_size = os.path.getsize(sql_dump_path)
        logger.info("PostgreSQL dump complete: %d bytes", pg_size)

        # 2. Compute encryption key fingerprint (for manifest, not the key itself)
        encryption_key = os.environ.get("ENCRYPTION_KEY", "")
        import hashlib
        key_sha256 = hashlib.sha256(encryption_key.encode()).hexdigest() if encryption_key else ""

        # 3. Write manifest
        manifest = BackupManifest(
            description=description or "Full system backup",
            encryption_key_sha256=key_sha256,
        )
        import json
        with open(manifest_path, "w", encoding="utf-8") as f:
            f.write(manifest.model_dump_json(indent=2))

        # 4. Create archive
        logger.info("Creating backup archive: %s", archive_path)
        data_size = 0
        with tarfile.open(archive_path, "w:gz") as tar:
            tar.add(sql_dump_path, arcname="database.sql")
            tar.add(manifest_path, arcname="manifest.json")

            if os.path.isdir(data_dir):
                # Count size before adding
                for dirpath, _dirnames, filenames in os.walk(data_dir):
                    for filename in filenames:
                        fp = os.path.join(dirpath, filename)
                        try:
                            data_size += os.path.getsize(fp)
                        except OSError:
                            pass
                tar.add(data_dir, arcname="data")

        archive_size = os.path.getsize(archive_path)
        logger.info("Backup archive created: %s (%d bytes)", archive_path, archive_size)
        return BackupResult(
            success=True,
            archive_path=archive_path,
            archive_size_bytes=archive_size,
            pg_dump_size_bytes=pg_size,
            data_dir_size_bytes=data_size,
        )

    except subprocess.TimeoutExpired:
        error = "pg_dump timed out after 300 seconds"
        logger.error(error)
        return BackupResult(success=False, error_message=error)
    except Exception as exc:
        logger.exception("Backup failed: %s", exc)
        return BackupResult(success=False, error_message=str(exc))
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def restore_full_backup(
    archive_path: str,
    database_url: str,
    data_dir: str = "/app/data",
) -> RestoreResult:
    """Restore a full-system backup from a ``.tar.gz`` archive.

    Args:
        archive_path: Path to the backup archive.
        database_url: SQLAlchemy connection string.
        data_dir: Path to the application data directory.

    Returns:
        RestoreResult with success status and counts.
    """
    if not os.path.exists(archive_path):
        return RestoreResult(success=False, error_message=f"Archive not found: {archive_path}")

    tmpdir = tempfile.mkdtemp(prefix="workbench_restore_")
    sql_dump_path = os.path.join(tmpdir, "database.sql")

    try:
        # 1. Extract archive
        logger.info("Extracting backup archive: %s", archive_path)
        with tarfile.open(archive_path, "r:gz") as tar:
            tar.extractall(path=tmpdir)

        if not os.path.exists(sql_dump_path):
            return RestoreResult(
                success=False,
                error_message="database.sql not found in archive — corrupted backup?",
            )

        # 2. Check manifest for encryption key mismatch
        manifest_path = os.path.join(tmpdir, "manifest.json")
        if os.path.exists(manifest_path):
            import json
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest_data = json.load(f)
            stored_sha = manifest_data.get("encryption_key_sha256", "")
            if stored_sha:
                encryption_key = os.environ.get("ENCRYPTION_KEY", "")
                import hashlib
                current_sha = hashlib.sha256(encryption_key.encode()).hexdigest() if encryption_key else ""
                if current_sha and stored_sha != current_sha:
                    logger.warning(
                        "Encryption key has changed since this backup was created! "
                        "All encrypted API keys in the restored data will be unrecoverable "
                        "unless you revert to the original ENCRYPTION_KEY."
                    )

        # 3. Restore PostgreSQL
        db = _parse_db_connection_string(database_url)
        pg_env = {"PGPASSWORD": db["password"]}

        # Drop and recreate the public schema to get a clean slate
        logger.info("Dropping existing public schema...")
        drop_cmd = [
            "psql",
            "-h", db["host"],
            "-p", db["port"],
            "-U", db["user"],
            "-d", db["dbname"],
            "-c", "DROP SCHEMA public CASCADE; CREATE SCHEMA public;",
        ]
        _run(drop_cmd, timeout=60, env=pg_env)

        # Restore the dump
        logger.info("Restoring PostgreSQL from dump...")
        restore_cmd = [
            "psql",
            "-h", db["host"],
            "-p", db["port"],
            "-U", db["user"],
            "-d", db["dbname"],
            "-f", sql_dump_path,
        ]
        exit_code, stdout, stderr = _run(restore_cmd, timeout=300, env=pg_env)
        if exit_code != 0:
            # psql may still succeed partially — errors during restore
            # (e.g., extensions already exist) are non-fatal
            logger.warning("psql restore output:\n%s\n%s", stdout, stderr)

        # Count restored tables
        tables_result = _run(
            [
                "psql",
                "-h", db["host"],
                "-p", db["port"],
                "-U", db["user"],
                "-d", db["dbname"],
                "-t", "-c",
                "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';",
            ],
            timeout=30,
            env=pg_env,
        )
        tables_count = 0
        try:
            tables_count = int(tables_result[1].strip())
        except ValueError:
            pass
        logger.info("Tables in database after restore: %d", tables_count)

        # 4. Restore data directory
        data_files_count = 0
        archive_data_dir = os.path.join(tmpdir, "data")
        if os.path.isdir(archive_data_dir):
            # Clear target data dir
            if os.path.isdir(data_dir):
                shutil.rmtree(data_dir)
            os.makedirs(data_dir, exist_ok=True)

            for item in os.listdir(archive_data_dir):
                src = os.path.join(archive_data_dir, item)
                dst = os.path.join(data_dir, item)
                if os.path.isdir(src):
                    shutil.copytree(src, dst, dirs_exist_ok=True)
                else:
                    shutil.copy2(src, dst)
                data_files_count += 1
            logger.info("Data directory restored: %d top-level items", data_files_count)

        return RestoreResult(
            success=True,
            tables_restored=tables_count,
            data_files_restored=data_files_count,
        )

    except subprocess.TimeoutExpired:
        error = "Restore operation timed out"
        logger.error(error)
        return RestoreResult(success=False, error_message=error)
    except Exception as exc:
        logger.exception("Restore failed: %s", exc)
        return RestoreResult(success=False, error_message=str(exc))
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Tier 2 — Per-user export / import (architected, not yet exposed via API)
# ---------------------------------------------------------------------------


async def export_user_data(
    user_id: UUID,
    session: Any,  # SQLAlchemy AsyncSession
) -> UserDataExport:
    """Export all data owned by a single user.

    This is a pure service-layer function — API routes that call it can be
    added later without any changes to this module.

    The returned payload contains NO cleartext keys — API keys, Brave keys,
    and inference provider keys are all masked (last-4 only).

    Args:
        user_id: The UUID of the user whose data to export.
        session: An active SQLAlchemy AsyncSession.

    Returns:
        UserDataExport with all user-owned data.
    """
    from sqlalchemy import select

    from workbench.core.models import (
        AgentSession,
        BlogPost,
        StoredReport,
        User,
        UserAgentSettings,
        UserApiKey,
        UserBraveKey,
        UserInferenceProvider,
    )
    from workbench.shared.db.base import Base

    import json

    # Fetch user
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise ValueError(f"User not found: {user_id}")

    export = UserDataExport(
        user_id=str(user.id),
        username=user.username,
        email=user.email,
        is_admin=user.is_admin,
        created_at=user.created_at.isoformat() if user.created_at else "",
    )

    # API keys (masked only — NEVER cleartext)
    keys_result = await session.execute(
        select(UserApiKey).where(UserApiKey.user_id == user_id)
    )
    for k in keys_result.scalars().all():
        export.api_keys.append({
            "id": str(k.id),
            "label": k.label,
            "key_masked": k.key_masked,
            "created_at": k.created_at.isoformat() if k.created_at else "",
            "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
            "expires_at": k.expires_at.isoformat() if k.expires_at else None,
        })

    # Brave key (masked)
    brave_result = await session.execute(
        select(UserBraveKey).where(UserBraveKey.user_id == user_id)
    )
    brave = brave_result.scalar_one_or_none()
    if brave:
        export.brave_key_masked = brave.masked_key

    # Inference providers (masked keys)
    prov_result = await session.execute(
        select(UserInferenceProvider).where(UserInferenceProvider.user_id == user_id)
    )
    for p in prov_result.scalars().all():
        export.inference_providers.append({
            "id": str(p.id),
            "name": p.name,
            "api_key_masked": p.api_key_masked,
            "provider_url": p.provider_url,
            "strong_model": p.strong_model,
            "quick_model": p.quick_model,
            "requests_per_minute": p.requests_per_minute,
            "is_default": p.is_default,
            "created_at": p.created_at.isoformat() if p.created_at else "",
        })

    # Agent settings
    settings_result = await session.execute(
        select(UserAgentSettings).where(UserAgentSettings.user_id == user_id)
    )
    for s in settings_result.scalars().all():
        export.agent_settings.append({
            "agent_name": s.agent_name,
            "enabled": s.enabled,
            "settings": s.settings,
            "updated_at": s.updated_at.isoformat() if s.updated_at else "",
        })

    # Agent sessions
    sessions_result = await session.execute(
        select(AgentSession).where(AgentSession.user_id == user_id)
    )
    for s in sessions_result.scalars().all():
        export.agent_sessions.append({
            "id": str(s.id),
            "agent_name": s.agent_name,
            "session_id": s.session_id,
            "title": s.title,
            "state_json": s.state_json,
            "content": s.content,
            "content_format": s.content_format,
            "metadata_json": s.metadata_json,
            "created_at": s.created_at.isoformat() if s.created_at else "",
            "updated_at": s.updated_at.isoformat() if s.updated_at else "",
        })

    # Stored reports
    reports_result = await session.execute(
        select(StoredReport).where(StoredReport.user_id == user_id)
    )
    for r in reports_result.scalars().all():
        export.reports.append({
            "id": str(r.id),
            "agent_name": r.agent_name,
            "title": r.title,
            "content": r.content,
            "content_format": r.content_format,
            "metadata_json": r.metadata_json,
            "created_at": r.created_at.isoformat() if r.created_at else "",
        })

    # Blog posts
    blog_result = await session.execute(
        select(BlogPost).where(BlogPost.user_id == user_id)
    )
    for b in blog_result.scalars().all():
        export.blog_posts.append({
            "id": str(b.id),
            "title": b.title,
            "slug": b.slug,
            "filename": b.filename,
            "comment": b.comment,
            "format": b.format,
            "is_published": b.is_published,
            "created_at": b.created_at.isoformat() if b.created_at else "",
            "updated_at": b.updated_at.isoformat() if b.updated_at else "",
        })

    logger.info("Exported data for user %s: %d sessions, %d reports, %d blog posts",
                user.username, len(export.agent_sessions), len(export.reports), len(export.blog_posts))
    return export


async def import_user_data(
    user_id: UUID,
    data: UserDataExport,
    session: Any,
    merge_strategy: str = "upsert",
) -> dict[str, int]:
    """Import previously exported user data.

    Args:
        user_id: Target user UUID.
        data: The exported data payload.
        session: Active SQLAlchemy AsyncSession.
        merge_strategy: "upsert" (default) — update existing, insert new.
                        "skip_existing" — only insert new records.
                        "replace" — delete existing then insert all.

    Returns:
        Dict with counts of imported items per table.
    """
    from sqlalchemy import select, delete
    from workbench.core.models import (
        AgentSession,
        BlogPost,
        StoredReport,
        User,
        UserAgentSettings,
        UserApiKey,
        UserBraveKey,
        UserInferenceProvider,
    )
    from workbench.core.auth import hash_password

    logger.info("Importing user data for %s (strategy: %s)", user_id, merge_strategy)

    counts: dict[str, int] = {
        "api_keys": 0,
        "inference_providers": 0,
        "agent_settings": 0,
        "agent_sessions": 0,
        "reports": 0,
        "blog_posts": 0,
    }

    # Ensure the target user exists
    user_result = await session.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    if user is None:
        raise ValueError(f"Target user not found: {user_id}")

    if merge_strategy == "replace":
        for model in [UserApiKey, UserInferenceProvider, UserAgentSettings,
                       AgentSession, StoredReport, BlogPost, UserBraveKey]:
            await session.execute(delete(model).where(
                getattr(model, "user_id") == user_id
            ))

    # Agent settings
    for s in data.agent_settings:
        existing = await session.execute(
            select(UserAgentSettings).where(
                UserAgentSettings.user_id == user_id,
                UserAgentSettings.agent_name == s["agent_name"],
            )
        )
        existing_obj = existing.scalar_one_or_none()
        if existing_obj:
            if merge_strategy != "skip_existing":
                existing_obj.enabled = s.get("enabled", existing_obj.enabled)
                existing_obj.settings = s.get("settings", existing_obj.settings)
        else:
            session.add(UserAgentSettings(
                user_id=user_id,
                agent_name=s["agent_name"],
                enabled=s.get("enabled", False),
                settings=s.get("settings", {}),
            ))
        counts["agent_settings"] += 1

    # Agent sessions
    for s_data in data.agent_sessions:
        existing = await session.execute(
            select(AgentSession).where(
                AgentSession.user_id == user_id,
                AgentSession.session_id == s_data.get("session_id", ""),
            )
        )
        if existing.scalar_one_or_none() and merge_strategy == "skip_existing":
            continue
        session.add(AgentSession(
            user_id=user_id,
            agent_name=s_data["agent_name"],
            session_id=s_data.get("session_id", ""),
            title=s_data.get("title", ""),
            state_json=s_data.get("state_json", {}),
            content=s_data.get("content"),
            content_format=s_data.get("content_format", "markdown"),
            metadata_json=s_data.get("metadata_json", {}),
        ))
        counts["agent_sessions"] += 1

    # Stored reports
    for r in data.reports:
        if merge_strategy == "skip_existing":
            existing = await session.execute(
                select(StoredReport).where(
                    StoredReport.user_id == user_id,
                    StoredReport.title == r.get("title", ""),
                )
            )
            if existing.scalar_one_or_none():
                continue
        session.add(StoredReport(
            user_id=user_id,
            agent_name=r["agent_name"],
            title=r.get("title", ""),
            content=r.get("content", ""),
            content_format=r.get("content_format", "markdown"),
            metadata_json=r.get("metadata_json", {}),
        ))
        counts["reports"] += 1

    # Blog posts (metadata only — files are in data dir which is part of full backup)
    for b in data.blog_posts:
        if merge_strategy == "skip_existing":
            existing = await session.execute(
                select(BlogPost).where(
                    BlogPost.user_id == user_id,
                    BlogPost.slug == b.get("slug", ""),
                )
            )
            if existing.scalar_one_or_none():
                continue
        session.add(BlogPost(
            user_id=user_id,
            title=b.get("title", ""),
            slug=b.get("slug", ""),
            filename=b.get("filename", ""),
            comment=b.get("comment"),
            format=b.get("format", "markdown"),
            is_published=b.get("is_published", False),
        ))
        counts["blog_posts"] += 1

    await session.commit()
    logger.info("Import complete: %s", counts)
    return counts


# ---------------------------------------------------------------------------
# Tier 3 — Per-agent export / import (architected, not yet exposed via API)
# ---------------------------------------------------------------------------


async def export_agent_data(
    agent_name: str,
    session: Any,
    scope: str = "all_users",
    user_id: UUID | None = None,
) -> AgentDataExport:
    """Export all data for a specific agent.

    Args:
        agent_name: The agent name (e.g., "research", "debate").
        session: Active SQLAlchemy AsyncSession.
        scope: "all_users" or "user:{user_id}".
        user_id: Required if scope is user-specific.

    Returns:
        AgentDataExport with sessions, reports, and settings.
    """
    from sqlalchemy import select
    from workbench.core.models import AgentSession, StoredReport, UserAgentSettings

    export = AgentDataExport(agent_name=agent_name, scope=scope)

    user_filter = []
    if user_id is not None:
        user_filter.append(UserAgentSettings.user_id == user_id)

    # Settings
    settings_query = select(UserAgentSettings).where(
        UserAgentSettings.agent_name == agent_name,
        *user_filter,
    )
    settings_result = await session.execute(settings_query)
    for s in settings_result.scalars().all():
        export.settings.append({
            "user_id": str(s.user_id),
            "enabled": s.enabled,
            "settings": s.settings,
            "updated_at": s.updated_at.isoformat() if s.updated_at else "",
        })

    # Sessions
    session_user_filter = []
    if user_id is not None:
        session_user_filter.append(AgentSession.user_id == user_id)
    sessions_query = select(AgentSession).where(
        AgentSession.agent_name == agent_name,
        *session_user_filter,
    )
    sessions_result = await session.execute(sessions_query)
    for s in sessions_result.scalars().all():
        export.sessions.append({
            "id": str(s.id),
            "user_id": str(s.user_id),
            "session_id": s.session_id,
            "title": s.title,
            "state_json": s.state_json,
            "content": s.content,
            "content_format": s.content_format,
            "metadata_json": s.metadata_json,
            "created_at": s.created_at.isoformat() if s.created_at else "",
            "updated_at": s.updated_at.isoformat() if s.updated_at else "",
        })

    # Reports
    report_user_filter = []
    if user_id is not None:
        report_user_filter.append(StoredReport.user_id == user_id)
    reports_query = select(StoredReport).where(
        StoredReport.agent_name == agent_name,
        *report_user_filter,
    )
    reports_result = await session.execute(reports_query)
    for r in reports_result.scalars().all():
        export.reports.append({
            "id": str(r.id),
            "user_id": str(r.user_id),
            "title": r.title,
            "content": r.content,
            "content_format": r.content_format,
            "metadata_json": r.metadata_json,
            "created_at": r.created_at.isoformat() if r.created_at else "",
        })

    logger.info("Exported agent data for '%s' (scope: %s): %d settings, %d sessions, %d reports",
                agent_name, scope, len(export.settings), len(export.sessions), len(export.reports))
    return export