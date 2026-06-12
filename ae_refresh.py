#!/usr/bin/env python3
"""
ae_refresh.py — keep the AlsoEnergy session + data endpoints fresh, automatically.

What it does (in order):
  1. SESSION  : validates ae_session.json; if expired, auto-relogs via
                ae_auto_login.py using AE_USERNAME / AE_PASSWORD from .env
                (falls back to alsoenergy_curl.txt if .env is missing)
  2. ENDPOINTS: re-pulls the live data endpoints
                  - alert history   (last N days)   -> ae_alerts.xlsx
                  - sites + power                    -> ae_sites.xlsx
                  - hardware inventory               -> ae_hardware.xlsx   (--full)
                  - rule results                     -> ae_ruleresults.xlsx (--full)
  3. DASHBOARDS: regenerates
                  - dashboards/alerts.html  (operational alert dashboard)
                  - dashboards/index.html + per-site KPI pages (--full)

USAGE
-----
    python ae_refresh.py            # quick: session + alerts + alert dashboard
    python ae_refresh.py --full     # everything (hardware, rules, KPI pages)
    python ae_refresh.py --days 14  # wider alert look-back

SCHEDULING (Windows)
--------------------
Double-click ae_refresh.bat, or register a Task Scheduler job:
    schtasks /create /tn "SolRiver AE Refresh" /sc hourly ^
        /tr "py C:\\path\\to\\ae_refresh.py"
"""

import argparse
import subprocess
import sys
import time
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).parent
PY = sys.executable


def run(label, cmd, timeout=600):
    print(f"\n=== {label} ===")
    t0 = time.time()
    try:
        r = subprocess.run(cmd, cwd=str(HERE), timeout=timeout)
        ok = r.returncode == 0
    except subprocess.TimeoutExpired:
        print(f"  TIMED OUT after {timeout}s")
        ok = False
    print(f"  {'OK' if ok else 'FAILED'} ({time.time()-t0:.0f}s)")
    return ok


def ensure_session():
    """Validate or refresh the session. Returns True if authenticated."""
    print("=== Session check ===")
    try:
        from ae_auth import get_session
        get_session()           # auto-falls-back to cURL / ae_auto_login
        return True
    except RuntimeError as e:
        print(e)
        env = HERE / ".env"
        if not env.exists():
            print(
                "\nTIP: create a .env file with your AlsoEnergy login to make\n"
                "re-auth fully automatic (copy .env.example):\n"
                "    AE_USERNAME=you@solrivercapital.com\n"
                "    AE_PASSWORD=********\n"
            )
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--full", action="store_true",
                    help="also refresh hardware, rule results and KPI dashboards")
    args = ap.parse_args()

    if not ensure_session():
        sys.exit(1)

    d_to = date.today()
    d_from = d_to - timedelta(days=args.days - 1)

    results = {}
    results["alerts"] = run(
        "Alert history",
        [PY, "ae_alert_loader.py", "--from", d_from.isoformat(),
         "--to", d_to.isoformat(), "--excel-only", "--excel", "ae_alerts.xlsx"])
    results["sites"] = run("Sites + live power", [PY, "ae_sites_loader.py"])

    if args.full:
        results["hardware"] = run("Hardware inventory", [PY, "ae_hardware_loader.py"])
        results["rules"] = run("Rule results", [PY, "ae_ruleresults_loader.py"])
        results["kpi"] = run("KPI dashboards", [PY, "ae_kpi_dashboard.py"])

    results["alert_dash"] = run(
        "Operational alert dashboard",
        [PY, "ae_alert_dashboard.py", "--days", str(args.days)])

    print("\n=== Summary ===")
    for k, ok in results.items():
        print(f"  {k:12s} {'OK' if ok else 'FAILED'}")
    if all(results.values()):
        print("\nAll endpoints refreshed. Open dashboards/alerts.html")
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
