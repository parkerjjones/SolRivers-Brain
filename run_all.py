#!/usr/bin/env python3
"""
run_all.py — one-shot runner for the SolRiver / AlsoEnergy data pipeline.

Runs the full Quick Start sequence on THIS machine (which has live network +
your browser session), so it works even when the Cowork sandbox can't reach
apps.alsoenergy.com.

Just double-click run_all.bat, or run:  python run_all.py
Optional:  python run_all.py --days 14     (alert look-back window, default 7)
"""

import argparse
import datetime as dt
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run(label, cmd):
    print("\n" + "=" * 70)
    print(f"  {label}")
    print("  $ " + " ".join(cmd))
    print("=" * 70, flush=True)
    result = subprocess.run(cmd, cwd=HERE)
    ok = result.returncode == 0
    print(f"  -> {'OK' if ok else 'FAILED (exit %d)' % result.returncode}", flush=True)
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7,
                    help="alert look-back window in days (default 7)")
    ap.add_argument("--skip-deps", action="store_true",
                    help="skip pip install -r requirements.txt")
    args = ap.parse_args()

    py = sys.executable  # use the same interpreter that launched us
    today = dt.date.today()
    d_from = (today - dt.timedelta(days=args.days)).isoformat()
    d_to = (today + dt.timedelta(days=1)).isoformat()  # inclusive of today

    print(f"SolRiver pipeline | look-back {args.days}d | {d_from} -> {d_to}")

    # 0. dependencies
    if not args.skip_deps:
        run("Installing dependencies", [py, "-m", "pip", "install", "-q",
                                        "-r", "requirements.txt"])

    # 1. auth gate — if this fails, the session is genuinely expired
    if not run("Verifying session (ae_auth.py)", [py, "ae_auth.py"]):
        print("\n" + "!" * 70)
        print("  AUTH FAILED — your AlsoEnergy session has expired.")
        print("  Fix: open https://apps.alsoenergy.com/powertrack in Chrome/Edge,")
        print("       F12 -> Network -> right-click any request -> Copy as cURL (bash),")
        print("       paste into alsoenergy_curl.txt (overwrite it), then re-run.")
        print("!" * 70)
        sys.exit(1)

    # 2. loaders, in dependency order
    steps = [
        ("Alerts (last %dd)" % args.days,
         [py, "ae_alert_loader.py", "--from", d_from, "--to", d_to,
          "--excel-only", "--excel", "ae_alerts.xlsx"]),
        ("Hardware inventory", [py, "ae_hardware_loader.py"]),
        ("Sites + live power", [py, "ae_sites_loader.py"]),
        ("Diagnostic rule results", [py, "ae_ruleresults_loader.py"]),
        ("AI site summaries", [py, "ae_ai_summaries.py"]),
        ("Master dashboard", [py, "ae_master_dashboard.py"]),
    ]

    results = {}
    for label, cmd in steps:
        results[label] = run(label, cmd)

    # 3. recap
    print("\n" + "#" * 70)
    print("  RUN COMPLETE — summary")
    print("#" * 70)
    for label, ok in results.items():
        print(f"   [{'OK ' if ok else 'XX '}] {label}")
    failed = [l for l, ok in results.items() if not ok]
    if failed:
        print(f"\n  {len(failed)} step(s) failed — see output above.")
    else:
        print("\n  All outputs refreshed in this folder. OneDrive will sync them.")
    print("#" * 70)


if __name__ == "__main__":
    main()
