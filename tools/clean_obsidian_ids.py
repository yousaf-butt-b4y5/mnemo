"""One-time cleanup: strip Obsidian block IDs (\id=UUID) from all note content."""
import sqlite3, re, sys
from pathlib import Path

PAT = re.compile(
    r'\\id=[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12} ?',
    re.IGNORECASE
)

def strip(s):
    if not s:
        return s
    return PAT.sub('', s).strip()

base = Path(__file__).parent.parent / 'data'
for db_path in base.glob('*.db'):
    con = sqlite3.connect(db_path)
    rows = con.execute('SELECT id, title, content, raw, summary FROM entries').fetchall()
    changed = 0
    for eid, title, content, raw, summary in rows:
        nt = strip(title); nc = strip(content); nr = strip(raw); ns = strip(summary)
        if (nt, nc, nr, ns) != (title, content, raw, summary):
            con.execute(
                'UPDATE entries SET title=?,content=?,raw=?,summary=? WHERE id=?',
                (nt, nc, nr, ns, eid)
            )
            changed += 1
    con.commit()
    con.close()
    print(f'{db_path.name}: {changed}/{len(rows)} entries cleaned')
