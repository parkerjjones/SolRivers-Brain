#!/usr/bin/env python3
"""
Whitetail (S59656) late-start morning investigation — data extraction.

Pulls:
  1. Alarm/event log for ALL site devices (target mornings + full Feb–May 2026)
  2. Per-inverter morning time-series (requires chart endpoint — see notes)
  3. Revenue/production meter morning data (same dependency)
  4. Inverter config/settings (what the API exposes)

Output files:
  alarms_whitetail.csv        — Pull 1
  morning_timeseries.csv      — Pull 2 (if chart endpoint available)
  meter_morning.csv           — Pull 3 (if chart endpoint available)
  inverter_settings.csv       — Pull 4
"""

import csv
import json
import re
import sys
import time
from datetime import date, datetime, timedelta

from ae_auth import get_session, handle_response

API_BASE = "https://apps.alsoenergy.com/api"
SITE_KEY = "S59656"
SITE_NAME = "Whitetail"

TZ_OFFSET_MIN = 300  # US/Eastern = UTC-5 (300 min); DST handled by the platform

TARGET_DATES = [
    "2026-02-22", "2026-02-27",
    "2026-03-01", "2026-03-04", "2026-03-05", "2026-03-06", "2026-03-27",
    "2026-03-30", "2026-03-31",
    "2026-04-01", "2026-04-02", "2026-04-03", "2026-04-04", "2026-04-05",
    "2026-04-07", "2026-04-10", "2026-04-11", "2026-04-12", "2026-04-13",
    "2026-04-14", "2026-04-15", "2026-04-17", "2026-04-18", "2026-04-26",
    "2026-04-29",
    "2026-05-07", "2026-05-09", "2026-05-10", "2026-05-11", "2026-05-12",
]

MORNING_START_H = 5
MORNING_END_H = 11

PRIMARY_INVERTERS = [7, 35, 51, 78]
SECONDARY_INVERTERS = [2, 40]
CONTEXT_INVERTERS = [5, 39, 52, 71, 72]
ALL_INTEREST = PRIMARY_INVERTERS + SECONDARY_INVERTERS + CONTEXT_INVERTERS

FLAG_PATTERNS = [
    (r"insulation\s*resistance|low\s*insulation|\biso\s*fault|\briso\b|fault\s*0?39", "ISO/Insulation"),
    (r"leakage\s*current|residual\s*current|fault\s*0?12", "Leakage/Residual Current"),
    (r"comm\s*(?:loss|fail)|communi?cation\s+(?:error|loss|fail)|heartbeat|gateway|data.?logger\s*offline|no\s*data|device\s+communication", "Communication"),
    (r"recloser|ac\s*breaker|grid\s*trip|islanding", "Recloser/Grid"),
]

ALERT_URL = f"{API_BASE}/view/alerthistory"
WINDOW_DAYS = 31
SLEEP = 1.2


# ── Helpers ──────────────────────────────────────────────────────────────

def parse_ts(v):
    if not v:
        return None
    s = str(v).strip()
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S", "%m/%d/%Y %I:%M:%S %p"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def split_event_code(s):
    if not s:
        return None, None
    m = re.match(r"^\s*(\d+)\s*-\s*(.+)$", str(s))
    if m:
        return int(m.group(1)), m.group(2).strip()
    return None, str(s).strip()


def flag_alarm(code_str, name_str, desc_str):
    text = f"{code_str or ''} {name_str or ''} {desc_str or ''}".lower()
    flags = []
    for pat, label in FLAG_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            flags.append(label)
    return "; ".join(flags) if flags else ""


def windows(d_from, d_to, step):
    cur = d_from
    while cur <= d_to:
        end = min(cur + timedelta(days=step - 1), d_to)
        yield cur, end
        cur = end + timedelta(days=1)


# ── Resolve hardware ─────────────────────────────────────────────────────

def resolve_hardware(session):
    print(f"Resolving hardware for {SITE_KEY} ({SITE_NAME})...")
    r = session.get(
        f"{API_BASE}/scriptsite/{SITE_KEY}?lastChanged=1900-01-01T00:00:00.000Z",
        timeout=30,
    )
    handle_response(r, "scriptsite")
    data = r.json()
    hw_list = data.get("hardware", [])
    print(f"  {len(hw_list)} total hardware items")

    inv_map = {}
    meter = None
    poa = None
    all_devices = {}

    for h in hw_list:
        key = h.get("key", "")
        name = h.get("name", "")
        fc = h.get("functionCode", -1)
        all_devices[key] = {"name": name, "fc": fc}

        if fc == 1:
            m = re.search(r"Inverter\s+(\d+)", name)
            if m:
                inv_num = int(m.group(1))
                inv_map[inv_num] = key

        if fc == 2 and meter is None:
            meter = key

        if "POA" in name and fc == 5:
            poa = key

    print(f"  Inverters: {len(inv_map)}")
    print(f"  Production meter: {meter}")
    print(f"  POA pyranometer: {poa}")
    print()

    print("  Resolved inverter IDs:")
    for num in sorted(ALL_INTEREST):
        hk = inv_map.get(num, "NOT FOUND")
        role = (
            "PRIMARY" if num in PRIMARY_INVERTERS
            else "SECONDARY" if num in SECONDARY_INVERTERS
            else "CONTEXT"
        )
        print(f"    Inverter {num:3d} -> {hk:10s}  ({role})")
    print()

    return inv_map, meter, poa, all_devices, data


# ── PULL 1: Alarm / event log ────────────────────────────────────────────

def fetch_alerts(session, site_key, d_from, d_to, label=""):
    all_records = []
    for w_start, w_end in windows(d_from, d_to, WINDOW_DAYS):
        payload = {
            "key": site_key,
            "from": w_start.isoformat(),
            "to": w_end.isoformat(),
            "offset": TZ_OFFSET_MIN,
        }
        r = session.post(ALERT_URL, json=payload, timeout=60)
        if r.status_code == 204:
            continue
        handle_response(r, f"alerthistory {w_start}..{w_end}")
        data = r.json()
        recs = data.get("list", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
        all_records.extend(recs)
        print(f"    {label}{w_start}..{w_end}: {len(recs)} alerts")
        time.sleep(SLEEP)
    return all_records


def normalize_alert(rec):
    code, name = split_event_code(rec.get("eventCode"))
    start = parse_ts(rec.get("start"))
    end = parse_ts(rec.get("end"))
    dur_min = None
    if start and end:
        dur_min = round((end - start).total_seconds() / 60, 1)
    code_str = str(code) if code else ""
    name_str = name or ""
    desc_str = rec.get("description") or ""
    return {
        "device_name": rec.get("hardwareName") or rec.get("siteName") or "",
        "hardware_key": rec.get("hardwareKey") or "",
        "asset_code": rec.get("assetCode") or "",
        "alarm_code": code_str,
        "alarm_name": name_str,
        "description": desc_str,
        "severity": rec.get("severity"),
        "category": rec.get("category"),
        "start_utc": start.isoformat() if start else "",
        "end_utc": end.isoformat() if end else "",
        "duration_min": dur_min if dur_min is not None else "",
        "is_resolved": rec.get("isResolved", False),
        "resolved_by": rec.get("resolvedByName") or "",
        "flag": flag_alarm(code_str, name_str, desc_str),
    }


def pull_alarms(session):
    print("=" * 60)
    print("PULL 1: Alarm / event log")
    print("=" * 60)

    # Part A: full range Feb 1 – May 31 for all inverter alarms
    print("\n  [A] Full range 2026-02-01 to 2026-05-31 (site-wide)...")
    full_recs = fetch_alerts(
        session, SITE_KEY,
        date(2026, 2, 1), date(2026, 5, 31),
        label="full ",
    )

    # Part B: target-date morning windows — already included in full range,
    #         but we tag them separately
    target_set = set(TARGET_DATES)

    # Normalize all
    rows = []
    seen_ids = set()
    for rec in full_recs:
        aid = str(rec.get("alertId", ""))
        if aid in seen_ids:
            continue
        seen_ids.add(aid)
        row = normalize_alert(rec)
        rows.append(row)

    # Tag morning overlaps
    for row in rows:
        start = parse_ts(row["start_utc"]) if row["start_utc"] else None
        end = parse_ts(row["end_utc"]) if row["end_utc"] else None
        overlap_dates = []
        for td_str in TARGET_DATES:
            td = date.fromisoformat(td_str)
            # Morning window in UTC (EST+5h): 05:00 EST = 10:00 UTC, 11:00 EST = 16:00 UTC
            # But during EDT (Mar–Nov): 05:00 EDT = 09:00 UTC, 11:00 EDT = 15:00 UTC
            # Use conservative overlap: just check if alarm overlaps the date at all
            # and the morning hours. Since we have UTC timestamps and site is EST/EDT,
            # we check 09:00-16:00 UTC as the broad morning window.
            morning_start = datetime(td.year, td.month, td.day, 9, 0, 0)
            morning_end = datetime(td.year, td.month, td.day, 16, 0, 0)
            if start and start <= morning_end:
                if not end or end >= morning_start:
                    overlap_dates.append(td_str)
        row["target_morning_overlap"] = "; ".join(overlap_dates)

    # Write CSV
    fieldnames = [
        "device_name", "hardware_key", "asset_code", "alarm_code", "alarm_name",
        "description", "severity", "category", "start_utc", "end_utc",
        "duration_min", "is_resolved", "resolved_by", "flag", "target_morning_overlap",
    ]
    out_path = "alarms_whitetail.csv"
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    # Summary
    flagged = sum(1 for r in rows if r["flag"])
    morning_hits = sum(1 for r in rows if r["target_morning_overlap"])
    dates_span = ""
    starts = [r["start_utc"] for r in rows if r["start_utc"]]
    if starts:
        dates_span = f"{min(starts)[:10]} to {max(starts)[:10]}"
    print(f"\n  Saved: {out_path}")
    print(f"    {len(rows)} unique alarms, date span: {dates_span}")
    print(f"    {flagged} flagged (ISO/leakage/comm/recloser)")
    print(f"    {morning_hits} overlapping target morning windows")
    return rows


# ── PULL 2: Per-inverter morning time-series ─────────────────────────────

def pull_timeseries(session, inv_map, poa_key):
    print("\n" + "=" * 60)
    print("PULL 2: Per-inverter morning time-series")
    print("=" * 60)

    # The chart endpoint (POST /api/view/chart) payload shape is unknown.
    # All tested payload structures return HTTP 500 with empty body.
    # To unlock this pull, capture a Copy-as-cURL (bash) from DevTools:
    #   1. Open PowerTrack → navigate to Whitetail → Chart Builder
    #   2. Add an inverter channel (e.g., DC Voltage for Inverter 7)
    #   3. Open DevTools (F12) → Network tab
    #   4. Click "Apply" or change the date range
    #   5. Find the POST to /api/view/chart → right-click → Copy as cURL (bash)
    #   6. Paste it into a file and share it
    #
    # Available data registers per inverter (from scriptsite):
    #   DC: Vdc1, Idc1 (DC Voltage, DC Current — single MPPT)
    #   AC: VacAB/BC/CA, IacA/B/C, KwAC, KVA, KVAR, PowerFactor
    #   Energy: KWH
    #   Status: several status registers
    # POA pyranometer (Hukseflux SR-30 - POA):
    #   Sun (POA irradiance, W/m²)

    print("\n  STATUS: BLOCKED — POST /api/view/chart returns HTTP 500")
    print("  for all tested payload shapes. The endpoint exists but the")
    print("  request body format is undocumented.")
    print()
    print("  TO UNLOCK: Capture a chart POST from DevTools (see above).")
    print()
    print("  Available channels per inverter (live dataRegisters):")
    print("    DC Voltage: Vdc1  |  DC Current: Idc1")
    print("    AC Power: KwAC   |  AC Voltage: VacAB/BC/CA")
    print("    AC Current: IacA/B/C  |  Energy: KWH")
    print(f"  POA sensor: {poa_key} (Hukseflux SR-30 - POA, field: Sun)")
    print()
    print("  morning_timeseries.csv: NOT GENERATED (chart endpoint required)")
    return False


# ── PULL 3: Revenue / production meter ────────────────────────────────────

def pull_meter(session, meter_key):
    print("\n" + "=" * 60)
    print("PULL 3: Revenue / production meter morning data")
    print("=" * 60)

    print(f"\n  Meter: {meter_key} (SEL-735 Production Meter)")
    print("  Available channels (live dataRegisters):")
    print("    KW (Real power), KWHnet (Total energy), KWHdel (Export energy)")
    print("    KWHrec (Import energy), KVAR, KVA, PowerFactor")
    print("    VacA/B/C (Phase voltages), IacA/B/C (Phase currents)")
    print()
    print("  STATUS: BLOCKED — same chart endpoint dependency as Pull 2.")
    print("  meter_morning.csv: NOT GENERATED")
    return False


# ── PULL 4: Inverter config / settings ────────────────────────────────────

def pull_inverter_settings(session, inv_map, site_data):
    print("\n" + "=" * 60)
    print("PULL 4: Inverter config / settings")
    print("=" * 60)

    hw_list = site_data.get("hardware", [])
    hw_by_key = {h["key"]: h for h in hw_list}

    rows = []
    target_nums = PRIMARY_INVERTERS  # 7, 35, 51, 78

    for num in target_nums:
        hk = inv_map.get(num)
        if not hk or hk not in hw_by_key:
            print(f"  Inverter {num}: NOT FOUND")
            continue

        hw = hw_by_key[hk]
        settings = hw.get("settings", [])
        data_regs = hw.get("dataRegisters", [])

        # Look for ISO / insulation resistance / startup voltage in settings
        iso_setting = None
        startup_v = None
        for s in settings:
            sname = (s.get("name") or "").lower()
            if "iso" in sname or "insulation" in sname or "riso" in sname:
                iso_setting = s
            if "startup" in sname or "vstart" in sname:
                startup_v = s

        # Check data registers for any config-like values
        iso_reg = None
        for dr in data_regs:
            dname = (dr.get("dataName") or "").lower()
            mname = (dr.get("modBusName") or "").lower()
            if "iso" in dname or "insulation" in dname or "riso" in dname:
                iso_reg = dr
            if "iso" in mname or "insulation" in mname:
                iso_reg = dr

        row = {
            "inverter": f"Inverter {num}",
            "hardware_key": hk,
            "serial_num": hw.get("serialNum") or "",
            "settings_count": len(settings),
            "all_settings": json.dumps(settings) if settings else "",
            "iso_setting_found": "YES" if iso_setting else "NO",
            "iso_setting_value": json.dumps(iso_setting) if iso_setting else "",
            "startup_v_found": "YES" if startup_v else "NO",
            "startup_v_value": json.dumps(startup_v) if startup_v else "",
            "iso_register_found": "YES" if iso_reg else "NO",
            "iso_register_value": json.dumps(iso_reg, default=str) if iso_reg else "",
        }
        rows.append(row)
        print(f"  Inverter {num} ({hk}): {len(settings)} settings, ISO={'found' if iso_setting or iso_reg else 'not exposed'}")

    if not rows:
        print("  No inverter settings found")
        return

    out_path = "inverter_settings.csv"
    fieldnames = list(rows[0].keys())
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    print(f"\n  Saved: {out_path}")
    print(f"    {len(rows)} inverters")
    print()
    print("  NOTE: The AlsoEnergy API exposes only basic device comm settings")
    print("  (Modbus register offset, baud rate) via the scriptsite endpoint.")
    print("  Inverter-level protection thresholds (ISO/Riso, startup voltage)")
    print("  are NOT exposed in this API — they must be read from the Sungrow")
    print("  iSolarCloud portal or directly from the inverter via Modbus.")


# ── MAIN ──────────────────────────────────────────────────────────────────

def main():
    print(f"Whitetail Late-Start Morning Investigation")
    print(f"Site: {SITE_NAME} ({SITE_KEY})")
    print(f"Target dates: {len(TARGET_DATES)} mornings, 05:00-11:00 local")
    print(f"Primary inverters: {PRIMARY_INVERTERS}")
    print(f"Secondary inverters: {SECONDARY_INVERTERS}")
    print(f"Context inverters: {CONTEXT_INVERTERS}")
    print()

    session = get_session()

    inv_map, meter_key, poa_key, all_devices, site_data = resolve_hardware(session)

    # Pull 1: Alarms (HIGHEST PRIORITY)
    pull_alarms(session)

    # Pull 2: Time-series
    pull_timeseries(session, inv_map, poa_key)

    # Pull 3: Meter
    pull_meter(session, meter_key)

    # Pull 4: Settings
    pull_inverter_settings(session, inv_map, site_data)

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print("  alarms_whitetail.csv   — DONE (full Feb-May + morning flags)")
    print("  morning_timeseries.csv — BLOCKED (chart endpoint)")
    print("  meter_morning.csv      — BLOCKED (chart endpoint)")
    print("  inverter_settings.csv  — DONE (limited to API-exposed settings)")
    print()
    print("  To unlock time-series pulls, capture a chart POST cURL from")
    print("  PowerTrack DevTools and share it. See Pull 2 output for steps.")


if __name__ == "__main__":
    main()
