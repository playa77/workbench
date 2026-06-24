# Login Page Visual Polish — Centered Card

**Date:** 2026-06-23 | **Status:** approved

## Goal
Improve the visual quality of the login page without changing any
functionality, behavior, or JS logic.

## Approach: Centered Card

### Layout change
- The login wrapper (`#login-section` content) becomes a vertically and
  horizontally centered card in the viewport.
- CSS only: `display: flex; align-items: center; justify-content: center`
  on the parent container, with `min-height: 100vh` (or similar).
- The card has `max-width: 420px; width: 100%` so it doesn't stretch on
  large screens.

### Card styling
- `padding: 32px`, `border-radius: 12px`, subtle `box-shadow`
- Background: slightly lighter than body (`var(--bg-card)` or similar
  existing token; add one if none exists for cards).
- Card uses the existing theme variable system so dark/light themes work.

### Branding
- App title "Workbench" already exists above the card area (in navbar).
  Keep it, but optionally add a small icon/emoji or subtitle for visual
  warmth.
- No new assets — use a CSS-drawn icon or Unicode symbol.

### Typography & spacing
- Subtitle "Unified BYOK AI Workbench" stays, slightly more breathing
  room above the card.
- Input labels remain the same; group spacing stays consistent.
- Button stays full-width inside the card.

### Error state
- `#login-message` (alert-error) remains below the button inside the
  card — no structural change.

### What does NOT change
- No HTML form structure changes (forms are already present from previous fix).
- No JavaScript changes.
- No new routes, no backend changes.
- Dark/light theme toggle works exactly as before.

## Files touched
- `src/workbench/webui/static/css/base.css` — card class, centering, spacing.
- `src/workbench/webui/static/js/app.js` — possibly a `<div class="login-card">`
  wrapper in `renderLogin()` HTML template (purely visual, no JS logic).

## Verification
- Browser test login flow (Enter key, button click, error message).
- Toggle dark/light theme — card should adapt.
- Responsive: card should center on mobile, not cut off.
