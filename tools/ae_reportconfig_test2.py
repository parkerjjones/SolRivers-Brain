#!/usr/bin/env python3
"""
Targeted test of POST /api/reportconfig/new/fromtemplate using real template keys.

Template keys confirmed from /api/reportconfig/public/dashboardlistitems:
  F51163  - Site Validation Report (PV Reports)
  F26433  - Site Production and Alert Summary
  F29395  - Monthly Portfolio Report Template
  F14358  - Operations Report
"""

import json, sys
from datetime import datetime, timezone, timedelta

API_BASE = "https://apps.alsoenergy.com/api"
PORTFOLIO = "C12941"
SITE = "S65787"  # Sunflower Solar

def pp(obj):
    print(json.dumps(obj, indent=2, default=str))

def try_post(session, url, payload, label):
    body = json.dumps(payload)
    print(f"\n--- {label} ---")
    print(f"    Payload ({len(body)}b): {body}")
    r = session.post(url, json=payload, timeout=30)
    print(f"    HTTP {r.status_code}  |  {len(r.content)} bytes")
    if r.content:
        try:
            pp(r.json())
        except Exception:
            print(r.text[:800])
    return r

def try_get(session, url, label):
    print(f"\n--- GET {label} ---")
    r = session.get(url, timeout=30)
    print(f"    HTTP {r.status_code}  |  {len(r.content)} bytes")
    if r.ok and r.content:
        try:
            d = r.json()
            pp(d if isinstance(d, dict) else (d[:2] if isinstance(d, list) else d))
        except Exception:
            print(r.text[:500])
    return r

from ae_auth import get_session
session = get_session()

today = datetime.now(timezone.utc).date()
week_ago = today - timedelta(days=7)

# ── Try POST with real template keys (F-prefix format) ───────────────────────

# Variant 1: fromKey + parentKey (folder), name, language
try_post(session, f"{API_BASE}/reportconfig/new/fromtemplate", {
    "fromKey": "F51163",
    "name": f"Site Validation - {SITE} - {today}",
    "parentKey": PORTFOLIO,
    "language": "en-US",
}, "fromtemplate F51163 (fromKey)")

# Variant 2: templateKey instead of fromKey
try_post(session, f"{API_BASE}/reportconfig/new/fromtemplate", {
    "templateKey": "F51163",
    "name": f"Site Validation - {SITE} - {today}",
    "key": PORTFOLIO,
    "language": "en-US",
}, "fromtemplate F51163 (templateKey)")

# Variant 3: sourceKey
try_post(session, f"{API_BASE}/reportconfig/new/fromtemplate", {
    "sourceKey": "F51163",
    "name": f"Site Validation - {SITE}",
    "destinationKey": PORTFOLIO,
    "siteKey": SITE,
}, "fromtemplate F51163 (sourceKey)")

# Variant 4: just key (the template key IS the key)
try_post(session, f"{API_BASE}/reportconfig/new/fromtemplate", {
    "key": "F51163",
    "name": f"Site Validation - {SITE}",
    "parentKey": PORTFOLIO,
    "siteKey": SITE,
    "language": "en-US",
    "startDate": str(week_ago),
    "endDate": str(today),
}, "fromtemplate F51163 (key + siteKey)")

# Variant 5: try the view/reportconfigs endpoint with site scope
try_post(session, f"{API_BASE}/view/reportconfigs?lastChanged=1900-01-01T00:00:00.000Z", {
    "key": SITE,
}, "view/reportconfigs with site key")

# ── Look for reportconfig under site or portfolio ─────────────────────────────
try_get(session, f"{API_BASE}/reportconfig/{SITE}?lastChanged=1900-01-01T00:00:00.000Z", f"reportconfig for {SITE}")
try_get(session, f"{API_BASE}/reportconfig/F51163", "GET reportconfig F51163 template detail")
try_get(session, f"{API_BASE}/reportconfig/F51163?lastChanged=1900-01-01T00:00:00.000Z", "GET reportconfig F51163 full")

# ── Check if there are any existing report configs in our account ─────────────
# The hierarchy shows "SolRiver Capital : Public Documents : AlsoEnergy Public Docs"
# Try to list what's directly under C12941 as a report folder
try_get(session, f"{API_BASE}/node?lastChanged=1900-01-01T00:00:00.000Z", "node hierarchy (portfolio-level)")

# Try with portfolio POST
try_post(session, f"{API_BASE}/node?lastChanged=1900-01-01T00:00:00.000Z", {"key": PORTFOLIO}, "node hierarchy POST")

print("\n\nDone.")
