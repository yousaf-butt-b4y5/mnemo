"""Organize pasted (non-secret) content into title/summary/tags/tree_path.

Order: local Ollama -> OpenRouter (personal vault only) -> rule-based fallback.
Secret content never reaches this module (handled upstream in app.py).
"""
from __future__ import annotations
import json
import re
from typing import Dict
from urllib.parse import urlparse

import httpx

from . import config

PROMPT = """You are an assistant that files notes into a clean tree.
Given the pasted content below, respond with ONLY a JSON object, no prose.

Keys:
- "type": one of note, link, code, doc, task, reference
- "title": a short clear title (max 8 words)
- "summary": one factual sentence
- "tags": array of 2-5 short lowercase tags
- "tree_path": a folder-like path of 1-3 segments, e.g. "Personal/Logins",
  "Work/Network", "Code/PowerShell", "Links/Reading". Group logically.

Content:
\"\"\"
{content}
\"\"\"
"""

_CODE_HINTS = re.compile(
    r"(?m)^\s*(def |class |function |import |#!/|<\?php|SELECT |Get-|Set-|"
    r"New-|param\(|\$\w+\s*=|console\.|public |private |func )"
)
_LANG_HINTS = [
    ("PowerShell", re.compile(r"(?m)(Get-|Set-|New-|\$PSItem|param\(|Write-Host)")),
    ("Python", re.compile(r"(?m)^\s*(def |import |from \w+ import|print\()")),
    ("SQL", re.compile(r"(?i)\b(SELECT|INSERT|UPDATE|DELETE)\b.+\bFROM\b")),
    ("Bash", re.compile(r"(?m)(#!/bin/(ba)?sh|\bsudo\b|apt |grep )")),
    ("JavaScript", re.compile(r"(?m)(const |let |=>|console\.log)")),
]


def _extract_json(text: str) -> Dict:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError("no json")
    return json.loads(m.group(0))


def _clean(result: Dict) -> Dict:
    tags = result.get("tags", [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    return {
        "type": str(result.get("type", "note")).lower().strip() or "note",
        "title": (result.get("title") or "Untitled").strip()[:120],
        "summary": (result.get("summary") or "").strip()[:300],
        "tags": [str(t).lower().strip() for t in tags][:5],
        "tree_path": (result.get("tree_path") or "Inbox").strip("/ ") or "Inbox",
    }


async def _ollama(content: str) -> Dict:
    async with httpx.AsyncClient(timeout=config.OLLAMA_TIMEOUT) as client:
        r = await client.post(
            f"{config.OLLAMA_URL}/api/generate",
            json={
                "model": config.OLLAMA_MODEL,
                "prompt": PROMPT.format(content=content[:4000]),
                "stream": False,
                "format": "json",          # force valid JSON output
                "keep_alive": "30m",        # keep the model warm between captures
                "options": {"temperature": 0.1, "num_predict": 220},
            },
        )
        r.raise_for_status()
        return _clean(_extract_json(r.json().get("response", "")))


async def _openrouter(content: str) -> Dict:
    if not config.OPENROUTER_API_KEY:
        raise RuntimeError("no openrouter key")
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            config.OPENROUTER_URL,
            headers={"Authorization": f"Bearer {config.OPENROUTER_API_KEY}"},
            json={
                "model": config.OPENROUTER_MODEL,
                "messages": [{"role": "user", "content": PROMPT.format(content=content[:4000])}],
                "temperature": 0.1,
            },
        )
        r.raise_for_status()
        msg = r.json()["choices"][0]["message"]["content"]
        return _clean(_extract_json(msg))


def rule_based(content: str) -> Dict:
    """Deterministic offline fallback — always works, no AI needed."""
    text = content.strip()
    first_line = text.splitlines()[0][:80] if text else "Note"

    # URL / link
    urls = re.findall(r"https?://\S+", text)
    if urls and len(text) < 400:
        host = urlparse(urls[0]).netloc.replace("www.", "")
        return {"type": "link", "title": host or first_line,
                "summary": text[:200], "tags": ["link", host.split(".")[0] if host else "web"],
                "tree_path": "Links"}

    # Code
    if _CODE_HINTS.search(text):
        lang = next((name for name, pat in _LANG_HINTS if pat.search(text)), "Code")
        return {"type": "code", "title": f"{lang} snippet",
                "summary": first_line, "tags": ["code", lang.lower()],
                "tree_path": f"Code/{lang}"}

    # Default note
    title = first_line.lstrip("# ").strip() or "Note"
    return {"type": "note", "title": title[:120], "summary": text[:200],
            "tags": ["note"], "tree_path": "Inbox"}


async def classify(content: str, allow_cloud: bool) -> Dict:
    try:
        return await _ollama(content)
    except Exception:
        pass
    if allow_cloud:
        try:
            return await _openrouter(content)
        except Exception:
            pass
    return rule_based(content)
