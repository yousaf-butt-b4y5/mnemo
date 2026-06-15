"""One-time: migrate Windows Sticky Notes (plum.sqlite) → Mnemo (personal vault).

Reads the live DB read-only (immutable, no lock), strips the leading
`\\id=<guid>` anchor each note carries, and POSTs each to /api/capture.
Mnemo's secret-detector masks credential notes; nothing is printed in clear.
Run once:  python tools/migrate_sticky.py
"""
import re
import sqlite3
import httpx

DB = ("file:C:/Users/yousa/AppData/Local/Packages/"
      "Microsoft.MicrosoftStickyNotes_8wekyb3d8bbwe/LocalState/plum.sqlite"
      "?mode=ro&immutable=1")
MNEMO = "http://127.0.0.1:7575"


def clean(t: str) -> str:
    t = re.sub(r"^\\id=[0-9a-fA-F-]+\s*", "", t or "")  # strip Sticky-Notes id anchor
    return t.strip()


def main():
    c = sqlite3.connect(DB, uri=True)
    notes = [clean(t) for (t,) in c.execute("SELECT Text FROM Note ORDER BY rowid")]
    notes = [n for n in notes if n]
    print(f"{len(notes)} notes to migrate")
    cli = httpx.Client(base_url=MNEMO, timeout=120)
    note = sec = err = 0
    for i, n in enumerate(notes, 1):
        try:
            r = cli.post("/api/capture",
                         json={"content": n, "vault": "personal", "source": "sticky"})
            r.raise_for_status()
            if r.json().get("is_secret"):
                sec += 1
            else:
                note += 1
        except Exception as e:  # noqa: BLE001
            err += 1
            print(f"  [{i}] ERROR: {str(e)[:80]}")
        if i % 20 == 0:
            print(f"  …{i}/{len(notes)}")
    print(f"DONE — {note} notes, {sec} secrets, {err} errors")


if __name__ == "__main__":
    main()
