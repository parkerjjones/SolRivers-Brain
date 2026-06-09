#!/usr/bin/env python3
"""
AlsoEnergy session manager — never paste cURL again.

HOW SESSIONS ACTUALLY WORK
---------------------------
AlsoEnergy uses ASP.NET Identity cookies for server-side sessions.
The AESession + .AspNet.Cookies cookies are what authenticate you.
These last HOURS OR DAYS, not 20 minutes.

The AESessionC1 cookie contains an OAuth JWT with expires_in=1200,
but the server does NOT use that JWT for API auth — it uses the
cookie-based session. So we can ignore the JWT expiry.

WHAT CAUSES 500s
-----------------
  - Very stale cookies (days-old, server-side session expired)
  - Wrong AWSALB load-balancer routing cookie (can cause 500 too)

STRATEGY
---------
1. Save cookies to ae_session.json the first time
2. Reuse them for every subsequent run — no cURL needed
3. Auto-detect real auth failure (401/403/500 with empty body)
4. Only then prompt: "paste a new cURL"

You typically need a new cURL every few days, not every 20 minutes.

USAGE IN YOUR SCRIPTS
---------------------
    from ae_auth import get_session, handle_response

    session = get_session()
    r = session.get("https://apps.alsoenergy.com/api/...")
    handle_response(r)   # raises clear error if auth failed
"""

import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

import requests

CURL_FILE    = "alsoenergy_curl.txt"
SESSION_FILE = "ae_session.json"
BASE_URL     = "https://apps.alsoenergy.com"
API_BASE     = f"{BASE_URL}/api"
# Session health-check endpoint (cheap, always works when authenticated)
HEALTH_URL   = f"{API_BASE}/view/portfolio/C12941"


# -----------------------------------------------------------------------
# INTERNAL HELPERS
# -----------------------------------------------------------------------

def _parse_curl(path):
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read().replace("\\\r\n", " ").replace("\\\n", " ")
    tokens = shlex.split(raw)
    headers, cookie_str = {}, None
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t in ("-H", "--header"):
            k, _, v = tokens[i + 1].partition(":")
            headers[k.strip()] = v.strip()
            i += 2
        elif t in ("-b", "--cookie"):
            cookie_str = tokens[i + 1]
            i += 2
        else:
            i += 1
    return headers, cookie_str


def _cookies_dict(cookie_str):
    out = {}
    for part in (cookie_str or "").split("; "):
        if "=" in part:
            k, _, v = part.partition("=")
            out[k.strip()] = v.strip()
    return out


def _build_session_from(headers_dict, cookies_dict):
    s = requests.Session()
    s.headers.update({k: v for k, v in headers_dict.items() if k.lower() != "cookie"})
    for k, v in cookies_dict.items():
        s.cookies.set(k, v)
    return s


def _save(headers_dict, cookies_dict):
    Path(SESSION_FILE).write_text(
        json.dumps({"headers": headers_dict, "cookies": cookies_dict,
                    "saved_at": time.time()}, indent=2)
    )


def _load():
    try:
        return json.loads(Path(SESSION_FILE).read_text())
    except Exception:
        return None


def _is_auth_failure(r):
    """True when the server actively rejected our credentials."""
    if r.status_code in (401, 403, 419):
        return True
    if r.status_code == 500 and not r.text.strip():
        return True   # AlsoEnergy returns empty 500 for expired sessions
    return False


# -----------------------------------------------------------------------
# PUBLIC API
# -----------------------------------------------------------------------

def get_session(verbose=True):
    """
    Return an authenticated requests.Session.

    Tries the session cache first, then falls back to the cURL file.
    Only asks you to paste a new cURL if the server actually rejects us.
    """

    def _log(msg):
        if verbose:
            print(f"[ae_auth] {msg}")

    # ── 1. Try cached session ──────────────────────────────────────────
    cache = _load()
    if cache:
        headers = cache["headers"]
        cookies = cache["cookies"]
        age_hours = (time.time() - cache.get("saved_at", 0)) / 3600
        _log(f"Loaded session cache ({age_hours:.1f}h old) - testing...")
        s = _build_session_from(headers, cookies)
        r = s.get(HEALTH_URL, timeout=15)
        if r.ok:
            _log(f"Cached session is alive  ({r.status_code})")
            return s
        if _is_auth_failure(r):
            _log("Cached session expired — falling back to cURL file")
        else:
            _log(f"Unexpected response ({r.status_code}) — trying cURL file")

    # ── 2. Read cURL file ──────────────────────────────────────────────
    if not os.path.exists(CURL_FILE):
        raise RuntimeError(
            f"\nCould not find {CURL_FILE}.\n"
            f"In Chrome/Edge: open PowerTrack → DevTools (F12) → Network tab\n"
            f"→ find ANY request → right-click → Copy as cURL (bash)\n"
            f"→ paste into {CURL_FILE}\n"
        )

    _log(f"Reading {CURL_FILE}...")
    headers, cookie_str = _parse_curl(CURL_FILE)
    cookies = _cookies_dict(cookie_str)

    s = _build_session_from(headers, cookies)
    r = s.get(HEALTH_URL, timeout=15)

    if r.ok:
        _log(f"cURL session is alive  ({r.status_code})")
        _save(headers, cookies)
        _log(f"Saved to {SESSION_FILE} — next runs won't need the cURL file")
        return s

    if _is_auth_failure(r):
        # ── 3. Try automated re-login via ae_auto_login.py ────────────────
        auto_login_script = Path(__file__).parent / "ae_auto_login.py"
        if auto_login_script.exists():
            _log("Attempting automatic re-login via ae_auto_login.py...")
            result = subprocess.run(
                [sys.executable, str(auto_login_script)],
                cwd=str(auto_login_script.parent),
            )
            if result.returncode == 0:
                cache = _load()
                if cache:
                    s2 = _build_session_from(cache["headers"], cache["cookies"])
                    r2 = s2.get(HEALTH_URL, timeout=15)
                    if r2.ok:
                        _log("Auto-login succeeded!")
                        return s2
            _log("Auto-login failed — falling back to manual instructions")

        raise RuntimeError(
            f"\nAuthentication failed (HTTP {r.status_code}).\n"
            f"Option 1 — automated: ensure .env has AE_USERNAME and AE_PASSWORD,\n"
            f"  then run: python ae_auto_login.py\n"
            f"Option 2 — manual: paste a fresh cURL into {CURL_FILE}:\n"
            f"  Chrome/Edge → PowerTrack → F12 → Network → any request\n"
            f"  → right-click → Copy as cURL (bash) → save to {CURL_FILE}\n"
        )

    # Non-auth error — return session anyway (let caller decide)
    _log(f"Warning: health check returned {r.status_code} — session may be partially valid")
    _save(headers, cookies)
    return s


def handle_response(r, context=""):
    """
    Raise a clear RuntimeError if the response looks like an auth failure.
    Call this after any important request.
    """
    if _is_auth_failure(r):
        raise RuntimeError(
            f"Auth failure ({r.status_code}){' on ' + context if context else ''}.\n"
            f"Paste a fresh cURL into {CURL_FILE} and rerun."
        )
    r.raise_for_status()
    return r


# -----------------------------------------------------------------------
# SMOKE TEST
# -----------------------------------------------------------------------
if __name__ == "__main__":
    s = get_session()
    r = s.get(HEALTH_URL, timeout=15)
    sites = r.json().get("sites", []) if r.ok else []
    print(f"\nStatus: HTTP {r.status_code}  |  {len(sites)} sites")
    if sites:
        print("First 5:", [x["name"] for x in sites[:5]])
    print(f"\nSession saved to {SESSION_FILE}  —  all scripts will reuse this automatically.")
