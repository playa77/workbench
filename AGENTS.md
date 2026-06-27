### Project Working Guidelines

- **Verbose documentation.** Prioritize comments that explain why, not what — the code already shows what it does. Focus on non-obvious logic, design decisions, and surprising behavior. Obvious boilerplate doesn't need paragraph explanations.
- **Verbose logging.** All status and log messages must be detailed and include ISO 8601 timestamps. Emit sufficient context to make debugging straightforward without having to reproduce the issue.
- **Version every script.** Include a version comment at the top (e.g., `# Version: 1.3.2 | 2026-03-14`). Never call anything "final" — software evolves.
- **Respectful API usage.** Minimize concurrent calls. Implement sensible delays and respect rate limits. Use exponential backoff for retries.
- **No regressions.** Never remove existing functionality or UI features without explicit instruction. Flag when changes might affect existing behavior.
- **SSH via `sshpass`.** All SSH connections to remote VPS instances must use `sshpass`. Never spawn windows, dialogs, or interactive prompts on the host system.
- **Authentication failures.** If login to any remote host fails, stop immediately and ask the user for guidance. Do not retry or attempt alternative credentials without explicit instruction.
- **Python package installation.** Never use `--break-system-packages` (or equivalent flags) with `pip`. Always use a virtual environment. Create one venv per project directory (e.g., `./venv/`) and reuse it across tasks within that project. If a project directory doesn't exist yet, create it first, then initialize the venv there. Do not create throwaway venvs in arbitrary locations.
- **Changelog.** Maintain a changelog for every project. Append all relevant changes as you go. If no changelog exists, create one before making the first modification.
- **Browser automation.** Never use the `agent-browser` skill/tool — it has serious unresolved issues. Always use `playwright-cli` (or raw Playwright scripts) instead.

### Known Pitfalls

#### Electron + AppImage: Chromium SUID Sandbox Crash

**Problem:** Electron apps packaged as AppImage crash on launch with `FATAL:setuid_sandbox_host.cc` or show a blank window. Chromium's SUID sandbox helper requires `setuid` which cannot execute inside an AppImage's read-only squashfs filesystem.

**Fix — two pieces, wired at packaging time (never a post-build patch):**

1. **Wrapper script** — `scripts/apprun.sh`, committed to the repo:
   ```sh
   #!/bin/sh
   SELF="$(readlink -f "$0")"
   HERE="$(dirname "$SELF")"
   exec "$HERE/<executable-name>" --no-sandbox "$@"
   ```

2. **Injection point** — in `forge.config.js`, the AppImage maker must use this script as the entrypoint. The exact config key depends on the maker (`runtime`, `entrypoint`, `customEntrypoint` — check the maker's docs), e.g.:
   ```js
   {
     name: '@reforged/maker-appimage',
     config: {
       options: {
         runtime: path.join(__dirname, 'scripts', 'apprun.sh'),
       },
     },
   }
   ```

**The `.deb` package does not need this fix** — it runs on a writable filesystem where the sandbox works normally.

**Anti-patterns (do not do):**
- Launching the AppImage with `--no-sandbox` manually as a workaround
- Writing a separate launcher script next to the AppImage after build
- Editing the AppRun inside the squashfs after packaging
