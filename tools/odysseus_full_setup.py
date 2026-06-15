"""
Odysseus full operational setup:
1. Pause Email AI Auto Reply (must never auto-send)
2. Activate Email Calendar Events + Calendar Classify Events
3. Write the complete vision into Odysseus memory
"""
import httpx, os

BASE = "http://127.0.0.1:7000"
env_lines = open(r"F:\Apps\ecosystem-mcp\.env").read().splitlines()
TOKEN = next(l.split("=",1)[1].strip() for l in env_lines if l.startswith("ODYSSEUS_API_TOKEN="))

h = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

def api(method, path, **kw):
    r = httpx.request(method, BASE + path, headers=h, timeout=30, **kw)
    try: return r.status_code, r.json()
    except: return r.status_code, r.text

# ── 1. Get current tasks ──────────────────────────────────────────────────────
s, data = api("GET", "/api/tasks")
tasks = data.get("tasks", [])
print(f"Tasks found: {len(tasks)}")

def find_task(name_fragment):
    return [t for t in tasks if name_fragment.lower() in t.get("name","").lower()]

# Email AI Auto Reply -> PAUSE
for t in find_task("Auto Reply"):
    s, r = api("POST", f"/api/tasks/{t['id']}/pause")
    print(f"  PAUSE Email AI Auto Reply [{t['id'][:8]}] -> {s} {r}")

# Email Calendar Events -> RESUME
for t in find_task("Calendar Events"):
    s, r = api("POST", f"/api/tasks/{t['id']}/resume")
    print(f"  RESUME Email Calendar Events [{t['id'][:8]}] -> {s} {r}")

# Calendar Classify Events -> RESUME
for t in find_task("Classify Events"):
    s, r = api("POST", f"/api/tasks/{t['id']}/resume")
    print(f"  RESUME Calendar Classify Events [{t['id'][:8]}] -> {s} {r}")

# ── 2. Verify tasks endpoint accepts Bearer ───────────────────────────────────
s, data2 = api("GET", "/api/tasks")
for t in data2.get("tasks", []):
    icon = "RUN" if t["status"] == "active" else "---"
    print(f"  {icon} {t.get('name',''):<32} {t['status']}")

# ── 3. Write vision memories ──────────────────────────────────────────────────
print("\n=== Writing vision memories ===")

MEMORIES = [
    ("vision_north_star", "goal",
     "Vault + Odysseus are the single hub for all of Yousaf's digital life. F:\\Vault (PARA+Zettelkasten, git-backed) is the single source of truth. Odysseus is the AI brain at :7000. MCP servers expose the stack to every AI client. Long-term goal ~2031: Odysseus autonomously handles IT tickets, user onboarding/offboarding, and daily briefings as a fully autonomous AI-native IT admin."),

    ("vision_career_ladder", "goal",
     "Career path: IT-SysAdmin (NOW, GO! Express 2026-06-15) -> Automation Engineer -> Platform Engineer -> AI-Enterprise Architect. Core thesis: tools are not the advantage, the SYSTEM around them is. Master pattern: AI -> MCP -> system -> action + governance. Quantify every automation. First killer artifact: user-lifecycle automation (joiner/mover/leaver). Cert ladder: AZ-900/MS-900 -> SC-300 -> AZ-305. Target: 100k+ EUR in Germany."),

    ("vision_go_express_job", "fact",
     "Yousaf is IT-Systemadministrator at GO! Express & Logistics GmbH, Eltersdorfer Str. 21, 90425 Nurnberg. Start 2026-06-15, unbefristet, 40h/week, 6-month Probezeit ends ~2026-12-15. Tools: FreshService (tickets NOT Jira), Microsoft 365, Active Directory hybrid, Windows+Linux servers, telephony, IT-Rufbereitschaft on-call. Compliance binding: para 7 = no company data in personal cloud/GitHub; para 8 = notify employer before monetizing any tool (including Mnemo). Atlassian is for personal portfolio/learning ONLY."),

    ("vision_ecosystem_stack", "fact",
     "Running local stack: Odysseus :7000 (hub), Mnemo :7575 (note+secret store, 127 entries), Ollama :11434 (local LLMs), ChromaDB :8100 Docker (vector DB), Ecosystem MCP :9100 (8 tools: mnemo_search, odysseus_memory, odysseus_todos, odysseus_agenda, odysseus_documents, vault_search, vault_read, route_llm), Odysseus MCP Gateway :9090 (Bearer required). Docker MCP Toolkit servers: Atlassian, GitHub, Obsidian, Filesystem, Playwright, Fetch. OpenRouter for free LLM fallback."),

    ("vision_local_models", "fact",
     "Ollama models on RTX 2060 6GB VRAM: gemma3:4b (quick chat default, 2.5GB), qwen2.5-coder:7b (code tasks, 4.5GB), llama3.1:8b (agent+tool use, 5GB), deepseek-r1:7b (reasoning only, slow 30-40s, 4.5GB). Hardware ceiling: nothing above 7B Q4 fits cleanly. NEVER use gemma3 or deepseek-r1 for runtime tool routing. External fallback: OpenRouter free models via route_llm tool."),

    ("vision_email_rules", "preference",
     "CRITICAL: Odysseus must NEVER send email automatically. Always create a draft only. Email AI Auto Reply task stays PAUSED permanently until a human confirmation gate is built. Safe send-default account: surpriseb4y5@gmail.com. Primary: yousafb419@gmail.com (career/private, Apple Calendar). Secondary: buttyousaf67@gmail.com (tools/automated). Odysseus email tags write only to local SQLite (email_tags table), never to Gmail IMAP labels. Gmail labels are owned by Gmail filters only - one-owner rule."),

    ("vision_mcp_architecture", "goal",
     "MCP build order: 1) Personal Ecosystem MCP DONE (:9100, 8 tools, registered in Claude Code user scope). 2) Test deeply -> production. 3) GO! Express MCP (employer-approved, company infra, para 7/8 compliant, targets FreshService+Entra). Odysseus natively supports MCP Tool Server integration type in Settings -> Integrations. Docker MCP Toolkit is the realized hub for off-the-shelf servers. Ecosystem MCP complements it for bespoke stack."),

    ("vision_mnemo", "fact",
     "Mnemo: local AI note + secret store at F:\\Apps\\Mnemo, port 7575, FastAPI+SQLite+Ollama. 127 migrated entries (Obsidian block IDs cleaned). UI: Discord 3-pane + Claude-env warm clay palette. Long-term: universal store for passwords/APIs/SSH/logins/notes. App-Store launch planned after ~6 months (para 8 - notify GO! Express first). GitHub: github.com/yousaf-butt-b4y5/mnemo. Smoke tests: 17/17 passing."),

    ("vision_vault_structure", "fact",
     "Source of truth: F:\\Vault, git main, private at github.com/yousaf-butt-b4y5/vault. PARA structure: 01-projects, 02-areas, 03-resources, 04-archive, 05-identity (gitignored). Key docs: 02-areas/job-go-express/ (job facts+compliance+runbooks), 01-projects/odysseus/ (guides+voyage-map), 03-resources/ecosystem-architecture-2026.md (full layered architecture). NEVER sync: 05-identity/, 02-areas/family/, 02-areas/finance/, .env, auth.json, data/, logs/."),

    ("vision_odysseus_pulse", "goal",
     "Odysseus Pulse - self-awareness goal: Odysseus should detect and report new releases of Ollama models, OpenRouter free models, open-source tools, and Odysseus upstream PRs in a dedicated Daily Briefing section. Weekly evaluation of new free/open-source tools against current stack. Yousaf controls everything from Claude Code chat - minimize his manual steps: Claude acts, Yousaf confirms."),

    ("vision_odysseus_prs", "fact",
     "Odysseus upstream PR strategy - Windows testing advantage. Done: PR #2719 (Windows smoke test 7/7), README fix #2118. Next by ROI: PR-1 Cookbook status colors (45min, HIGH), PR-2 Deep Research modal confusion (1.5h), PR-3 Cookbook download ETA (2.5h), PR-4 Brain Skills edit/delete (2-3h), PR-5 Tasks status labels (2-3h), PR-6 GitHub integration legend (2.5h). All PRs target dev branch. PR description must have linked issue - N/A fails CI."),

    ("vision_what_not_to_do", "preference",
     "NEVER: auto-send emails, push .env/data/logs/auth.json to git, sync identity/finance/family vault areas, use cloud LLMs with company data (para 7), monetize tools without notifying GO! Express (para 8), run automated file cleanup scripts, activate Email AI Auto Reply without a human confirmation gate, use Google/Vertex/Azure-OpenAI-API (not priority/cost). File cleanup = done manually when passing by, not scheduled."),

    ("vision_deep_research_2026_06_15", "fact",
     "Research synthesis: Atlassian has official MS partnership (Teams, Azure AD SSO/SCIM, Outlook/Excel addons). Docker MCP Toolkit includes Atlassian Rovo MCP, GitHub, Playwright, Fetch, Filesystem, Obsidian. Playwright MCP gives AI agents full browser control. OpenRouter routes to free open-source models. n8n can glue all APIs for end-to-end automation. German salary targets: AI Engineer/Cloud Architect/Cybersecurity Lead = 100k+ EUR. GO! Express uses FreshService not Jira."),
]

for key, category, text in MEMORIES:
    s, r = api("POST", "/api/codex/memory", json={
        "text": text,
        "category": category,
        "source": "user"
    })
    ok = "OK" if s in (200, 201) else f"ERR {s}"
    print(f"  {ok}  [{key}]")
    if s not in (200, 201):
        print(f"       {r}")

# ── 4. Final task state ───────────────────────────────────────────────────────
print("\n=== Final task state ===")
s, data3 = api("GET", "/api/tasks")
for t in data3.get("tasks", []):
    icon = "RUN" if t["status"] == "active" else "---"
    last = (t.get("last_run") or "never")[:10]
    print(f"  {icon}  {t.get('name',''):<32} status={t['status']:<8} last={last}")

print("\nDone.")
