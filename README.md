# Mnemo 🗂️
**Paste anything. Find everything.**

A local, AI-powered note hub. Paste any mess — text, links, code, PDFs, login
blocks — and Mnemo cleans it, titles it, tags it, and files it onto a logical
tree. Click or search to retrieve. Built to replace sticky notes, txt files,
OneNote, and scattered bookmarks — **100% local-first**, runs on consumer hardware.

> Mnemo is **not** a hardcore password manager — use a real vault (e.g. Bitwarden)
> for true secrets. Mnemo gives fast, organized, lightly-protected access to notes
> and structured credentials, with a clean hook to add full encryption later.

## Quick start

```bash
git clone https://github.com/yousaf-butt-b4y5/mnemo
cd mnemo
pip install -r requirements.txt
python -m uvicorn app:app --port 7575      # Windows: .\run.ps1
```

Then open **http://localhost:7575**. Defaults work out of the box with a local
[Ollama](https://ollama.com) model (`gemma3:4b`); no cloud key required.

- **Paste** into the top box → `Capture` (or `Ctrl+Enter`).
- **Drag-drop** a file or PDF anywhere → it's read and filed.
- **Search** instantly (FTS5). Click a **tree** node to filter.
- **Secrets** are masked; click `Reveal` → eye-toggle → copy (clipboard auto-clears in 20s).

## How it organizes

1. **Secret detection (rule-based, local)** runs first — passwords, API keys,
   SSH keys, tokens, login blocks. Detected secrets are stored locally,
   masked, and **never sent to any LLM**.
2. **Non-secret content** is organized by **local Ollama** (`gemma3:4b`, ~3s),
   falling back to **OpenRouter** (personal vault only), falling back to a
   deterministic **offline rule-based** classifier. It always works.

## Vaults (personal vs work)

- `personal` — your life. May use cloud AI (OpenRouter) as a fallback.
- `work` — for company/sensitive data. **Local-LLM-only**: that vault's text
  never touches the cloud. Switch with the header toggle — a banner shows which
  vault is active.

Each vault is a separate SQLite file in `data/`. Keep a work vault only on
trusted/managed storage and never sync it to personal cloud.

## Talking to other tools

- `GET /mnemo/search?q=...` — a scoped surface another app (e.g. a personal AI
  workspace) can call to find a note. Returns **non-secret** entries only;
  secrets are excluded entirely and can never be pulled this way.

## Convenience scripts (Windows)

| Script | What it does |
|---|---|
| `run.ps1` | Start Mnemo (idempotent — won't double-start). |
| `start-hidden.vbs` | Start Mnemo with no console window (used by autostart). |
| `install-autostart.ps1` | Run **once** → Mnemo starts hidden at every logon. Undo by deleting the Startup `.lnk`. |
| `backup.ps1` | Copy both vault DBs to `backups\<timestamp>\` (keeps last 20). |
| `tests/smoke.py` | Re-runnable health check (detection + HTTP). Exit 0 = all good. |

## Config

`.env` holds your live settings (gitignored — copy `.env.example` to start).
Add an OpenRouter key to enable cloud fallback for the personal vault; leave it
blank to stay 100% local.

| Setting | Default |
|---|---|
| Port | 7575 |
| Local model | `gemma3:4b` (Ollama) |
| Cloud fallback | OpenRouter `gemini-2.5-flash-lite` (personal vault only) |
| Data dir | `./data` |

## Architecture

```
app.py                   FastAPI — capture/search/reveal/upload/scoped surface
mnemo/config.py          paths, vaults, models, port
mnemo/secrets_detect.py  rule-based secret detection (runs before any LLM)
mnemo/classifier.py      Ollama -> OpenRouter -> offline rule-based
mnemo/db.py              SQLite + FTS5; secret values never enter the search index
static/index.html        the UI (vanilla, dark, single page)
```

## Roadmap

- App PIN/lock; optional SQLCipher full-DB encryption (the hook is reserved).
- Portable PyInstaller build (no install / no admin).
- Push to an external workspace (documents/memory) + global capture hotkey.
- Configurable large-store path; Postgres/cloud path for multi-device.

## License
MIT — see [LICENSE](LICENSE).
