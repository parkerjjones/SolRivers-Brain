#!/usr/bin/env python3
"""
Explores the AlsoEnergy reportconfig API endpoints.

Discovers available report templates and attempts to create a report
from a template via POST /api/reportconfig/new/fromtemplate.

USAGE
-----
    python ae_reportconfig_explorer.py
    python ae_reportconfig_explorer.py --portfolio C12941
"""

import argparse
import json
import sys
from datetime import datetime, timezone, timedelta

API_BASE  = "https://apps.alsoenergy.com/api"
PORTFOLIO = "C12941"


def pp(obj):
    print(json.dumps(obj, indent=2, default=str))


def get_session():
    from ae_auth import get_session as _gs
    return _gs()


def try_get(session, url, label):
    print(f"\n--- GET {label} ---")
    print(f"    {url}")
    r = session.get(url, timeout=30)
    print(f"    HTTP {r.status_code}  |  {len(r.content)} bytes")
    if r.ok and r.content:
        try:
            data = r.json()
            pp(data if isinstance(data, dict) else data[:3] if isinstance(data, list) else data)
            return data
        except Exception:
            print(r.text[:500])
    else:
        print(r.text[:300] if r.text else "(empty body)")
    return None


def try_post(session, url, payload, label):
    print(f"\n--- POST {label} ---")
    print(f"    {url}")
    body = json.dumps(payload)
    print(f"    Payload ({len(body)} bytes): {body[:300]}")
    r = session.post(url, json=payload, timeout=30)
    print(f"    HTTP {r.status_code}  |  {len(r.content)} bytes")
    if r.content:
        try:
            data = r.json()
            pp(data)
            return data
        except Exception:
            print(r.text[:500])
    else:
        print("(empty body)")
    return None


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--portfolio", default=PORTFOLIO)
    ap.add_argument("--site", default=None, help="Site key for site-level reports")
    args = ap.parse_args()

    session = get_session()
    portfolio = args.portfolio
    site = args.site or "S65787"  # Sunflower Solar as default test site

    today = datetime.now(timezone.utc).date()
    week_ago = today - timedelta(days=7)

    print(f"\nPortfolio: {portfolio}")
    print(f"Site:      {site}")
    print(f"Date range: {week_ago} to {today}")

    # ── 1. List public templates ──────────────────────────────────────────
    templates_data = try_get(
        session,
        f"{API_BASE}/reportconfig/public/dashboardlistitems",
        "Public Report Templates"
    )

    # ── 2. Try portfolio-level report configs ─────────────────────────────
    try_get(
        session,
        f"{API_BASE}/reportconfig/{portfolio}?lastChanged=1900-01-01T00:00:00.000Z",
        f"Portfolio report configs ({portfolio})"
    )

    # ── 3. Try listing report templates directly ──────────────────────────
    try_get(
        session,
        f"{API_BASE}/reportconfig/templates",
        "Report templates list"
    )

    try_get(
        session,
        f"{API_BASE}/reportconfig/public/templates",
        "Public templates"
    )

    # ── 4. Try POST /api/reportconfig/new/fromtemplate ────────────────────
    # Content-length was 372 in the captured request, so the payload is ~372 bytes.
    # We try several plausible payloads.

    # Attempt A: minimal — just template name + key
    if templates_data and isinstance(templates_data, list) and templates_data:
        first_template = templates_data[0]
        template_id = first_template.get("id") or first_template.get("key") or first_template.get("templateId")
        if template_id:
            try_post(
                session,
                f"{API_BASE}/reportconfig/new/fromtemplate",
                {
                    "templateId": template_id,
                    "name": f"Weekly Report {week_ago} to {today}",
                    "key": portfolio,
                    "from": str(week_ago),
                    "to": str(today),
                },
                "fromtemplate (template from list)"
            )

    # Attempt B: site validation report style
    try_post(
        session,
        f"{API_BASE}/reportconfig/new/fromtemplate",
        {
            "templateId": "SiteValidation",
            "name": f"Site Validation - {site}",
            "siteKey": site,
            "portfolioKey": portfolio,
            "from": str(week_ago),
            "to": str(today),
            "language": "en-US",
            "format": "pdf",
        },
        "fromtemplate (SiteValidation)"
    )

    # Attempt C: weekly health report style
    try_post(
        session,
        f"{API_BASE}/reportconfig/new/fromtemplate",
        {
            "templateId": "PortfolioHealthWeekly",
            "name": f"Portfolio Health Weekly - {week_ago}",
            "key": portfolio,
            "from": str(week_ago),
            "to": str(today),
            "language": "en-US",
            "timezone": "America/New_York",
        },
        "fromtemplate (PortfolioHealthWeekly)"
    )

    # Attempt D: mirror the referer portfolio C18496 to check if it's portfolio-scoped
    try_post(
        session,
        f"{API_BASE}/reportconfig/new/fromtemplate",
        {
            "portfolioKey": portfolio,
            "templateKey": "default",
            "reportName": f"Weekly Health {week_ago}",
            "startDate": str(week_ago),
            "endDate": str(today),
        },
        "fromtemplate (portfolioKey + templateKey)"
    )

    # ── 5. Try view/reportconfigs endpoint ────────────────────────────────
    try_post(
        session,
        f"{API_BASE}/view/reportconfigs?lastChanged=1900-01-01T00:00:00.000Z",
        {"key": portfolio},
        "view/reportconfigs"
    )

    # ── 6. Try generating/downloading a report ────────────────────────────
    try_get(
        session,
        f"{API_BASE}/reportconfig/public/dashboardlistitems?key={portfolio}",
        "Public templates (portfolio-filtered)"
    )

    print("\n\nDone — review output above to identify valid template IDs and payload structure.")
