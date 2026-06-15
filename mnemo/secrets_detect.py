"""Rule-based secret detection.

Runs BEFORE any LLM call so credentials are never sent to a cloud (or local)
model. Detects passwords, API keys, SSH keys, tokens, and login blocks, and
extracts them into structured fields.
"""
from __future__ import annotations
import math
import re
from typing import Dict, List

# --- High-signal patterns ----------------------------------------------------
SSH_KEY = re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC |DSA |PGP )?PRIVATE KEY-----")
JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]+")

API_KEY_PATTERNS = [
    ("openrouter", re.compile(r"\bsk-or-[A-Za-z0-9_-]{20,}\b")),
    ("openai", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("stripe", re.compile(r"\b[rs]k_(?:live|test)_[A-Za-z0-9]{16,}\b")),
    ("aws_access", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github_pat", re.compile(r"\bghp_[A-Za-z0-9]{36}\b")),
    ("github_fine", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,}\b")),
    ("slack", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("google", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("odysseus", re.compile(r"\body_[A-Za-z0-9_-]{20,}\b")),
    ("bearer", re.compile(r"(?i)bearer\s+[A-Za-z0-9._-]{20,}")),
]

# Credentials embedded in a URL: scheme://user:pass@host
BASIC_AUTH_URL = re.compile(r"\b[a-z][a-z0-9+.\-]*://([^:/?#\s]+):([^@/?#\s]+)@")

# Inline secret keys (connection strings, env files). NOT line-anchored, so it
# catches Password=X;  AccountKey=X;  aws_secret_access_key = X  etc.
INLINE_SECRET = re.compile(
    r"(?i)\b(password|passwort|pwd|kennwort|secret|client[_-]?secret|"
    r"api[_-]?key|apikey|access[_-]?key|account[_-]?key|aws_secret_access_key|"
    r"auth[_-]?token|sas[_-]?token|connection[_-]?string)\b"
    r"\s*[:=]\s*['\"]?([^\s'\";,]{6,})['\"]?"
)
# Keys that are always credentials regardless of how word-like the value is.
_ALWAYS_SECRET_KEYS = {
    "accountkey", "accesskey", "awssecretaccesskey", "apikey", "api_key",
    "clientsecret", "client_secret", "secret", "sastoken", "connectionstring",
}

# label: value  /  label = value   (password, username, host, etc.)
# Up to 3 descriptive words may precede the keyword, so compound labels like
# "App password:", "Gmail Password =", "Account Login:" are matched (the keyword
# must be the last token before the separator). The value may contain spaces, so
# space-separated app passwords ("abcd efgh ijkl mnop") are captured intact.
KV_LINE = re.compile(
    r"(?im)^\s*(?:[A-Za-z][\w.()/-]*\s+){0,3}"
    r"(?P<key>password|passwort|pass|pwd|kennwort|user(?:name)?|login|"
    r"benutzer|account|konto|email|e-?mail|host|server|url|port|token|api[_-]?key|secret|pin)"
    r"\s*[:=]\s*(?P<val>.+?)\s*$"
)

# user:pass shorthand on one line
USERPASS = re.compile(r"\b([A-Za-z0-9._%+-]{2,}@?[A-Za-z0-9._-]*)\s*[:|]\s*(\S{3,})\b")

SECRET_KEYS = {"password", "passwort", "pass", "pwd", "kennwort", "token",
               "api_key", "api-key", "apikey", "secret", "pin"}
USER_KEYS = {"user", "username", "login", "benutzer", "account", "konto", "email", "e-mail"}
# Service / label words that must never be treated as a username in the
# user:pass shorthand (so "Gmail: surpriseb4y5" isn't read as user/password).
LABEL_WORDS = {"gmail", "email", "mail", "login", "account", "konto", "user",
               "username", "password", "passwort", "kennwort", "app", "web",
               "site", "server", "host", "url", "token", "service", "portal", "name"}


def _entropy(s: str) -> float:
    if not s:
        return 0.0
    freq: Dict[str, int] = {}
    for ch in s:
        freq[ch] = freq.get(ch, 0) + 1
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in freq.values())


def _norm_key(k: str) -> str:
    return re.sub(r"[\s_-]+", "", k.lower())


def _looks_like_password(val: str) -> bool:
    """True only for values that resemble a real credential, not prose words.

    Requires length >= 8 and >= 3 of {lower, upper, digit, symbol},
    or very high entropy. Filters out common words like 'host', 'Tuesday'.
    """
    if len(val) < 8 or " " in val:
        return False
    classes = sum([
        bool(re.search(r"[a-z]", val)),
        bool(re.search(r"[A-Z]", val)),
        bool(re.search(r"\d", val)),
        bool(re.search(r"[^A-Za-z0-9]", val)),
    ])
    if classes >= 3:
        return True
    return _entropy(val) >= 3.6 and len(val) >= 12


def detect(text: str) -> Dict:
    """Return {is_secret, kind, fields:[{label,value,kind}], title_hint}."""
    fields: List[Dict] = []
    kinds: List[str] = []

    if SSH_KEY.search(text):
        fields.append({"label": "SSH private key", "value": text.strip(),
                       "kind": "ssh_key", "conf": "high"})
        kinds.append("ssh_key")

    for name, pat in API_KEY_PATTERNS:
        for m in pat.findall(text):
            val = m if isinstance(m, str) else m[0]
            fields.append({"label": f"{name} key", "value": val.strip(),
                           "kind": "api_key", "conf": "high"})
            kinds.append("api_key")

    for m in JWT.findall(text):
        fields.append({"label": "JWT token", "value": m, "kind": "token", "conf": "high"})
        kinds.append("token")

    # Credentials inside a URL (scheme://user:pass@host)
    for um in BASIC_AUTH_URL.finditer(text):
        fields.append({"label": "Username", "value": um.group(1), "kind": "username"})
        fields.append({"label": "Password", "value": um.group(2), "kind": "password", "conf": "high"})
        kinds.append("password")

    # Inline secret keys (connection strings, env vars, AWS/Azure keys)
    for im in INLINE_SECRET.finditer(text):
        key_norm = _norm_key(im.group(1))
        val = im.group(2)
        is_pw = key_norm in ("password", "passwort", "pwd", "kennwort")
        if key_norm in _ALWAYS_SECRET_KEYS or is_pw or _looks_like_password(val):
            fields.append({
                "label": im.group(1).strip().title(),
                "value": val,
                "kind": "password" if is_pw else "api_key",
                # A plain "password:" is a weak signal (low); structured keys
                # (AccountKey, connection strings, strong values) stay high.
                "conf": "low" if is_pw else "high",
            })
            kinds.append("password" if is_pw else "api_key")

    # key: value lines
    for m in KV_LINE.finditer(text):
        key = _norm_key(m.group("key"))
        val = m.group("val").strip()
        if not val or val.lower() in ("none", "null", "-"):
            continue
        if key in {_norm_key(k) for k in SECRET_KEYS}:
            fields.append({"label": m.group("key").strip().title(),
                           "value": val, "kind": "password", "conf": "low"})
            kinds.append("password")
        elif key in {_norm_key(k) for k in USER_KEYS}:
            fields.append({"label": m.group("key").strip().title(),
                           "value": val, "kind": "username"})
        elif key in ("host", "server", "url", "port"):
            fields.append({"label": m.group("key").strip().title(),
                           "value": val, "kind": "meta"})

    # If we found a username but no password yet, scan user:pass shorthand
    has_pw = any(f["kind"] == "password" for f in fields)
    _url_schemes = {"http", "https", "ftp", "ftps", "ssh", "git", "file", "mailto"}
    if not has_pw:
        for um in USERPASS.finditer(text):
            user, pw = um.group(1), um.group(2)
            seg = text[max(0, um.start() - 3):um.end() + 3]
            # skip URLs (https://…), time (10:30), scheme:path, and lines where
            # the "user" is really a service/label word (e.g. "Gmail: name") —
            # otherwise the account name gets mis-saved as the password.
            if ("://" in seg or pw.startswith("/")
                    or user.lower() in _url_schemes or user.lower() in LABEL_WORDS):
                continue
            if pw.isdigit():
                continue
            if _looks_like_password(pw):
                fields.append({"label": "Username", "value": user, "kind": "username"})
                fields.append({"label": "Password", "value": pw, "kind": "password", "conf": "low"})
                kinds.append("password")
                break

    # De-duplicate fields (INLINE_SECRET and KV_LINE can match the same line).
    seen = set()
    deduped = []
    for f in fields:
        key = (f["kind"], f["value"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(f)
    fields = deduped

    # Confidence + shape. High-confidence patterns (API/SSH keys, JWTs,
    # connection strings, URL creds) always protect. A WEAK password signal
    # (a "password:" line or user:pass shorthand) only flags the whole entry as
    # secret when the note is credential-SHAPED (short) — so a long note
    # (to-dos, CV, prompts) with one stray key:value line stays a readable note
    # instead of being masked.
    _lines = [l for l in text.splitlines() if l.strip()]
    cred_shaped = len(_lines) <= 8 and len(text) <= 400
    high = any(f.get("conf") == "high" and f["kind"] in ("password", "api_key", "ssh_key", "token")
               for f in fields)
    low_pw = any(f.get("conf") == "low" and f["kind"] == "password" for f in fields)
    is_secret = high or (low_pw and cred_shaped)

    title_hint = ""
    if is_secret:
        primary = next((k for k in ("ssh_key", "api_key", "token", "password")
                        if k in kinds), "credential")
        label_map = {"ssh_key": "SSH Key", "api_key": "API Key",
                     "token": "Token", "password": "Login"}
        title_hint = label_map.get(primary, "Credential")

    return {
        "is_secret": is_secret,
        "kind": kinds[0] if kinds else "",
        "fields": fields,
        "title_hint": title_hint,
    }
