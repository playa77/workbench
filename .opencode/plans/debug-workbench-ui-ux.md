# Plan: Debug Workbench UI/UX Issues

## Issue 1: History Tab Navigation

### Problem
- `viewSession()` replaces `#history-content` innerHTML with session detail, overwriting the list view
- Clicking History tab shows the detail view again instead of the list (since the existing panel is just shown as-is)
- No `pushState`/`popstate` support — browser back doesn't work
- "Back to List" button is in an unintuitive position (far right in header)

### Implementation

**File: `src/workbench/webui/static/js/router.js`**
1. Add `onActivate(name, fn)` method — registers a callback that fires when a tab is activated
2. Call `onActivateCallbacks[name]()` when `tabPanels[name]` exists and is shown (line ~70)
3. Add `destroyPanel(name)` method to fully clear and remove a panel

**File: `src/workbench/webui/static/js/components/history-tab.js`**
1. Add `_historyState` module-level variable tracking current view (`{mode: 'list'}` or `{mode: 'detail', sessionId: '...'}`)
2. Add `history.pushState()` in `viewSession()` before rendering detail
3. Add `window.addEventListener('popstate', ...)` to handle browser back
4. In `renderHistoryTab()`, register `Router.onActivate('history', showHistoryList)` — this ensures clicking the History tab always returns to the list
5. Move the "Back to List" button to the TOP of the detail view (above the title), styled as a prominent btn-secondary with a left arrow icon
6. Make the back button use `history.back()` instead of re-rendering from scratch

## Issue 2: PDF Export Unresponsive

### Problem
- `exportSessionPdf()` in `history-tab.js` calls `Utils.exportMarkdownAsPdf()`
- `exportMarkdownAsPdf()` tries `document.getElementById('btn-export-pdf')` which doesn't exist in history context → no loading indicator
- Server uses tectonic LaTeX compilation (5-15s) — no caching
- No double-click prevention

### Implementation
**File: `src/workbench/webui/static/js/components/history-tab.js`**
1. Modify `exportSessionPdf(id, title)` to:
   - Accept `btn` parameter (the button element)
   - Disable the button immediately on click, show loading state
   - Call `Utils.exportMarkdownAsPdf()` with the content
   - Re-enable button on completion or error

**File: `src/workbench/webui/static/js/utils.js`**
1. Modify `exportMarkdownAsPdf()` to optionally accept a button element parameter for loading feedback
2. If no button passed, use the existing `#btn-export-pdf` fallback

## Issue 3: Template Selector Label

**File: `src/workbench/webui/static/js/components/history-tab.js`**
- Add a `<label>` before `<span id="history-template-picker">` in the filter row: "PDF Style:"

## Issue 4: Tab Overlap

### Problem
When switching tabs, previous tab content sometimes stays visible alongside new tab content.

### Implementation
**File: `src/workbench/webui/static/js/router.js`**
1. In `setActive()`, ensure ALL existing panels get `display: 'none'` before showing the new one (already done, but verify)
2. Check if `viewSession` creates content outside the tab-panel by examining DOM — add a defensive `panel.style.display = 'none'` in `_createAndRender()`

**File: `src/workbench/webui/static/js/components/history-tab.js`**
- Ensure `viewSession()` only modifies content inside `#history-content` within the history tab panel

## Issue 5: Settings Layout

### Problem
Password change, Brave key, invite users, email config sections use full-width inputs in single-column layout.

### Implementation
**File: `src/workbench/webui/static/css/base.css`**
1. Add `.settings-grid` class: `display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 24px;`
2. Add `.settings-field` class: `max-width: 400px;` for text inputs in settings

**File: `src/workbench/webui/static/js/app.js`**
1. Wrap the form sections (password, brave, invite, email) inside a `.settings-grid` container
2. Use `max-width: 400px` on individual inputs rather than `width: 100%`
3. Keep the same card-based aesthetic as the providers section

## Issue 6: Deploy

1. `scp` or rebuild Docker image on VPS
2. `docker compose up -d --build workbench`
3. Verify nginx and certbot status
4. Test all fixes on `workbench.gronowski.cc`
