#!/usr/bin/env python3
"""
ae_auto_login.py — automatically refresh the AlsoEnergy session via Playwright.

Reads credentials from .env (AE_USERNAME, AE_PASSWORD), logs in headlessly,
extracts session cookies, and saves them to ae_session.json so all other
scripts continue working without manual cURL pasting.

Usage:
    python ae_auto_login.py          # headless refresh
    python ae_auto_login.py --show   # show browser window (debug)
"""

import argparse
import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    sys.exit("python-dotenv not installed.  Run: pip install python-dotenv")

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
except ImportError:
    sys.exit(
        "playwright not installed.\n"
        "  pip install playwright\n"
        "  python -m playwright install chromium"
    )

from ae_auth import SESSION_FILE, HEALTH_URL, _save, _load, _build_session_from

APP_URL = "https://apps.alsoenergy.com/powertrack"


def _credentials():
    load_dotenv()
    u = os.environ.get("AE_USERNAME")
    p = os.environ.get("AE_PASSWORD")
    if not u or not p:
        sys.exit(
            "Credentials missing.  Create a .env file:\n"
            "  AE_USERNAME=your@email.com\n"
            "  AE_PASSWORD=yourpassword\n"
        )
    return u, p


def _static_headers():
    """Return the static ae_s / ae_v headers from the existing session cache."""
    cache = _load()
    if cache and cache.get("headers"):
        return cache["headers"]
    # Fall back to cURL file
    curl = Path("alsoenergy_curl.txt")
    if curl.exists():
        from ae_auth import _parse_curl
        headers, _ = _parse_curl(str(curl))
        return headers
    return {}


def run_login(headless=True):
    username, password = _credentials()
    static_headers = _static_headers()

    print(f"[ae_auto_login] Launching {'headless' if headless else 'visible'} browser...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context()
        page = context.new_page()

        print("[ae_auto_login] Navigating to login page...")
        page.goto(APP_URL, wait_until="networkidle", timeout=30000)

        # Step 1 — username (Auth0 two-step flow: username → Continue → password → Submit)
        try:
            page.wait_for_selector("input[name='username']", timeout=10000)
        except PWTimeout:
            browser.close()
            sys.exit("[ae_auto_login] Could not find username field — login page may have changed.")

        print("[ae_auto_login] Entering username...")
        page.fill("input[name='username']", username)
        page.click("button[type='submit']")

        # Step 2 — password appears after Continue
        try:
            page.wait_for_selector("input[type='password']", timeout=10000)
        except PWTimeout:
            browser.close()
            sys.exit("[ae_auto_login] Password field did not appear after username — check credentials or login flow.")

        print("[ae_auto_login] Entering password...")
        page.fill("input[type='password']", password)
        page.click("button[type='submit']")

        # Wait for redirect back into PowerTrack
        try:
            page.wait_for_url("**/powertrack**", timeout=20000)
        except PWTimeout:
            error_el = page.query_selector(
                "[class*='error'], [class*='alert'], [role='alert']"
            )
            msg = error_el.inner_text().strip() if error_el else "timed out"
            browser.close()
            sys.exit(f"[ae_auto_login] Login failed: {msg}")

        print("[ae_auto_login] Logged in — extracting cookies...")
        raw_cookies = context.cookies()
        cookies_dict = {
            c["name"]: c["value"]
            for c in raw_cookies
            if "alsoenergy.com" in c.get("domain", "")
        }
        browser.close()

    _save(static_headers, cookies_dict)
    print(f"[ae_auto_login] Saved to {SESSION_FILE}")

    # Quick health check
    s = _build_session_from(static_headers, cookies_dict)
    r = s.get(HEALTH_URL, timeout=15)
    if r.ok:
        sites = r.json().get("sites", [])
        print(f"[ae_auto_login] Session verified — {len(sites)} sites accessible")
    else:
        print(f"[ae_auto_login] Warning: health check returned {r.status_code}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", action="store_true", help="show browser window")
    args = ap.parse_args()
    run_login(headless=not args.show)
