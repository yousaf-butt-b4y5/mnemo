import sqlite3

con = sqlite3.connect(r'F:\Doc-SSD\Git-Repos\odysseus\data\app.db')
tasks = con.execute("""
    SELECT id, name, action, schedule, cron_expression, status, last_run, next_run, run_count
    FROM scheduled_tasks ORDER BY created_at
""").fetchall()

print(f"{'ID':<10} {'Name':<30} {'Action':<25} {'Status':<8} {'Last Run':<22} {'Runs'}")
print("-" * 115)
for t in tasks:
    tid, name, action, sched, cron, status, last_run, next_run, run_count = t
    last = (last_run or 'never')[:19]
    print(f"{tid[:8]:<10} {(name or ''):<30} {(action or ''):<25} {status:<8} {last:<22} {run_count}")

# Also get today's task_runs
print("\n=== TODAY'S TASK RUNS ===")
runs = con.execute("""
    SELECT tr.id, st.name, tr.started_at, tr.status, tr.result, tr.error
    FROM task_runs tr JOIN scheduled_tasks st ON tr.task_id = st.id
    WHERE tr.started_at >= '2026-06-15'
    ORDER BY tr.started_at DESC LIMIT 20
""").fetchall()
for r in runs:
    rid, name, started, status, result, error = r
    print(f"  [{started[:19]}] {name:<30} {status:<10} {(result or error or '')[:80]}")

con.close()
