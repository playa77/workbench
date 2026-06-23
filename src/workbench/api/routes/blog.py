"""Blog / Publishing Hub routes.

Public pages (no auth):
  GET  /blog/{username}              — user's blog listing
  GET  /blog/{username}/{slug}       — single post page
  GET  /blog/{username}/{slug}/raw   — raw file download

Authenticated API (management):
  GET    /api/v1/blog/posts           — list own posts
  POST   /api/v1/blog/posts           — create (multipart or JSON)
  GET    /api/v1/blog/posts/{id}      — get post
  PUT    /api/v1/blog/posts/{id}      — update post
  DELETE /api/v1/blog/posts/{id}      — delete post

Git history (authenticated):
  GET /api/v1/blog/posts/{id}/history         — commit log for file
  GET /api/v1/blog/posts/{id}/history/{hash}  — file at specific commit
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, FileResponse, Response
from fastapi.templating import Jinja2Templates
from jinja2 import Environment, select_autoescape
from markdown import markdown
from pydantic import BaseModel, Field
from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from workbench.core.auth import get_current_user
from workbench.core.db import get_session
from workbench.core.models import BlogPost, User

logger = logging.getLogger(__name__)

# ---- Jinja2 Templates ----
# Try source tree relative to cwd (Docker WORKDIR=/app), then relative to this file (dev)
_templates_dir = Path.cwd() / "src" / "workbench" / "webui" / "templates"
if not _templates_dir.exists():
    _templates_dir = Path(__file__).resolve().parent.parent.parent / "webui" / "templates"
templates = Jinja2Templates(directory=str(_templates_dir))

router = APIRouter()

# ---- Constants ----
MAX_COMMENT_LENGTH = 2048
BLOG_DATA_DIR = "data/blog"

# ---- Helpers ----

def _slugify(title: str) -> str:
    """Generate a URL-safe slug from a title."""
    slug = title.lower().strip()
    slug = re.sub(r'[^a-z0-9]+', '-', slug)
    slug = slug.strip('-')
    return slug[:300] if slug else "untitled"


def _sanitize_html(content: str) -> str:
    """Strip script tags and event handlers from HTML. Minimal, no extra deps."""
    # Remove <script>...</script> tags
    content = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.DOTALL | re.IGNORECASE)
    # Remove on* event attributes
    content = re.sub(r'\s+on\w+\s*=\s*"[^"]*"', '', content, flags=re.IGNORECASE)
    content = re.sub(r"\s+on\w+\s*=\s*'[^']*'", '', content, flags=re.IGNORECASE)
    # Remove javascript: URLs
    content = re.sub(r'href\s*=\s*["\']javascript:[^"\']*["\']', '', content, flags=re.IGNORECASE)
    return content


def _render_content(content: str, fmt: str) -> str:
    """Render content to HTML based on format."""
    if fmt == "markdown":
        return markdown(content, extensions=["fenced_code", "tables", "codehilite", "toc"])
    elif fmt == "html":
        return _sanitize_html(content)
    return _sanitize_html(content)


def _detect_format(filename: str) -> str:
    """Detect format from file extension."""
    ext = Path(filename).suffix.lower()
    if ext in (".md", ".markdown"):
        return "markdown"
    elif ext in (".html", ".htm"):
        return "html"
    elif ext == ".pdf":
        return "pdf"
    return "markdown"


# ---- Git Helpers ----

def _blog_dir(user_id: str) -> Path:
    """Get the blog data directory for a user."""
    return Path(BLOG_DATA_DIR) / user_id


def _init_git_repo(user_dir: Path) -> None:
    """Initialize a git repo if one doesn't exist."""
    if not (user_dir / ".git").exists():
        user_dir.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "init"],
            cwd=str(user_dir),
            capture_output=True,
            check=False,
        )
        # Set git user identity for commits (required by git)
        subprocess.run(
            ["git", "config", "user.email", "blog@workbench.local"],
            cwd=str(user_dir),
            capture_output=True,
            check=False,
        )
        subprocess.run(
            ["git", "config", "user.name", "Workbench Blog"],
            cwd=str(user_dir),
            capture_output=True,
            check=False,
        )
        logger.info("Initialized git repo at %s", user_dir)


def _git_commit(user_dir: Path, filename: str, message: str) -> None:
    """Stage and commit a file."""
    subprocess.run(
        ["git", "add", filename],
        cwd=str(user_dir),
        capture_output=True,
        check=False,
    )
    subprocess.run(
        ["git", "commit", "-m", message],
        cwd=str(user_dir),
        capture_output=True,
        check=False,
    )


def _git_rm(user_dir: Path, filename: str, message: str) -> None:
    """Remove a file and commit the removal."""
    subprocess.run(
        ["git", "rm", filename],
        cwd=str(user_dir),
        capture_output=True,
        check=False,
    )
    subprocess.run(
        ["git", "commit", "-m", message],
        cwd=str(user_dir),
        capture_output=True,
        check=False,
    )


def _git_history(user_dir: Path, filename: str) -> list[dict]:
    """Get commit history for a file."""
    result = subprocess.run(
        ["git", "log", "--format=%H|%s|%aI", "--", filename],
        cwd=str(user_dir),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return []
    commits = []
    for line in result.stdout.strip().split("\n"):
        parts = line.split("|", 2)
        if len(parts) == 3:
            commits.append({
                "hash": parts[0],
                "message": parts[1],
                "date": parts[2],
            })
    return commits


def _git_show(user_dir: Path, filename: str, commit_hash: str) -> str | None:
    """Get file content at a specific commit."""
    result = subprocess.run(
        ["git", "show", f"{commit_hash}:{filename}"],
        cwd=str(user_dir),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout


# ---- Pydantic Models ----

class BlogPostCreate(BaseModel):
    title: str = Field(..., max_length=300)
    comment: str | None = Field(None, max_length=MAX_COMMENT_LENGTH)
    format: str = "markdown"
    content: str | None = None  # Inline content (if no file upload)
    is_published: bool = False


class BlogPostUpdate(BaseModel):
    title: str | None = Field(None, max_length=300)
    comment: str | None = Field(None, max_length=MAX_COMMENT_LENGTH)
    format: str | None = None
    content: str | None = None
    is_published: bool | None = None


class BlogPostSummary(BaseModel):
    id: str
    title: str
    slug: str
    format: str
    is_published: bool
    comment: str | None
    created_at: str
    updated_at: str


class BlogPostDetail(BlogPostSummary):
    filename: str
    content: str | None = None


# ---- Public Routes (no auth) ----

@router.get("/blog/{username}")
async def blog_index(request: Request, username: str):
    """Public blog listing for a user."""
    # We need a sync DB session for this. We'll use the async session factory.
    from workbench.core.db import get_session_factory

    session_factory = get_session_factory()
    async with session_factory() as session:
        # Find the user
        result = await session.execute(
            select(User).where(User.username == username)
        )
        user = result.scalar_one_or_none()
        if not user:
            return HTMLResponse(
                content="<h1>User not found</h1>",
                status_code=404,
            )

        # Get published posts
        result = await session.execute(
            select(BlogPost)
            .where(BlogPost.user_id == user.id, BlogPost.is_published == True)
            .order_by(BlogPost.updated_at.desc())
        )
        posts = result.scalars().all()

        return templates.TemplateResponse(
            request=request,
            name="blog_index.html",
            context={
                "username": user.username,
                "posts": [
                    {
                        "title": p.title,
                        "slug": p.slug,
                        "format": p.format,
                        "comment": p.comment,
                        "updated_at": p.updated_at.isoformat() if p.updated_at else "",
                        "comment_rendered": _render_content(p.comment or "", "markdown") if p.comment else "",
                    }
                    for p in posts
                ],
            },
        )


@router.get("/blog/{username}/{slug}")
async def blog_post(request: Request, username: str, slug: str):
    """Public single post view."""
    from workbench.core.db import get_session_factory

    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            select(User).where(User.username == username)
        )
        user = result.scalar_one_or_none()
        if not user:
            return HTMLResponse(content="<h1>User not found</h1>", status_code=404)

        result = await session.execute(
            select(BlogPost).where(
                BlogPost.user_id == user.id,
                BlogPost.slug == slug,
                BlogPost.is_published == True,
            )
        )
        post = result.scalar_one_or_none()
        if not post:
            return HTMLResponse(content="<h1>Post not found</h1>", status_code=404)

        # Render content
        rendered_content = ""
        is_pdf = post.format == "pdf"
        if not is_pdf:
            user_dir = _blog_dir(str(user.id))
            filepath = user_dir / post.filename
            if filepath.exists():
                raw_content = filepath.read_text()
                rendered_content = _render_content(raw_content, post.format)
            else:
                rendered_content = "<p><em>File not found.</em></p>"

        comment_rendered = _render_content(post.comment or "", "markdown") if post.comment else ""

        return templates.TemplateResponse(
            request=request,
            name="blog_post.html",
            context={
                "username": user.username,
                "post": {
                    "title": post.title,
                    "slug": post.slug,
                    "format": post.format,
                    "comment": post.comment,
                    "created_at": post.created_at.isoformat() if post.created_at else "",
                    "updated_at": post.updated_at.isoformat() if post.updated_at else "",
                },
                "content": rendered_content,
                "comment_rendered": comment_rendered,
                "is_pdf": is_pdf,
            },
        )


@router.get("/blog/{username}/{slug}/raw")
async def blog_raw(request: Request, username: str, slug: str):
    """Serve the raw file for download (PDFs, source files)."""
    from workbench.core.db import get_session_factory

    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            select(User).where(User.username == username)
        )
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        result = await session.execute(
            select(BlogPost).where(
                BlogPost.user_id == user.id,
                BlogPost.slug == slug,
                BlogPost.is_published == True,
            )
        )
        post = result.scalar_one_or_none()
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")

        user_dir = _blog_dir(str(user.id))
        filepath = user_dir / post.filename

        if not filepath.exists():
            raise HTTPException(status_code=404, detail="File not found")

        media_type_map = {
            "markdown": "text/markdown",
            "html": "text/html",
            "pdf": "application/pdf",
        }
        media_type = media_type_map.get(post.format, "application/octet-stream")

        return FileResponse(
            path=str(filepath),
            filename=post.filename,
            media_type=media_type,
        )


# ---- Authenticated API Routes ----

@router.get("/api/v1/blog/posts", response_model=list[BlogPostSummary])
async def list_blog_posts(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """List all posts for the current user."""
    result = await session.execute(
        select(BlogPost)
        .where(BlogPost.user_id == user.id)
        .order_by(BlogPost.updated_at.desc())
    )
    posts = result.scalars().all()
    return [
        BlogPostSummary(
            id=str(p.id),
            title=p.title,
            slug=p.slug,
            format=p.format,
            is_published=p.is_published,
            comment=p.comment,
            created_at=p.created_at.isoformat() if p.created_at else "",
            updated_at=p.updated_at.isoformat() if p.updated_at else "",
        )
        for p in posts
    ]


@router.post("/api/v1/blog/posts", response_model=BlogPostDetail)
async def create_blog_post(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    title: str = Form(...),
    comment: str | None = Form(None, max_length=MAX_COMMENT_LENGTH),
    format: str = Form("markdown"),
    is_published: bool = Form(False),
    content: str | None = Form(None),
    file: UploadFile | None = File(None),
):
    """Create a new blog post. Supports file upload OR inline content."""
    # Validate
    if not title or not title.strip():
        raise HTTPException(status_code=400, detail="Title is required")

    if file and file.filename:
        # File upload
        fmt = _detect_format(file.filename)
        slug = _slugify(title)
        ext = Path(file.filename).suffix or (".md" if fmt == "markdown" else ".html")
        filename = f"{slug}{ext}"

        # Check slug uniqueness
        existing = await session.execute(
            select(BlogPost).where(BlogPost.user_id == user.id, BlogPost.slug == slug)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="A post with this title already exists")

        user_dir = _blog_dir(str(user.id))
        _init_git_repo(user_dir)
        filepath = user_dir / filename
        file_content = await file.read()
        filepath.write_bytes(file_content)
        _git_commit(user_dir, filename, f"{slug}: create")
        content_value = None
    elif content is not None and content.strip():
        # Inline content
        fmt = format if format in ("markdown", "html", "pdf") else "markdown"
        slug = _slugify(title)
        ext_map = {"markdown": ".md", "html": ".html", "pdf": ".pdf"}
        ext = ext_map.get(fmt, ".md")
        filename = f"{slug}{ext}"

        existing = await session.execute(
            select(BlogPost).where(BlogPost.user_id == user.id, BlogPost.slug == slug)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="A post with this title already exists")

        user_dir = _blog_dir(str(user.id))
        _init_git_repo(user_dir)
        filepath = user_dir / filename
        filepath.write_text(content)
        _git_commit(user_dir, filename, f"{slug}: create")
        content_value = content
    else:
        raise HTTPException(status_code=400, detail="Either file or content must be provided")

    post = BlogPost(
        id=uuid4(),
        user_id=user.id,
        title=title.strip(),
        slug=slug,
        filename=filename,
        comment=comment[:MAX_COMMENT_LENGTH] if comment else None,
        format=fmt,
        is_published=is_published,
    )
    session.add(post)
    await session.commit()
    await session.refresh(post)

    return BlogPostDetail(
        id=str(post.id),
        title=post.title,
        slug=post.slug,
        filename=post.filename,
        format=post.format,
        is_published=post.is_published,
        comment=post.comment,
        created_at=post.created_at.isoformat() if post.created_at else "",
        updated_at=post.updated_at.isoformat() if post.updated_at else "",
        content=content_value,
    )


@router.get("/api/v1/blog/posts/{post_id}", response_model=BlogPostDetail)
async def get_blog_post(
    post_id: str,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Get a single blog post."""
    result = await session.execute(
        select(BlogPost).where(
            BlogPost.id == UUID(post_id),
            BlogPost.user_id == user.id,
        )
    )
    post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    # Read file content for display
    content = None
    user_dir = _blog_dir(str(user.id))
    filepath = user_dir / post.filename
    if filepath.exists() and post.format != "pdf":
        content = filepath.read_text()

    return BlogPostDetail(
        id=str(post.id),
        title=post.title,
        slug=post.slug,
        filename=post.filename,
        format=post.format,
        is_published=post.is_published,
        comment=post.comment,
        created_at=post.created_at.isoformat() if post.created_at else "",
        updated_at=post.updated_at.isoformat() if post.updated_at else "",
        content=content,
    )


@router.put("/api/v1/blog/posts/{post_id}", response_model=BlogPostDetail)
async def update_blog_post(
    post_id: str,
    body: BlogPostUpdate,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Update a blog post. Writes file content if provided."""
    result = await session.execute(
        select(BlogPost).where(
            BlogPost.id == UUID(post_id),
            BlogPost.user_id == user.id,
        )
    )
    post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    user_dir = _blog_dir(str(user.id))

    # Update title → regenerate slug if title changed
    if body.title is not None and body.title != post.title:
        new_slug = _slugify(body.title)
        # Check slug not taken (by other posts)
        existing = await session.execute(
            select(BlogPost).where(
                BlogPost.user_id == user.id,
                BlogPost.slug == new_slug,
                BlogPost.id != UUID(post_id),
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Another post with this title exists")
        post.title = body.title.strip()
        post.slug = new_slug

    # Update content if provided
    if body.content is not None:
        filepath = user_dir / post.filename
        filepath.write_text(body.content)
        _git_commit(user_dir, post.filename, f"{post.slug}: update")

    # Update format if provided
    if body.format is not None:
        post.format = body.format

    # Update comment
    if body.comment is not None:
        post.comment = body.comment[:MAX_COMMENT_LENGTH]

    # Update published state
    if body.is_published is not None:
        post.is_published = body.is_published

    await session.commit()
    await session.refresh(post)

    return BlogPostDetail(
        id=str(post.id),
        title=post.title,
        slug=post.slug,
        filename=post.filename,
        format=post.format,
        is_published=post.is_published,
        comment=post.comment,
        created_at=post.created_at.isoformat() if post.created_at else "",
        updated_at=post.updated_at.isoformat() if post.updated_at else "",
        content=None,
    )


@router.delete("/api/v1/blog/posts/{post_id}")
async def delete_blog_post(
    post_id: str,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Delete a blog post and remove its file from git."""
    result = await session.execute(
        select(BlogPost).where(
            BlogPost.id == UUID(post_id),
            BlogPost.user_id == user.id,
        )
    )
    post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    user_dir = _blog_dir(str(user.id))
    filepath = user_dir / post.filename
    if filepath.exists():
        _git_rm(user_dir, post.filename, f"{post.slug}: delete")

    await session.delete(post)
    await session.commit()
    return {"status": "ok"}


# ---- Git History Routes ----

@router.get("/api/v1/blog/posts/{post_id}/history")
async def get_post_history(
    post_id: str,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Get git history for a blog post."""
    result = await session.execute(
        select(BlogPost).where(
            BlogPost.id == UUID(post_id),
            BlogPost.user_id == user.id,
        )
    )
    post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    user_dir = _blog_dir(str(user.id))
    history = _git_history(user_dir, post.filename)
    return {"filename": post.filename, "commits": history}


@router.get("/api/v1/blog/posts/{post_id}/history/{commit_hash}")
async def get_post_at_commit(
    post_id: str,
    commit_hash: str,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Get blog post content at a specific git commit."""
    result = await session.execute(
        select(BlogPost).where(
            BlogPost.id == UUID(post_id),
            BlogPost.user_id == user.id,
        )
    )
    post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    user_dir = _blog_dir(str(user.id))
    content = _git_show(user_dir, post.filename, commit_hash)
    if content is None:
        raise HTTPException(status_code=404, detail="Commit not found")

    return {"commit_hash": commit_hash, "filename": post.filename, "content": content}
