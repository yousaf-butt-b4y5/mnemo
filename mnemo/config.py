"""Mnemo configuration. Zero-cost, local-first, env-overridable."""
from __future__ import annotations
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    """Minimal .env loader (no external dependency)."""
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        os.environ.setdefault(key, val)


_load_dotenv()

# --- Storage -----------------------------------------------------------------
# App + small DBs on F:. Repoint DATA_DIR / STORE_DIR to D: when notes grow.
DATA_DIR = Path(os.environ.get("MNEMO_DATA_DIR", BASE_DIR / "data"))
STORE_DIR = Path(os.environ.get("MNEMO_STORE_DIR", BASE_DIR / "store"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
STORE_DIR.mkdir(parents=True, exist_ok=True)

# --- Vaults (separate DB files; work vault never leaves local disk) ----------
VAULTS = {
    "personal": DATA_DIR / "personal.db",
    "work": DATA_DIR / "work.db",
}
DEFAULT_VAULT = "personal"

# Work vault is local-LLM-only: company text must never reach a cloud LLM (§7).
CLOUD_ALLOWED_VAULTS = {"personal"}

# --- AI organization engine --------------------------------------------------
OLLAMA_URL = os.environ.get("MNEMO_OLLAMA_URL", "http://localhost:11434")
# llama3.1:8b is the single local model kept on this box (the §7 privacy lever).
# Good tool/JSON behaviour for the organize prompt. Override via env.
OLLAMA_MODEL = os.environ.get("MNEMO_OLLAMA_MODEL", "llama3.1:8b")
# Cold-load on a 6 GB GPU can take >30s; warm calls are fast (model kept alive).
OLLAMA_TIMEOUT = float(os.environ.get("MNEMO_OLLAMA_TIMEOUT", "75"))

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.environ.get(
    "MNEMO_OPENROUTER_MODEL", "google/gemini-2.5-flash-lite"
)

# --- Server ------------------------------------------------------------------
HOST = os.environ.get("MNEMO_HOST", "127.0.0.1")
PORT = int(os.environ.get("MNEMO_PORT", "7575"))

# Token Odysseus presents to read non-secret notes via /mnemo/search.
# Empty = open on localhost (MVP). Set for shared/portable use.
MNEMO_SHARED_TOKEN = os.environ.get("MNEMO_SHARED_TOKEN", "")

# Cap stored content so a giant paste can't bloat the DB/FTS index.
MAX_CAPTURE_CHARS = int(os.environ.get("MNEMO_MAX_CHARS", "100000"))
# Cap uploaded file size (bytes). Default 25 MB.
MAX_UPLOAD_BYTES = int(os.environ.get("MNEMO_MAX_UPLOAD", str(25 * 1024 * 1024)))
