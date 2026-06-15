import sqlite3

con = sqlite3.connect(r'F:\Doc-SSD\Git-Repos\odysseus\data\app.db')

print("=== TASK RUNS TODAY ===")
rows = con.execute("""
    SELECT st.name, tr.started_at, tr.status, tr.result, tr.error
    FROM task_runs tr
    JOIN scheduled_tasks st ON tr.task_id = st.id
    WHERE tr.started_at >= '2026-06-15'
    ORDER BY tr.started_at DESC
    LIMIT 20
""").fetchall()
for name, started, status, result, error in rows:
    msg = (result or error or "")[:100]
    print(f"  [{started[:19]}] {name:<30} {status:<10} {msg}")

print()
print("=== RECENT MEMORIES (last 20) ===")
mems = con.execute("""
    SELECT category, created_at, substr(content, 1, 90) FROM memories
    ORDER BY created_at DESC LIMIT 20
""").fetchall()
for cat, ts, txt in mems:
    print(f"  [{cat:<12}] {txt}")

print()
print("=== EMAIL ACTIVITY TODAY ===")
# Check emails table
try:
    emails = con.execute("""
        SELECT subject, sender, date, account FROM emails
        WHERE date >= '2026-06-15'
        ORDER BY date DESC LIMIT 10
    """).fetchall()
    print(f"  {len(emails)} emails today")
    for e in emails:
        print(f"  [{e[3]}] {e[0]} from {e[1]}")
except Exception as ex:
    print(f"  No emails table or error: {ex}")

print()
print("=== SCHEDULED EMAIL CHECK ===")
try:
    rows = con.execute("SELECT * FROM email_ai_replies LIMIT 5").fetchall()
    print(f"  email_ai_replies: {len(rows)} rows")
    for r in rows:
        print(f"  {r}")
except:
    pass
try:
    rows = con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%email%'").fetchall()
    print(f"  Email tables: {[r[0] for r in rows]}")
except: pass

con.close()
