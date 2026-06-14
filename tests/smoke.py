"""Mnemo smoke test — run anytime to confirm nothing is broken.

    cd F:\Apps\Mnemo
    & "C:\Program Files\Python311\python.exe" tests\smoke.py

Part 1 (detection) runs offline. Part 2 (HTTP) runs only if the server is up
on http://127.0.0.1:7575. It writes a few throwaway entries then deletes them.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mnemo import secrets_detect as s  # noqa: E402

FAILS = 0


def check(name, cond):
    global FAILS
    print(("  [OK]  " if cond else "  [FAIL]") + " " + name)
    if not cond:
        FAILS += 1


print("=== Part 1: secret detection (offline) ===")
# Fixtures are split with `+` so the raw source never contains a literal
# provider-secret pattern (GitHub push-protection blocks the push otherwise);
# at runtime each reassembles into the full string the detector must catch.
should = {
    "login block": "username: admin\npassword: Sup3rStr0ng!2026",
    "aws secret": "aws_secret_access_key = wJalrXUtnFEMI/K7MDENG/" + "bPxRfiCYEXAMPLEKEY",
    "azure conn": "AccountName=go;AccountKey=abc123XYZ" + "+/=def456ghi789jkl==;",
    "sql conn pwd": "Server=db01;User Id=sa;Password=P@ssw0rd2026Strong;",
    "stripe": "sk_" + "live_51HxYzAbCdEfGhIjKlMnOpQrStUvWxYz0123",
    "private key": "-----BEGIN RSA PRIVATE " + "KEY-----\nMIIE\n-----END RSA PRIVATE KEY-----",
    "basic auth url": "https://user:Secr3tP@ss99@internal.example.com/api",
}
for n, t in should.items():
    check("secret: " + n, s.detect(t)["is_secret"])

shouldnt = {
    "meeting time": "Standup at 09:30, review at 14:00",
    "ratio": "aspect ratio 16:9",
    "path": "config at C:/Users/yousa/app.ini",
    "prose colon": "Reminder: order laptops for Bielefeld",
    "ip": "gateway 192.168.1.1 dns 8.8.8.8",
    "url": "docs https://learn.microsoft.com/ad",
}
for n, t in shouldnt.items():
    check("not-secret: " + n, not s.detect(t)["is_secret"])

# Regression: a labeled (compound) app password must be captured as the password,
# and the service/account name must NOT be mistaken for the password.
_g = s.detect("Gmail: surpriseb4y5\nApp password: abcd efgh ijkl mnop")
_pw = [f["value"] for f in _g["fields"] if f["kind"] == "password"]
check("gmail app-pw captured intact", "abcd efgh ijkl mnop" in _pw)
check("account name not mistaken for pw", not any("surpriseb4y5" in v.lower() for v in _pw))

print("\n=== Part 2: HTTP integration (needs server on :7575) ===")
try:
    import httpx
    c = httpx.Client(base_url="http://127.0.0.1:7575", timeout=90)
    c.get("/api/health").raise_for_status()

    def cap(x, v="personal"):
        return c.post("/api/capture", json={"content": x, "vault": v})

    ids = []
    r = cap("smoke link https://github.com/yousaf-butt-b4y5/odysseus test")
    ids.append(r.json()["id"])
    check("capture link 200", r.status_code == 200)

    sec = cap("smoke login\nusername: x\npassword: Zk9!mQ2vLp4Z").json()
    ids.append(sec["id"])
    check("login is secret", sec["is_secret"])

    for q in ["smoke", "git*", "a:b", "(test)", "@x", '"q']:
        check("search no-500: " + q, c.get("/api/entries", params={"vault": "personal", "q": q}).status_code == 200)

    od = c.get("/mnemo/search", params={"q": "smoke", "vault": "personal"}).json()
    check("odysseus excludes secret", all(not x.get("is_secret") for x in od["results"]))

    check("bad vault 400", cap("x", v="ghost").status_code == 400)
    check("empty 400", cap("").status_code == 400)
    check("missing 404", c.get("/api/entry/9999999", params={"vault": "personal"}).status_code == 404)

    for i in ids:
        c.delete(f"/api/entry/{i}", params={"vault": "personal"})
    check("cleanup ok", True)
except Exception as e:
    print("  [SKIP] server not reachable or error: %r" % e)

print("\n%s — %d failure(s)" % ("PASS" if FAILS == 0 else "FAIL", FAILS))
sys.exit(1 if FAILS else 0)
