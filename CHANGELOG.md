# Changelog

All notable changes to the Workbench project.

## [0.1.4] — 2026-06-24

### Changed
- **Complete Button CSS Rewrite**: Every button now has distinct, perceivable states across all 7 transition properties (background, border-color, color, transform, box-shadow, filter, opacity). Hover shows `brightness(1.12)` + colored box-shadow glow. Active/pressed shows `brightness(0.82)` + `scale(0.96)` + inset shadow. Disabled has `grayscale(0.5)`. Keyboard focus gets `outline: 2px solid var(--accent)`. Added `.btn-success` and `.btn-warning` variant classes (previously used in JS but undefined in CSS).

### Added
- **Logout Button in Header**: "Sign Out" icon button now lives in the header bar (right side, next to theme/settings icons). No longer buried exclusively at the bottom of the Settings page.

### Fixed
- **Consigliere Synthesis Crash**: The `_generate_synthesis` method was calling `_safe_json_parse()` on prose Markdown output (the synthesis is structured prose, not JSON). This threw `json.JSONDecodeError` on every run with enabled synthesis, causing the entire deliberation pipeline to fail at the final step. Removed the erroneous JSON parse — synthesis returns prose directly now.
- **Strategic Planning completed event missing content**: The SSE `completed` event only sent `content_length` and `elapsed_seconds` — never the actual plan text. Frontend received `renderPlanResult('')` with empty content, making Copy/Export/PDF buttons do nothing. Now includes `"content": content` in the completed event.
- **Debate End Debate button active after completion**: The "End Debate" button was always enabled regardless of debate status. Now it transforms to "Back to Setup" (secondary style) when the debate completes.
- **News Pipeline feed & interest management**: Interest cards now have "Edit" and "Feeds" buttons. Edit opens a pre-filled form for all interest settings. Feeds opens an inline panel to list/add/delete RSS/Atom feeds per interest. Previously there was zero UI to manage feeds or edit interests after creation.

### Fixed
- **Settings Theme Toggle**: The "Switch to Light/Dark Theme" button in Settings > Themes now actually works. It switches the theme immediately AND updates the button label to reflect the new state. Previously the button called `renderSettings` with the wrong container element (`#active-tab-content` instead of `#settings-panel`), causing the re-render to go to a hidden element — no visual feedback and no button label update. Also simplified: instead of re-rendering the entire settings panel (which destroyed/recreated every element and event listener), the click handler now directly updates `this.textContent` after toggling, providing instant feedback with no side effects.
- **Same bug in Brave Key handlers**: Both save and delete Brave key handlers also called `renderSettings` on the wrong container. Fixed from `#active-tab-content` to `#settings-panel`.

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
