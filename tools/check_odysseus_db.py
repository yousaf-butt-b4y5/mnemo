import sqlite3, json

con = sqlite3.connect(r'F:\Doc-SSD\Git-Repos\odysseus\data\app.db')
tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print("Tables:", tables)

for t in tables:
    if any(k in t.lower() for k in ['token', 'codex', 'agent', 'task', 'integr', 'memory']):
        cols = [c[1] for c in con.execute(f"PRAGMA table_info({t})").fetchall()]
        rows = con.execute(f"SELECT * FROM {t} LIMIT 5").fetchall()
        print(f"\n--- {t} | cols: {cols}")
        for r in rows:
            safe = tuple(str(v)[:60] if isinstance(v, str) and len(str(v)) > 60 else v for v in r)
            print(" ", safe)
con.close()
