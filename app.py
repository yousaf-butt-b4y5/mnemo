"""Mnemo — FastAPI backend.

Paste anything -> secret-detect (rule-based, local) -> AI-organize (Ollama,
OpenRouter fallback) -> file onto a tree -> search / retrieve / extract.
"""
from __future__ import annotations
import io
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from mnemo import config, db, classifier, secrets_detect

app = FastAPI(title="Mnemo", version="0.1.0")

# Localhost-only by default; CORS open so the navigator + Odysseus can call.
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

db.init_all()


# --- Models ------------------------------------------------------------------
class CaptureIn(BaseModel):
    content: str
    vault: str = config.DEFAULT_VAULT
    source: str = "paste"


class UpdateIn(BaseModel):
    vault: str = config.DEFAULT_VAULT
    title: Optional[str] = None
    summary: Optional[str] = None
    content: Optional[str] = None
    tags: Optional[list] = None
    tree_path: Optional[str] = None


class SecretFieldsIn(BaseModel):
    vault: str = config.DEFAULT_VAULT
    fields: list = []  # [{label, value, kind}]


# --- Health + meta -----------------------------------------------------------
@app.get("/api/health")
def health():
    return {"status": "ok", "app": "mnemo", "version": "0.1.0"}


@app.get("/api/vaults")
def vaults():
    return {
        "vaults": [
            {"name": v, "cloud_allowed": v in config.CLOUD_ALLOWED_VAULTS,
             **db.counts(v)}
            for v in config.VAULTS
        ],
        "default": config.DEFAULT_VAULT,
    }


# --- Capture (the core flow) -------------------------------------------------
@app.post("/api/capture")
async def capture(body: CaptureIn):
    if body.vault not in config.VAULTS:
        raise HTTPException(400, "unknown vault")
    content = body.content.strip()
    if not content:
        raise HTTPException(400, "empty content")
    if len(content) > config.MAX_CAPTURE_CHARS:
        content = content[:config.MAX_CAPTURE_CHARS] + "\n\n[… truncated by Mnemo]"

    det = secrets_detect.detect(content)

    if det["is_secret"]:
        # Credentials are organized WITHOUT any LLM call. Nothing leaves the box.
        is_work = body.vault == "work"
        base = "Work/Logins" if is_work else "Personal/Logins"
        title = det["title_hint"]
        # try to name it from a username/host field
        for f in det["fields"]:
            if f["kind"] in ("username", "meta") and f["value"]:
                title = f"{det['title_hint']} — {f['value'][:40]}"
                break
        n = len(det["fields"])
        entry_id = db.add_entry(
            body.vault, title=title,
            summary=f"{n} protected field(s) · {det['kind']}",
            content="", raw=content, type="credential",
            tags=["credential", det["kind"]], tree_path=base,
            source=body.source, is_secret=True, secret_fields=det["fields"],
        )
        return {"id": entry_id, "is_secret": True,
                "entry": db.get_entry(body.vault, entry_id)}

    # Non-secret -> AI organize (work vault stays local-only)
    allow_cloud = body.vault in config.CLOUD_ALLOWED_VAULTS
    org = await classifier.classify(content, allow_cloud=allow_cloud)
    entry_id = db.add_entry(
        body.vault, title=org["title"], summary=org["summary"],
        content=content, raw=content, type=org["type"], tags=org["tags"],
        tree_path=org["tree_path"], source=body.source, is_secret=False,
    )
    return {"id": entry_id, "is_secret": False,
            "entry": db.get_entry(body.vault, entry_id)}


# --- Read --------------------------------------------------------------------
@app.get("/api/entries")
def entries(vault: str = config.DEFAULT_VAULT, tree: str = "", q: str = ""):
    if vault not in config.VAULTS:
        raise HTTPException(400, "unknown vault")
    if q:
        return {"entries": db.search(vault, q)}
    return {"entries": db.list_entries(vault, tree_prefix=tree)}


@app.get("/api/tree")
def get_tree(vault: str = config.DEFAULT_VAULT):
    if vault not in config.VAULTS:
        raise HTTPException(400, "unknown vault")
    return {"tree": db.tree(vault)}


@app.get("/api/entry/{entry_id}")
def entry(entry_id: int, vault: str = config.DEFAULT_VAULT):
    e = db.get_entry(vault, entry_id)
    if not e:
        raise HTTPException(404, "not found")
    return e


@app.get("/api/entry/{entry_id}/secrets")
def reveal(entry_id: int, vault: str = config.DEFAULT_VAULT):
    """Reveal-on-demand. Local-only; gate behind a PIN in Phase D."""
    e = db.get_entry(vault, entry_id, include_secret=True)
    if not e:
        raise HTTPException(404, "not found")
    if not e["is_secret"]:
        return {"secret_fields": []}
    return {"secret_fields": e.get("secret_fields", [])}


@app.put("/api/entry/{entry_id}")
def update(entry_id: int, body: UpdateIn):
    ok = db.update_entry(
        body.vault, entry_id, title=body.title, summary=body.summary,
        content=body.content, tags=body.tags, tree_path=body.tree_path,
    )
    if not ok:
        raise HTTPException(404, "not found")
    return db.get_entry(body.vault, entry_id)


@app.put("/api/entry/{entry_id}/secrets")
def update_secrets(entry_id: int, body: SecretFieldsIn):
    """Replace an entry's secret fields — lets a mis-parsed credential be fixed."""
    ok = db.update_secret_fields(body.vault, entry_id, body.fields)
    if not ok:
        raise HTTPException(404, "not found")
    return db.get_entry(body.vault, entry_id, include_secret=True)


@app.delete("/api/entry/{entry_id}")
def delete(entry_id: int, vault: str = config.DEFAULT_VAULT):
    db.delete_entry(vault, entry_id)
    return {"deleted": entry_id}


# --- File / PDF ingest -------------------------------------------------------
@app.post("/api/upload")
async def upload(vault: str = Form(config.DEFAULT_VAULT),
                 file: UploadFile = File(...)):
    if vault not in config.VAULTS:
        raise HTTPException(400, "unknown vault")
    data = await file.read()
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"file too large (max {config.MAX_UPLOAD_BYTES // (1024*1024)} MB)")
    dest_dir = config.STORE_DIR / vault
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / file.filename
    dest.write_bytes(data)

    text = ""
    if file.filename.lower().endswith(".pdf"):
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(data))
            text = "\n".join((p.extract_text() or "") for p in reader.pages)
        except Exception:
            text = ""
    elif file.content_type and file.content_type.startswith("text"):
        text = data.decode("utf-8", errors="replace")

    allow_cloud = vault in config.CLOUD_ALLOWED_VAULTS
    if text.strip():
        org = await classifier.classify(text, allow_cloud=allow_cloud)
    else:
        org = {"type": "doc", "title": file.filename, "summary": "Uploaded file",
               "tags": ["file"], "tree_path": "Files"}

    entry_id = db.add_entry(
        vault, title=org["title"], summary=org["summary"],
        content=text[:20000], raw=text[:20000], type="doc",
        tags=org["tags"] + ["file"], tree_path=org["tree_path"],
        source="upload", is_secret=False,
    )
    db.add_attachment(vault, entry_id, file.filename, str(dest),
                      file.content_type or "application/octet-stream", len(data))
    return {"id": entry_id, "entry": db.get_entry(vault, entry_id)}


# --- Scoped endpoint Odysseus calls (only when the user asks) ----------------
@app.get("/mnemo/search")
def odysseus_search(q: str, vault: str = config.DEFAULT_VAULT,
                    x_mnemo_token: str = Header(default="")):
    """Non-secret search surface for Odysseus. Secrets are excluded entirely."""
    if config.MNEMO_SHARED_TOKEN and x_mnemo_token != config.MNEMO_SHARED_TOKEN:
        raise HTTPException(403, "bad token")
    results = db.search(vault, q, secret_ok=False)
    return {"query": q, "vault": vault, "results": results}


# --- Static frontend ---------------------------------------------------------
STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")
