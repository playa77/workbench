# Open WebUI Wrapper

A native Linux desktop wrapper for [Open WebUI](https://github.com/open-webui/open-webui) — the self-hosted LLM chat interface.

Launches Open WebUI as a background process, finds an available port, and opens it in a dedicated window. No terminal, no manual `serve` command, no browser tab hunting.

![Status](https://img.shields.io/badge/status-experimental-orange) ![Platform](https://img.shields.io/badge/platform-linux-blue) ![License](https://img.shields.io/badge/license-MIT-green)

---

## Features

- **Zero-config launch** — starts `open-webui serve` automatically via `uvx`
- **Automatic port selection** — scans ports 8080–8180, picks the first free one
- **Health-checked startup** — polls `/health` until the server responds (2 min timeout)
- **Loading & error screens** — dark-themed spinner while waiting; stderr log + Retry button on failure
- **Graceful shutdown** — sends SIGTERM, force-kills after 5s if needed
- **Single instance** — prevents accidental duplicate launches
- **Linux packaging** — builds `.deb` and `.AppImage` with electron-builder

---

## Prerequisites

| Requirement | Why |
|---|---|
| **Node.js 18+** | Electron 33 runtime |
| **[`uvx`](https://docs.astral.sh/uv/)** | Launches `open-webui` from PyPI without a manual install |

```bash
# Install uv (if you don't have it)
curl -LsSf https://astral.sh/uv/install.sh | sh
```

---

## Quick Start

```bash
# Clone and install
git clone https://github.com/playa77/open-webui-wrapper
cd open-webui-wrapper
npm install

# Run in development mode
npm run dev

# Build for production
npm run build

# Package as .deb
npm run dist:deb

# Package as AppImage
npm run dist:appimage

# Package both
npm run dist
```

Built packages land in `release/`.

---

## Configuration

Open WebUI reads its own environment variables. Pass them however you normally would:

```bash
# Example: point Open WebUI to a remote Ollama instance
OLLAMA_BASE_URL=http://192.168.1.50:11434 npm run dev
```

All environment variables in the current shell are forwarded to the `open-webui` process. You can also place a `.env` file in the project root (it's gitignored).

---

## How It Works

```
┌──────────────────────────────────────┐
│  Electron Main Process               │
│                                      │
│  1. Find free port (8080–8180)       │
│  2. Spawn: uvx open-webui serve      │
│  3. Show loading screen (React)      │
│  4. Poll /health every 500ms         │
│  5. On ready → load Open WebUI URL   │
│  6. On quit → SIGTERM → SIGKILL      │
└──────────────────────────────────────┘
```

- **`src/main/index.ts`** — Electron lifecycle, window creation
- **`src/main/server.ts`** — spawns and manages the Open WebUI child process
- **`src/main/ipc.ts`** — bridges server events to the renderer via preload
- **`src/main/preload.ts`** — exposes `window.owui` API securely (context isolation enabled)
- **`src/renderer/App.tsx`** — loading spinner and error screen UI

Tech stack: **Electron 33**, **React 18**, **TypeScript**, **Vite 6**.

---

## License

MIT — see [LICENSE](./LICENSE).
