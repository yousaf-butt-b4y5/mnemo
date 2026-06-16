"""Clean, private, deterministic migration: Windows Sticky Notes -> Mnemo.

Why direct + deterministic (not via /api/capture):
  * PRIVACY — sticky notes are PII-heavy (IBANs, tax IDs, addresses, family
    messages). The capture flow can send non-secret personal-vault text to a
    cloud LLM (OpenRouter). This migration makes ZERO model calls, so nothing
    ever leaves the machine.
  * QUALITY — the previous LLM migration produced 29 "Untitled" notes, dumped
    40 into Inbox, and mangled German umlauts. Deterministic rules give clean
    titles, a sensible tree, and correct UTF-8 every time.
  * SECRETS — credentials are still detected by mnemo.secrets_detect and stored
    as protected fields (never indexed in plaintext).

Source is read read-only/immutable (no lock). Original note dates are preserved.
Run once:  python tools/migrate_sticky.py
"""
from __future__ import annotations

import re
import shutil
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Make `mnemo` importable when run from the repo root or tools/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from mnemo import config, db, secrets_detect  # noqa: E402

STICKY_DB = (
    "file:C:/Users/yousa/AppData/Local/Packages/"
    "Microsoft.MicrosoftStickyNotes_8wekyb3d8bbwe/LocalState/plum.sqlite"
    "?mode=ro&immutable=1"
)
VAULT = "personal"

# A line in a Sticky note carries a `\id=<guid>` anchor; strip every occurrence
# (full GUID or a bare, truncated tail).
_ANCHOR = re.compile(r"\\id=[0-9a-fA-F-]*")


def clean_text(t: str) -> str:
    """Strip anchors, normalise newlines, collapse blank runs, trim."""
    t = _ANCHOR.sub("", t or "").replace("\r\n", "\n")
    out: list[str] = []
    blank = False
    for raw in t.split("\n"):
        line = raw.strip()
        if not line:
            if out and not blank:
                out.append("")
            blank = True
        else:
            out.append(line)
            blank = False
    return "\n".join(out).strip()


def derive_title(text: str, fallback: str) -> str:
    """Title from the first line that has real words; never 'Untitled'.

    Prefers a line with >=3 letters so a stray leading number/phone fragment
    (e.g. "518") doesn't become the title when a real sentence follows.
    """
    lines = [ln.strip().rstrip(":").strip() for ln in text.split("\n")]
    lines = [ln for ln in lines if ln]
    for ln in lines:
        if sum(c.isalpha() for c in ln) >= 3:
            return ln[:60]
    return lines[0][:60] if lines else fallback


# Deterministic, bilingual (DE/EN) routing. First match wins.
_ROUTES = [
    ("Personal/Finance", ["iban", "sparkasse", "paypal", "revolut", "mastercard",
                          "master card", "visa", "konto", "kontonummer", "bic",
                          "steuer", "versicherung", "kredit", "geld", "bank",
                          "blz", "next-level-marketing", "investment"]),
    ("Personal/Identity", ["steuer id", "versicherungsnummer", "personalausweis",
                           "ausweis", "passport", "reisepass", "cnic", "nationality",
                           "sozialversicherung", "geburts"]),
    ("Personal/Contacts", ["adress", "address", "nummer", "phone", "tel:", "mobil",
                           "herr.", "frau.", "kontakt", "contact", "house no",
                           "street", "colony", "lahore"]),
    ("Personal/Reading", ["buch:", "book:", "reading", "lesen"]),
    ("Code/PowerShell", ["get-", "set-", "new-", "param(", "write-host", "$psitem"]),
    ("Code", ["def ", "class ", "import ", "function ", "select ", "console.",
              "public ", "<?php"]),
    ("Personal/Logins", ["login", "passwort", "password", "benutzer", "username",
                         "account", "anmeld"]),
]


def classify(text: str) -> tuple[str, str, list[str]]:
    """Return (tree_path, type, tags) deterministically. No model calls."""
    low = text.lower()
    # Prose guard FIRST: a long, multi-sentence personal message is a written
    # note even if it mentions a money word ("Geld") in passing. Only structured
    # data markers (IBAN, "Nummer:", account labels) override this.
    strong_struct = any(m in low for m in
                        ("iban", "nummer:", "konto", "id:", "passwort", "password"))
    sentences = text.count(". ") + text.count(".\n") + text.rstrip().endswith(".")
    if len(text) > 200 and sentences >= 3 and not strong_struct:
        return "Personal/Notes", "note", ["note"]
    for tree, keys in _ROUTES:
        if any(k in low for k in keys):
            kind = "code" if tree.startswith("Code") else "note"
            leaf = tree.split("/")[-1].lower().replace(" ", "-")
            return tree, kind, [leaf]
    if len(text) > 180 and text.count(".") >= 2:
        return "Personal/Notes", "note", ["note"]
    return "Inbox", "note", ["inbox"]


def _parse_dt(value) -> str:
    """Decode Sticky Notes CreatedAt (.NET DateTime ticks) to ISO-8601 UTC.

    Ticks = 100-nanosecond intervals since 0001-01-01 UTC. Falls back to 'now'
    if the value is missing or outside a sane 2000-2100 window.
    """
    try:
        ticks = int(value)
        if ticks > 0:
            dt = datetime(1, 1, 1, tzinfo=timezone.utc) + timedelta(microseconds=ticks // 10)
            if 2000 <= dt.year <= 2100:
                return dt.isoformat()
    except (ValueError, TypeError, OverflowError):
        pass
    return datetime.now(timezone.utc).isoformat()


def wipe(vault: str) -> int:
    conn = db.connect(vault)
    try:
        n = conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
        conn.execute("DELETE FROM secret_fields")
        conn.execute("DELETE FROM entries")
        conn.execute("DELETE FROM entries_fts")
        conn.commit()
        return n
    finally:
        conn.close()


def main() -> None:
    # 1. Back up the current vault DB (data/ is gitignored).
    src = Path(config.VAULTS[VAULT])
    if src.exists():
        bak = src.with_suffix(f".premigrate-{datetime.now():%Y%m%d-%H%M%S}.bak")
        shutil.copy2(src, bak)
        print(f"Backup: {bak.name}")

    # 2. Read live sticky notes (skip deleted), read-only.
    sc = sqlite3.connect(STICKY_DB, uri=True)
    sc.row_factory = sqlite3.Row
    rows = sc.execute(
        "SELECT Text, CreatedAt FROM Note WHERE DeletedAt IS NULL ORDER BY rowid"
    ).fetchall()
    sc.close()

    notes = []
    for r in rows:
        text = clean_text(r["Text"])
        if text:
            notes.append((text, _parse_dt(r["CreatedAt"])))
    print(f"Sticky notes to migrate (clean, non-empty): {len(notes)}")

    # 3. Clean slate, then deterministic re-migration.
    removed = wipe(VAULT)
    print(f"Wiped {removed} botched entries from {VAULT}.db")

    note_n = sec_n = 0
    dates: list[tuple[str, int]] = []  # (created, entry_id) for the date pass
    for text, created in notes:
        det = secrets_detect.detect(text)
        if det["is_secret"]:
            title = det["title_hint"]
            for f in det["fields"]:
                if f["kind"] in ("username", "meta") and f["value"]:
                    title = f"{det['title_hint']} — {f['value'][:40]}"
                    break
            eid = db.add_entry(
                VAULT, title=title,
                summary=f"{len(det['fields'])} protected field(s) · {det['kind']}",
                content="", raw=text, type="credential",
                tags=["credential", det["kind"]],
                tree_path="Personal/Logins", source="sticky",
                is_secret=True, secret_fields=det["fields"],
            )
            sec_n += 1
        else:
            tree, typ, tags = classify(text)
            title = derive_title(text, fallback=f"{tree.split('/')[-1]} note")
            eid = db.add_entry(
                VAULT, title=title, summary=text.split("\n")[0][:200],
                content=text, raw=text, type=typ, tags=tags,
                tree_path=tree, source="sticky", is_secret=False,
            )
            note_n += 1
        dates.append((created, eid))

    # Second pass: preserve original note dates in one short transaction so it
    # never contends with add_entry's per-call connection (`created` is not in
    # the FTS index, so this is safe).
    conn = db.connect(VAULT)
    try:
        conn.executemany("UPDATE entries SET created=? WHERE id=?", dates)
        conn.commit()
    finally:
        conn.close()
    print(f"DONE — {note_n} notes, {sec_n} protected credentials, "
          f"{note_n + sec_n} total")


if __name__ == "__main__":
    main()
