# Changelog

All notable changes to the Workbench project.

## [Unreleased]

### Fixed
- **Debate Arena & Knowledge Base tab rendering**: Fixed JavaScript syntax errors caused by unescaped apostrophes inside single-quoted HTML strings in `debate-tab.js` (`next round's`) and `knowledge/tab.js` (`collection's`). These caused both tabs to fail with `Unexpected identifier 's'` errors, leaving them in a permanent blank/loading state.
- **Math Tutor enabled state mismatch**: `_require_enabled()` in `agents/math_tutor/agent.py` defaulted to `False`, but the tabs API (`GET /api/v1/tabs`) and agents API (`GET /api/v1/agents`) both defaulted to `True`. This caused the Math Tutor toggle to appear checked in Settings even when no DB row existed, and the actual agent endpoints returned 403 "not enabled". Changed the default to `True` for consistency.

### Added
- **News Pipeline — Per-Interest Email Recipient with Verification**: Users can now set any email address as the recipient for nightly news deliverables on a per-interest basis. A verification email with a 24-hour expiry link is sent to the recipient address. The recipient must click the public verification link (no login required) to confirm. Until verified, deliveries fall back to the user's own email address. Admin users see a warning notice on the interest card when email is not verified.
- **News Pipeline — Feed Edit**: Each feed in the feed management panel now has an "Edit" button for inline editing of name and URL (calls the existing `PATCH /feeds/{id}` endpoint).
- **News Pipeline — Interest Card Badges**: Interest cards now display the feed count badge (e.g. "3 feeds") next to the interest name and show recipient email status (verified, unverified warning) below the schedule line.
- **News Pipeline — Email Recipient UX Fixes**: The "Verify Email" button has been removed from the edit form and placed in the interest card header instead, where it appears alongside the unverified email warning. The email address is now shown in the "not verified" warning text. Email verification requires saving the recipient first — the button now sends a verification to the already-saved email.
- **News Pipeline — Verification Email SMTP Fix**: `send_verification_email` now reads SMTP settings from the `server_config` database table (admin-configured in Settings) and properly checks the send result. Previously it ignored SMTP configuration from the DB and silently returned success even when no email was sent.

### Fixed
- **News Pipeline — Feed Panel UX**: After adding or removing a feed, the feed management panel now stays open (previously it folded closed after every single operation, requiring the user to re-click "Feeds" for each feed). A background refresh re-renders the updated feed list in-place.
- **Optional dependency imports in `news_pipeline.py`**: Moved `import feedparser` and `import trafilatura` from module level into `_scrape()` method, fixing `ModuleNotFoundError` during pytest collection when the `[news]` optional dependencies aren't installed. The `httpx` import remains at module level since it's a core dependency.
- **News Pipeline — Email Dispatch Guard**: When `enable_email` is on but `email_recipient` is not verified, the system now correctly falls back to the user's email address (previously it used the unverified recipient address).

## [0.1.6] — 2026-06-26

### Added
- **Full System Backup/Restore**: New `workbench backup` and `workbench restore` CLI commands that dump the entire PostgreSQL database (via `pg_dump`) and the `/app/data` directory into a single compressed `.tar.gz` archive. Includes a manifest with encryption key SHA-256 fingerprint for mismatch detection. Restore drops the public schema, restores from dump, and copies back data files.
- **Per-User Export/Import Architecture** (`BackupService`): Designed but not yet exposed via API. `export_user_data()` exports every piece of data owned by a single user (API keys masked, never cleartext). `import_user_data()` supports three merge strategies: `upsert`, `skip_existing`, `replace`. Normal users can only export/import their own data; admins may target any user.
- **Per-Agent Export/Import Architecture** (`BackupService`): Designed but not yet exposed via API. `export_agent_data()` exports all sessions, reports, and settings for a specific agent type, scoped to one user or all users. Useful for migrating agent-specific content without touching unrelated data.
- **Backup Bind Mount**: `/app/backups` in the container is mounted to `./backups` on the host so backup archives survive container recreation.
- **Docker**: Added `postgresql-client` to the Docker image for `pg_dump` and `psql` CLI tools.

### Changed
- **PostgreSQL Storage: Named Volume → Bind Mount**: The `db` service now uses `./pgdata:/var/lib/postgresql/data` (host bind mount) instead of the `pgdata` Docker named volume. This ensures ALL user data survives any Docker Compose lifecycle operation including `docker compose down -v`. Previously, `-v` would irreversibly destroy the entire database volume. The `pgdata/` directory is already in `.gitignore`.
- **Docker Compose**: Added `./backups:/app/backups` volume mount. Removed `pgdata` from the `volumes:` block. Kept `openwebui_data` as a named volume (no user-owned data stored there).

## [0.1.5] — 2026-06-24

### Added
- **Enhanced Tooltip System**: Every actionable UI element (~155 across 12 component files) now has `data-tooltip` attributes providing verbose, context-aware descriptions. A `?` help icon in each tooltip opens a dedicated help page in a new browser tab. Tooltips support both dark and light themes with smooth fade-in animation.
- **14 Help Pages**: Comprehensive documentation at `/static/help/` covering every feature area: Login & Account, Settings, Chat, News Pipeline, Debate Arena, Deep Research, Consigliere/Deliberation, Strategic Planning, Session History, Blog/Publishing Hub, Math Tutor, Knowledge Base, Open WebUI, and a master Help Index.
- **Tooltip CSS Module** (`css/tooltips.css`): Styled bubble with placement-aware arrow, help-link badge, shortcut hint, and responsive viewport clamping. Light/dark theme variables.
- **Tooltip JS Engine** (`js/tooltips.js`): Hover-based tooltip rendering with `?` key/F1 keyboard shortcut for fast help access. Tooltip stays visible while hovering over it. Viewport-aware positioning (flips to below element when near top edge).
- **Help index page**: Central hub linking to all 13 feature help pages with description cards.
- **Docker static file mounts**: Volume mounts for `src/workbench/webui/static` and agent plugin static dirs in `docker-compose.yml` enable hot-reload of frontend files without rebuilding the Docker image.

### Changed
- **index.html**: Now loads `css/tooltips.css` and `js/tooltips.js`. Header icon buttons (Sign out, Theme toggle, Settings) have `data-tooltip` and `data-help-page` attributes alongside their existing `title` fallbacks.
- **docker-compose.yml**: Added volume mounts for static files and agent plugin directories for zero-downtime frontend updates.
- All component JS files annotated with tooltip/help attributes on every button, input, select, textarea, toggle, and link element.

### Infrastructure
- **TLS/HTTPS**: nginx reverse proxy configured for `workbench.gronowski.cc` with Let's Encrypt certificate. HTTP→HTTPS redirect, HSTS header, and security headers enabled.
- **nginx site config**: Proxies `/` to `workbench:8420` and `/open-webui/` to Open WebUI with sub_filter path rewriting.
- **Server**: Deployed to VPS at 37.60.240.152 via Docker Compose with PostgreSQL 16 and Open WebUI containers.



### Changed
- **Complete Button CSS Rewrite**: Every button now has distinct, perceivable states across all 7 transition properties (background, border-color, color, transform, box-shadow, filter, opacity). Hover shows `brightness(1.12)` + colored box-shadow glow. Active/pressed shows `brightness(0.82)` + `scale(0.96)` + inset shadow. Disabled has `grayscale(0.5)`. Keyboard focus gets `outline: 2px solid var(--accent)`. Added `.btn-success` and `.btn-warning` variant classes (previously used in JS but undefined in CSS).

### Added
- **Logout Button in Header**: "Sign Out" icon button now lives in the header bar (right side, next to theme/settings icons). No longer buried exclusively at the bottom of the Settings page.

### Fixed
- **Consigliere Synthesis Crash**: The `_generate_synthesis` method was calling `_safe_json_parse()` on prose Markdown output (the synthesis is structured prose, not JSON). This threw `json.JSONDecodeError` on every run with enabled synthesis, causing the entire deliberation pipeline to fail at the final step. Removed the erroneous JSON parse — synthesis returns prose directly now.
- **Strategic Planning completed event missing content**: The SSE `completed` event only sent `content_length` and `elapsed_seconds` — never the actual plan text. Frontend received `renderPlanResult('')` with empty content, making Copy/Export/PDF buttons do nothing. Now includes `"content": content` in the completed event.
- **Debate End Debate button active after completion**: The "End Debate" button was always enabled regardless of debate status. Now it transforms to "Back to Setup" (secondary style) when the debate completes.
- **News Pipeline feed & interest management**: Interest cards now have "Edit" and "Feeds" buttons. Edit opens a pre-filled form for all interest settings. Feeds opens an inline panel to list/add/delete RSS/Atom feeds per interest. Previously there was zero UI to manage feeds or edit interests after creation.
- **Settings Theme Toggle**: The "Switch to Light/Dark Theme" button in Settings > Themes now actually works. It switches the theme immediately AND updates the button label to reflect the new state. Previously the button called `renderSettings` with the wrong container element (`#active-tab-content` instead of `#settings-panel`), causing the re-render to go to a hidden element — no visual feedback and no button label update. Also simplified: instead of re-rendering the entire settings panel (which destroyed/recreated every element and event listener), the click handler now directly updates `this.textContent` after toggling, providing instant feedback with no side effects.
- **Same bug in Brave Key handlers**: Both save and delete Brave key handlers also called `renderSettings` on the wrong container. Fixed from `#active-tab-content` to `#settings-panel`.
- **Tooltip MutationObserver scope bug**: The MutationObserver that watches for dynamically-added `[data-tooltip]` elements (tab panels rendered after initial DOMContentLoaded) was defined outside the `Tooltips` IIFE, so its callback could not access the private `attach()` function. Tooltips on dynamically-rendered tab content (Chat, Debate, Research, News, Planning, Deliberation, Blog, OpenWebUI, History) never worked. Fixed by moving the MutationObserver setup inside the IIFE where it has lexical access to `attach()`. The observer now successfully attaches tooltip event listeners (`mouseenter`, `mouseleave`, `focus`, `blur`, `keydown`) to all elements with `data-tooltip` attributes that are inserted into the DOM after page load. Verified on live Chat tab — all 4 tooltip-equipped elements (model selector, text input, send button, past sessions toggle) graduate from zero tooltips to fully functional tooltips with text, `?` help link, keyboard shortcut, and correct help page routing.
- **Tooltips.js version bump**: 1.0.0 → 1.1.0.

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
