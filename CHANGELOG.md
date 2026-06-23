# Changelog

All notable changes to the Workbench project.

## [0.1.0] — 2026-06-23

### Added
- **Blog / Publishing Hub**: Users can publish and manage markdown, HTML, and PDF documents.
  - Per-user git-backed versioning for all documents (transparent, no user-facing git UI)
  - Public blog page at `/blog/{username}` with auto-rendered content
  - Management UI tab with file upload, inline content editor, and per-document markdown comment/description (max 2048 chars)
  - Git history API for inspection mode (commit log, version retrieval)
  - PDF support with download cards on public pages
  - `BlogPost` database model with slug-based URLs, published/draft toggle
  - Auto-slug generation from document titles
  - HTML sanitization (script tags, event handler removal)
  - Markdown rendering via `markdown>=3.7` library
- **Dependencies**: Added `markdown>=3.7` to project dependencies
- **Docker**: Added `git` to Docker image for blog versioning backend
