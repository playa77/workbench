# Changelog

All notable changes to the Workbench project.

## [0.1.2] — 2026-06-24

### Added
- **API Key Masking**: Inference provider API keys (OpenRouter, OpenAI, etc.) now display as masked strings (`sk-or-...xyz`) in Settings instead of just a boolean indicator. Brave Search API key also shows its masked form. Standard GUI pattern — first 6 and last 3 characters visible.
- **Database Migration**: Added `api_key_masked` to `workbench_inference_providers` and `masked_key` to `workbench_brave_keys`.

### Fixed
- **Button Visual Feedback**: ~25 async buttons across all tabs now show loading/success states. Includes: Delete Brave key, Delete API key, Revoke invite, Agent toggles, Logout, Debate Pause/Resume/Inject, Pipeline Run/Delete/Load, Math Tutor start/send/end, Knowledge Base create/delete/query, clipboard copy toasts, History delete session, and more. All use consistent `Utils.setButtonLoading/resetButton/setButtonSuccess` pattern.

## [0.1.1] — 2026-06-24

### Fixed
- **History Tab Navigation**: Added `history.pushState`/`popstate` for browser back/forward support. Clicking the History tab now always returns to the list view (via `Router.onActivate`). "Back to List" button moved to the top of the session detail view with a left-arrow icon for visibility.
- **PDF Export Feedback**: Fixed loading indicator on PDF buttons in the history list — now disables the specific clicked button and shows "Generating PDF..." instead of silently failing. Export function returns a promise for proper chaining.
- **Template Selector Label**: Added visible "PDF Style:" label next to the template dropdown in the history filter row.
- **Tab Overlap**: Added `display: none` as the default CSS for `.tab-panel` to prevent layout leaks. Added `onActivate` callback support in Router for tab re-activation handling.
- **Settings Layout**: Password change, invite users, Brave key, and email config sections now use a responsive grid layout (3-column `auto-fill`) instead of full-width single-column. Added `.settings-grid` CSS class and `.settings-field-limited` for constrained input widths.

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
