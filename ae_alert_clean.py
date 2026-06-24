#!/usr/bin/env python3
"""
ae_alert_clean.py — Transform ae_alerts.xlsx into NewLog-ready rows.

Applies the full mapping-rule set from NEWLOG_MAPPING_RULES.md:
  - Drop unwanted alert codes and error messages
  - Normalize Equip / SubPart / Issue4Work / Bucket
  - Parse Unit ID + QTY from hardware names and descriptions
  - Deduplicate (Site + Equip + Alert Type + Error Message)
  - Aggregate storm events (2-hour window, 1-day for trackers)
  - Split into Resolved / Unresolved / Ignored sheets

Usage:
    python ae_alert_clean.py                      # reads ae_alerts.xlsx
    python ae_alert_clean.py --input my_alerts.xlsx --output cleaned.xlsx
"""

import argparse
import re
import math
from datetime import timedelta
from pathlib import Path

import pandas as pd
import numpy as np

HERE = Path(__file__).resolve().parent

# ── Site → Project name mapping ──────────────────────────────────────
SITE_PROJECT = {
    "Bulloch 1A": "Bulloch1", "Bulloch 1B": "Bulloch2",
    "Butler Maple": "Maple", "C & B Graham Energy": "Graham",
    "Elk Solar": "Elk", "Gallia Academy": "GSR-Gallia",
    "Gray Fox Solar": "Gray Fox", "Green Elementary": "GSR-Green",
    "Green Solar": "Green", "Harding Solar": "Harding",
    "Longleaf Pine Solar, LLC": "Longleaf", "Marble Solar": "Marble",
    "McLean": "Mclean", "Monroe Landfill": "Monroe",
    "RRH 1 & 2": "RRH", "Rio Grande Elementary": "GSR-Rio",
    "Sheridan Solar": "Sheridan", "Sunflower Solar": "Sunflower",
    "Washington Solar": "Washington", "Whitehall Solar": "Whitehall",
    "Williams Solar, LLC": "Williams",
    "WCPS - Kate Collins Middle School": "Waynes-KCMS",
    "WCPS - Westwood Hills Elementary School": "Waynes-WHES",
    "WCPS - Waynesboro High School": "Waynes-WHS",
    "WCPS - William Perry Elementary School": "Waynes-WPHS",
    "Wallace Solar": "Wallace", "Auburn Solar": "Auburn",
}

# ── Site → Contractor mapping ────────────────────────────────────────
SITE_CONTRACTOR = {}
SITE_CONTRACTOR["Longleaf Pine Solar, LLC"] = "NRCO"
SITE_CONTRACTOR["Williams Solar, LLC"] = "NRCO"
for _sites, _c in [
    ("Whitetail,Sunflower Solar,Shorthorn,Whitehall Solar,Warbler,McLean,"
     "Elk Solar,Gray Fox Solar,Harding Solar,Washington Solar,"
     "Bulloch 1A,Bulloch 1B,Richmond,Upson", "NRCO"),
    ("Butler Maple,Sheridan Solar,Auburn Solar,Green Solar,Wallace Solar,"
     "Marble Solar", "Konisto"),
    ("C & B Graham Energy", "Solential"),
    ("Monroe Landfill", "All Bright"),
    ("Eagle,Gallia Academy,Green Elementary,Rio Grande Elementary", "TMI"),
    ("WCPS - Kate Collins Middle School,WCPS - Waynesboro High School,"
     "WCPS - William Perry Elementary School", "GOT Elect"),
    ("RIT,RRH 1 & 2", "Miller"),
]:
    for s in _sites.split(","):
        SITE_CONTRACTOR[s.strip()] = _c

# ── Dropped alert codes ─────────────────────────────────────────────
DROP_CODES = {614, 401, 358}

# ── Dropped error-message patterns ──────────────────────────────────
DROP_MSG_PATTERNS = [
    re.compile(r"Wiring problem between the device and the gateway", re.I),
    re.compile(r"Wiring problem between the gateway and the internet connection", re.I),
    re.compile(r"Checking production against available", re.I),
    re.compile(r"Low mid-day irradiance", re.I),
    re.compile(r"^kWh\s*=\s*", re.I),
    re.compile(r"Unable to process alert", re.I),
    re.compile(r"Upload queue exceeded", re.I),
]

# code 974 SOC alerts are KEPT (exception to the SOC drop)
DROP_MSG_SOC = re.compile(r"State of charge is under the critical threshold", re.I)


def should_drop(code, desc, hw):
    if code in DROP_CODES:
        return True
    desc_str = str(desc) if pd.notna(desc) else ""
    if DROP_MSG_SOC.search(desc_str) and code != 974:
        return True
    for pat in DROP_MSG_PATTERNS:
        if pat.search(desc_str):
            return True
    return False


# ── Equip normalization ─────────────────────────────────────────────
CODE_EQUIP = {534: "Xfmr", 2899: "Inverter", 1037: "Inverter",
              630: "Inverter", 2750: "Inverter", 438: "String",
              499: "Tracker", 863: "Tracker", 974: "Tracker",
              593: "Tracker", 3635: "Tracker", 3745: "Tracker"}

def normalize_equip(code, hw, desc):
    hw_s = str(hw) if pd.notna(hw) else ""
    desc_s = str(desc) if pd.notna(desc) else ""
    hw_low = hw_s.lower()
    desc_low = desc_s.lower()

    # Hardware-type overrides (highest priority — DAS / Site / Switchgear)
    if re.search(r"SEL[\s-]*751", hw_s, re.I) or "recloser" in hw_low:
        return "Site"
    if "ac breaker" in hw_low or "ac breaker" in desc_low:
        return "Switchgear"
    if code == 604:
        return "Site"
    if any(k in hw_low for k in ("powerlogger", "power logger")):
        return "DAS"
    if "weather" in hw_low and "station" in hw_low:
        return "DAS"
    if "production" in hw_low and "meter" in hw_low:
        return "DAS"
    if "datalogger" in hw_low:
        return "DAS"
    if "powermanager" in hw_low:
        return "DAS"
    if re.search(r"\bups\b|\bups\d", hw_low, re.I):
        return "DAS"

    # Alert-code overrides
    if code in CODE_EQUIP:
        equip = CODE_EQUIP[code]
        # but "inverter" in hw overrides 438->String
        if code == 438 and re.search(r"inverter|\binv\b", hw_low, re.I):
            return "Inverter"
        return equip

    # Hardware-content rules
    if re.search(r"inverter|\binv\b", hw_low, re.I):
        return "Inverter"
    if "modem" in hw_low:
        return "Mods"
    if "tracker" in hw_low:
        return "Tracker"
    if hw_s.strip() == "RELAY":
        return "Switchgear"

    # Comment-based
    if re.search(r"\bmodules?\b", desc_low):
        return "Mods"

    # Title-case all-caps leftovers
    if hw_s.isupper() and hw_s.strip():
        return hw_s.title()
    return hw_s if hw_s else ""


# ── SubPart from alert code ──────────────────────────────────────────
CODE_SUBPART = {
    250: "TCU", 499: "TCU", 863: "TCU", 974: "TCU", 593: "TCU",
    3635: "Motor", 3745: "Motor",
}

# ── Issue4Work from alert code ───────────────────────────────────────
CODE_ISSUE = {
    250: "Communication", 499: "Communication", 863: "Communication",
    974: "Communication", 593: "Communication",
    3635: "Stuck", 3745: "Stuck",
}


def determine_subpart(code, hw, desc, equip):
    hw_s = str(hw) if pd.notna(hw) else ""
    desc_s = str(desc) if pd.notna(desc) else ""
    hw_low = hw_s.lower()
    desc_low = desc_s.lower()

    # Hardware-type overrides (top priority)
    if any(k in hw_low for k in ("powerlogger", "power logger")):
        return "Data Logger"
    if "weather" in hw_low and "station" in hw_low:
        return "Weather station"
    if "production" in hw_low and "meter" in hw_low:
        return "Production Meter"
    if "datalogger" in hw_low:
        return "Data Logger"
    if re.search(r"\bups\b|\bups\d", hw_low, re.I):
        return ""  # blank per scrapped DAS battery rule
    if re.search(r"SEL[\s-]*751", hw_s, re.I) or "recloser" in hw_low:
        return "Recloser"
    if code == 604:
        return "Recloser"
    if "ac breaker" in hw_low or "ac breaker" in desc_low:
        return "AC Breaker"

    # Error-message / comment overrides
    if re.search(r"\bfan\b", desc_low):
        return "Fan"
    if "fuse" in desc_low and equip == "Xfmr":
        return "Fuse"
    if "insulation" in desc_low and equip == "Inverter":
        return "DC Wire"
    if re.search(r"\bac\s*switch\b", desc_low, re.I) and equip == "Inverter":
        return ""  # AC Switch not valid
    if "ac disconnect" in desc_low:
        return "AC Disconnect"
    if "igbt" in desc_low:
        return "IGBT"
    if re.search(r"sel relay|relay open|relay is open", desc_low):
        return "Relay"
    if any(k in desc_low for k in ("theft", "cut wire", "grounding wire", "string/ground")):
        return "DC Wire"
    if "fuse holder" in desc_low:
        return "Fuse Holder"
    if re.search(r"\bmc4\b", desc_low, re.I):
        return "MC4"
    if "conduit" in desc_low and "seal" in desc_low:
        return "Conduits Seal"
    if re.search(r"\bfuse\b", desc_low):
        return "Fuse"

    # Alert-code default
    if code in CODE_SUBPART:
        return CODE_SUBPART[code]
    return ""


def determine_issue(code, hw, desc, equip, subpart):
    hw_s = str(hw) if pd.notna(hw) else ""
    desc_s = str(desc) if pd.notna(desc) else ""
    hw_low = hw_s.lower()
    desc_low = desc_s.lower()

    # Hardware-type overrides
    if any(k in hw_low for k in ("powerlogger", "power logger")):
        return "Troubleshoot"
    if "weather" in hw_low and "station" in hw_low:
        return ""  # blank unless repair keyword
    if "production" in hw_low and "meter" in hw_low:
        return "Troubleshoot"
    if re.search(r"\bups\b|\bups\d", hw_low, re.I):
        return ""  # blank per DAS battery rule
    if re.search(r"SEL[\s-]*751", hw_s, re.I) or "recloser" in hw_low:
        return "Reclosed"
    if code == 604:
        return "Reclosed"

    # Code 974 special cases
    if code == 974:
        if DROP_MSG_SOC.search(desc_s) or "state of charge" in desc_low or "soc" in desc_low:
            return "Battery Low"
        if "emergency stop" in desc_low:
            return "Stuck"
        return "Communication"

    # Comment-based rules (later rule wins, so order matters — reverse priority)
    issue = None

    # Default from alert code
    if code in CODE_ISSUE:
        issue = CODE_ISSUE[code]

    # Keyword rules (later wins)
    if "shutdown" in desc_low or "offline" in desc_low:
        issue = "Offline"
    if "derate" in desc_low or "derated" in desc_low:
        if any(k in desc_low for k in ("curtail", "suspended production")):
            issue = "Curtailment"
        else:
            issue = "Underperformance"
    if "thermal event" in desc_low:
        issue = "Thermal Event"
    if "vacuum" in desc_low:
        issue = "Vacuum Vault Pressure Repair"
    if re.search(r"\brma\b", desc_low, re.I) or re.search(r"\brma\b", hw_low, re.I):
        issue = "RMA"
    if "reclosed" in desc_low:
        issue = "Reclosed"
    if re.search(r"utility trip|utility tripped|tripped offline by utility|outage", desc_low):
        issue = "Utility Trip"
    if re.search(r"islanding.*grid power outage", desc_low, re.I):
        issue = "Tripped Offline"

    # More specific keyword rules
    if re.search(r"\breset\b", desc_low):
        issue = "Reset"
    if "ground fault" in desc_low:
        issue = "Ground Fault"
    if "arc fault" in desc_low:
        issue = "Arc Fault"
    if desc_s.strip() == "Stop":
        issue = "Fault"
    if "faults detected" in desc_low or "overcurrent" in desc_low or "hardware self test" in desc_low:
        issue = "Fault"
    if "open phase" in desc_low:
        issue = "Fault"
    if "device abnormality" in desc_low:
        issue = "Device Abnormality"
    if re.search(r"grid voltage unbalance|voltage imbalance", desc_low):
        issue = "Grid Voltage Imbalance"
    if re.search(r"overvoltage|grid phase voltage high", desc_low):
        issue = "Grid Phase Voltage High"
    if re.search(r"high voltage.*hv|low voltage.*lv", desc_low, re.I):
        if issue != "Fault":  # don't override explicit Fault
            issue = "Repair"
    if re.search(r"outside acceptable range|trackerpos", desc_low, re.I):
        issue = "Stuck"
    if re.search(r"\bblocked\b|tracking disabled", desc_low, re.I):
        issue = "Stuck"
    if re.search(r"undervoltage|under voltage", desc_low):
        issue = "Offline"
    if re.search(r"theft|stolen", desc_low):
        issue = "Offline"
    if "low insolation" in desc_low:
        issue = "Low Insolation Fault"
    if re.search(r"\bhotspot\b", desc_low):
        issue = "Hotspots"
    if "firmware" in desc_low:
        issue = "Firmware Update"
    if "gateway heartbeat" in desc_low or code == 253:
        issue = "Gateway Heartbeat Alert"
    if re.search(r"curtail|suspended production", desc_low):
        issue = "Curtailment"
    if re.search(r"\bstow\b", desc_low):
        issue = "Stow"
    if "hurricane" in desc_low:
        issue = "Hurricane Damage"

    # SEL relay / Switchgear + Relay → Relay Settings, blank Issue
    if equip == "Switchgear" and subpart == "Relay":
        return ""

    # DAS Weather station → blank Issue
    if equip == "DAS" and subpart == "Weather station":
        for kw in ("repair", "replace", "rma", "broken", "failed"):
            if kw in desc_low:
                return issue or "Repair"
        return ""

    if issue:
        return issue
    return "Repair"


def determine_bucket(equip, issue):
    if equip == "Site" or issue in ("Utility Trip", "Reclosed", "Tripped Offline"):
        return "Outage"
    if issue in ("Replaced", "RMA", "Damaged", "Thermal Event", "Replacement",
                 "Replaced IGBT", "Offline Post RMA"):
        return "Equip Replace"
    if equip == "Inverter" and issue == "Thermal Event":
        return "Equip Replace"
    return "Repair"


def determine_create_loss(equip, subpart, desc):
    desc_low = str(desc).lower() if pd.notna(desc) else ""
    if equip == "DAS":
        return 0
    # Production Meter power-phase or current-mismatch only → 0
    if subpart == "Production Meter":
        if re.search(r"power phase error|current mismatch", desc_low) and \
           not re.search(r"(?!power phase|current mismatch)\w+\s+fault", desc_low):
            return 0
    return 1


# ── Unit ID + QTY parsing ────────────────────────────────────────────
def parse_unit_id(hw, desc):
    hw_s = str(hw) if pd.notna(hw) else ""
    desc_s = str(desc) if pd.notna(desc) else ""

    units = []

    # 1. Error message multi-unit: "Slave Alarms S NN" / "Individual Tracker Alarm NN"
    slave_nums = re.findall(r"(?:Slave Alarms S|Individual Tracker Alarm)\s*(\d+)", desc_s, re.I)
    if slave_nums:
        nums = sorted(set(int(n) for n in slave_nums))
        return range_compress(nums), len(nums)

    # "TCU Fault NN" patterns
    tcu_nums = re.findall(r"TCU Fault\s*(\d+)", desc_s, re.I)
    if tcu_nums:
        nums = sorted(set(int(n) for n in tcu_nums))
        return range_compress(nums), len(nums)

    # "Alarm N1-N2" range in error
    alarm_range = re.search(r"Alarm\s+(\d+)\s*-\s*(\d+)", desc_s, re.I)
    if alarm_range:
        lo, hi = int(alarm_range.group(1)), int(alarm_range.group(2))
        return f"{lo} - {hi}", hi - lo + 1

    # 2. Hardware device name patterns
    # "INVERTER 14", "INVERTER B18", "INVERTER 1"
    m = re.search(r"(?:INVERTER|Inverter)\s+([A-Z]?\d+(?:\.\d+)?)", hw_s)
    if m:
        return m.group(1), 1

    # "CPS SCH125kTL Inv - 5"
    m = re.search(r"Inv\s*-\s*(\d+(?:\.\d+)?)", hw_s)
    if m:
        return m.group(1), 1

    # "Inverter - 01.07"
    m = re.search(r"Inverter\s*-\s*(\d+\.\d+)", hw_s)
    if m:
        return m.group(1), 1

    # "Sungrow SG125 Inverter B19 at 100%"
    m = re.search(r"Inverter\s+([A-Z]?\d+)", hw_s)
    if m:
        return m.group(1), 1

    # Parenthetical tag: "TRACKER CONTROL (ST2)" → ST2
    m = re.search(r"\(([A-Z]+\d+)\)", hw_s)
    if m:
        return m.group(1), 1

    # "Weather Station 1"
    m = re.search(r"Weather Station\s+(\d+)", hw_s)
    if m:
        return m.group(1), 1

    # "DIGITAL I/O - XFMR ALARMS (IO2)" → IO2
    m = re.search(r"\((IO\d+)\)", hw_s)
    if m:
        return m.group(1), 1

    # Range in hw: "INVERTER 2-49 (~23 units)"
    m = re.search(r"(?:INVERTER|Inverter)\s+(\d+)\s*-\s*(\d+)", hw_s)
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
        return f"{lo} - {hi}", hi - lo + 1

    # 3. Fallback to description
    m = re.search(r"Inverter\s+(\d+)", desc_s, re.I)
    if m:
        return m.group(1), 1
    m = re.search(r"Row\s+(\d+)", desc_s, re.I)
    if m:
        return m.group(1), 1

    return "", 1


def range_compress(nums):
    if not nums:
        return ""
    nums = sorted(set(nums))
    ranges = []
    start = nums[0]
    end = nums[0]
    for n in nums[1:]:
        if n == end + 1:
            end = n
        else:
            ranges.append(f"{start}-{end}" if start != end else str(start))
            start = end = n
    ranges.append(f"{start}-{end}" if start != end else str(start))
    return ", ".join(ranges)


def range_compress_str(unit_ids_str):
    """Re-compress a comma-separated unit ID string."""
    parts = re.split(r"[,\s]+", str(unit_ids_str))
    nums = []
    non_nums = []
    for p in parts:
        p = p.strip().strip("-")
        if not p:
            continue
        m = re.match(r"^(\d+)$", p)
        if m:
            nums.append(int(m.group(1)))
        else:
            # Could be a range "1-5"
            rm = re.match(r"^(\d+)\s*-\s*(\d+)$", p)
            if rm:
                nums.extend(range(int(rm.group(1)), int(rm.group(2)) + 1))
            else:
                non_nums.append(p)
    result_parts = []
    if nums:
        result_parts.append(range_compress(sorted(set(nums))))
    result_parts.extend(non_nums)
    return ", ".join(result_parts)


# ── Comment cleaning ─────────────────────────────────────────────────
BOILERPLATE = re.compile(
    r"^This error may be the result of one of the following:\s*1\.\s*", re.I)

import platform
_WIN = platform.system() == "Windows"

def _fmt_date(ts):
    if _WIN:
        return ts.strftime("%#m/%#d/%Y")
    return ts.strftime("%-m/%-d/%Y")

def _fmt_time(ts):
    return ts.strftime("%I:%M %p").lstrip("0").lower()


def clean_comment(desc, equip, subpart, issue, start_time):
    s = str(desc) if pd.notna(desc) else ""
    s = s.replace("\t", " ").strip()
    s = BOILERPLATE.sub("", s)

    # "Stop" → "Inverter Faults Detected"
    if s.strip() == "Stop":
        return "Inverter Faults Detected"

    # Production Meter: drop raw A/B/C values
    if subpart == "Production Meter":
        s = re.sub(r"\s*A\s*=\s*[\d.,+-]+\s*(?:kW|Amps?),?\s*", " ", s)
        s = re.sub(r"\s*B\s*=\s*[\d.,+-]+\s*(?:kW|Amps?),?\s*", " ", s)
        s = re.sub(r"\s*C\s*=\s*[\d.,+-]+\s*(?:kW|Amps?)\s*", "", s)
        s = s.strip().rstrip(",").strip()

    # Night-time power phase error
    if subpart == "Production Meter" and "power phase error" in s.lower():
        if start_time and hasattr(start_time, "hour"):
            h = start_time.hour
            if h >= 19 or h < 5:
                return ("Power phase error/Alerts are too sensitive and happening "
                        "during the night. Low irradiance in the area is also "
                        "effecting these alerts.")

    # Drop current-mismatch raw values
    if "current mismatch" in s.lower():
        s = re.sub(r"\s*A\s*=\s*[\d.,]+\s*Amps?,?\s*", " ", s)
        s = re.sub(r"\s*B\s*=\s*[\d.,]+\s*Amps?,?\s*", " ", s)
        s = re.sub(r"\s*C\s*=\s*[\d.,]+\s*Amps?\s*", "", s)
        s = s.strip().rstrip(",").strip()
        if not s or s.lower() == "current mismatch":
            s = "Current mismatch"

    return s.strip()


# ── Main transform ───────────────────────────────────────────────────
def transform(df):
    rows = []
    ignored = []

    for _, r in df.iterrows():
        code = int(r["event_type_code"]) if pd.notna(r["event_type_code"]) else 0
        hw = r["hardware_name"]
        desc = r["description"]

        # Filter
        if should_drop(code, desc, hw):
            continue

        site = r["site_name"]
        project = SITE_PROJECT.get(site, site)
        contractor = SITE_CONTRACTOR.get(site, "")

        equip = normalize_equip(code, hw, desc)
        subpart = determine_subpart(code, hw, desc, equip)
        issue = determine_issue(code, hw, desc, equip, subpart)

        # Switchgear + Relay → Relay Settings (override subpart)
        if equip == "Switchgear" and subpart == "Relay" and code != 604:
            subpart = "Relay Settings"
            issue = ""

        # Invariant: "Weather station" SubPart only when Equip = DAS
        if subpart == "Weather station" and equip != "DAS":
            subpart = ""

        bucket = determine_bucket(equip, issue)

        # Inverter + Thermal Event always Equip Replace
        if equip == "Inverter" and issue == "Thermal Event":
            bucket = "Equip Replace"

        unit_id, qty = parse_unit_id(hw, desc)
        start = r["alert_start"]
        create_loss = determine_create_loss(equip, subpart, desc)
        comment = clean_comment(desc, equip, subpart, issue, start)

        # Work = SubPart - Issue4Work
        work_parts = [p for p in [subpart, issue] if p]
        work = " - ".join(work_parts)

        # Start/End date+time split
        start_date = _fmt_date(start) if pd.notna(start) else ""
        start_time_str = _fmt_time(start) if pd.notna(start) else ""

        end_date = ""
        end_time_str = ""
        resolved = r["is_resolved"]
        if resolved and pd.notna(r["resolved_time"]):
            rt = r["resolved_time"]
            end_date = _fmt_date(rt)
            end_time_str = _fmt_time(rt)

        row = {
            "alert_id": r["alert_id"],
            "event_type_code": code,
            "event_type_name": r["event_type_name"],
            "Contractor": contractor,
            "Project": project,
            "Equip": equip,
            "SubPart": subpart,
            "Issue4Work": issue,
            "Work": work,
            "CreateLoss": create_loss,
            "Comments": comment,
            "Unit ID": str(unit_id),
            "QTY": qty,
            "Bucket": bucket,
            "Start Date": start_date,
            "Start Time": start_time_str,
            "End Date": end_date,
            "End Time": end_time_str,
            "Resolved": resolved,
            "Repair (P)": "",
            "_site_raw": site,
            "_start_dt": start,
            "_resolved_dt": r["resolved_time"] if resolved else pd.NaT,
            "_desc_raw": desc,
        }
        rows.append(row)

    return pd.DataFrame(rows)


# ── Deduplication ────────────────────────────────────────────────────
def normalize_desc_for_dedup(desc):
    s = str(desc) if pd.notna(desc) else ""
    # Current mismatch: ignore amp values
    s = re.sub(r"[\d.,]+\s*Amps?", "", s)
    s = re.sub(r"[\d.,]+\s*kW", "", s)
    return s.strip().lower()


def dedup(df):
    df = df.copy()
    df["_dedup_key"] = (
        df["_site_raw"].astype(str) + "|" +
        df["Equip"].astype(str) + "|" +
        df["event_type_name"].astype(str) + "|" +
        df["_desc_raw"].apply(normalize_desc_for_dedup)
    )
    df["_date"] = df["_start_dt"].dt.date

    # Current mismatch: one per site per day
    cm_mask = df["_desc_raw"].str.contains("Current mismatch", case=False, na=False)
    cm = df[cm_mask].copy()
    non_cm = df[~cm_mask].copy()

    if not cm.empty:
        cm["_cm_key"] = cm["_site_raw"].astype(str) + "|" + cm["_date"].astype(str)
        cm = cm.sort_values("Resolved", ascending=False).drop_duplicates("_cm_key", keep="first")
        cm = cm.drop(columns=["_cm_key"])

    # General dedup: keep first resolved, else first unresolved
    if not non_cm.empty:
        non_cm = non_cm.sort_values("Resolved", ascending=False)
        non_cm = non_cm.drop_duplicates("_dedup_key", keep="first")

    result = pd.concat([non_cm, cm], ignore_index=True)
    result = result.sort_values("_start_dt").reset_index(drop=True)
    return result


# ── Storm / event aggregation ────────────────────────────────────────
STORM_CATEGORIES = {
    "Islanding": lambda r: "islanding" in str(r.get("_desc_raw", "")).lower(),
    "Arc Fault": lambda r: r.get("Issue4Work") == "Arc Fault",
    "Fault": lambda r: r.get("Issue4Work") == "Fault",
    "Communication": lambda r: r.get("Issue4Work") == "Communication" and r.get("Equip") == "Tracker",
    "DAS Meter": lambda r: r.get("Equip") == "DAS" and r.get("SubPart") == "Production Meter",
    "Xfmr Temp": lambda r: r.get("Equip") == "Xfmr" and "temp fault" in str(r.get("_desc_raw", "")).lower(),
    "Offline": lambda r: r.get("Issue4Work") == "Offline",
    "Repair": lambda r: r.get("Issue4Work") == "Repair",
    "HV/LV": lambda r: bool(re.search(r"high voltage.*hv|low voltage.*lv",
                                        str(r.get("_desc_raw", "")).lower())),
}

TRACKER_ISSUES = {"Communication", "Stuck", "Battery Low", "Stow"}


def aggregate_storms(df):
    aggregated = []
    used_indices = set()

    for cat_name, cat_fn in STORM_CATEGORIES.items():
        cat_mask = df.apply(cat_fn, axis=1)
        cat_df = df[cat_mask & ~df.index.isin(used_indices)]
        if cat_df.empty:
            continue

        for (site, date), group in cat_df.groupby(["_site_raw", "_date"]):
            is_tracker = group["Equip"].iloc[0] == "Tracker" or group["Issue4Work"].iloc[0] in TRACKER_ISSUES

            if cat_name in ("Offline", "Repair"):
                # Group by same comment AND same Issue4Work
                for (comment, iss), sub in group.groupby(["Comments", "Issue4Work"]):
                    _do_aggregate(sub, site, date, is_tracker, aggregated, used_indices)
            elif cat_name == "HV/LV":
                # Don't merge HV/LV with Fault — leave separate
                _do_aggregate(group, site, date, is_tracker, aggregated, used_indices)
            else:
                _do_aggregate(group, site, date, is_tracker, aggregated, used_indices)

    # Add non-aggregated rows
    remaining = df[~df.index.isin(used_indices)]
    aggregated.extend(remaining.to_dict("records"))

    result = pd.DataFrame(aggregated)
    result = result.sort_values("_start_dt").reset_index(drop=True)
    return result


def _to_dict(item):
    if isinstance(item, dict):
        return item
    return item.to_dict()


def _do_aggregate(group, site, date, is_tracker, aggregated, used_indices):
    if len(group) <= 1:
        aggregated.extend(group.to_dict("records"))
        used_indices.update(group.index)
        return

    group = group.sort_values("_start_dt")
    window_hours = 24 if is_tracker else 2

    rows = [group.iloc[i] for i in range(len(group))]
    clusters = []
    current_cluster = [rows[0]]
    for row in rows[1:]:
        prev = current_cluster[-1]
        diff = (row["_start_dt"] - prev["_start_dt"]).total_seconds() / 3600
        if diff <= window_hours:
            current_cluster.append(row)
        else:
            clusters.append(current_cluster)
            current_cluster = [row]
    clusters.append(current_cluster)

    for cluster in clusters:
        dicts = [_to_dict(c) for c in cluster]
        for c in cluster:
            if hasattr(c, "name"):
                used_indices.add(c.name)

        if len(dicts) == 1:
            aggregated.append(dicts[0])
            continue

        merged = dict(dicts[0])
        merged["_start_dt"] = min(d["_start_dt"] for d in dicts)

        resolved_times = [d["_resolved_dt"] for d in dicts if pd.notna(d["_resolved_dt"])]
        if resolved_times:
            avg_ts = pd.Timestamp(sum(t.value for t in resolved_times) / len(resolved_times))
            merged["_resolved_dt"] = avg_ts
            merged["End Date"] = _fmt_date(avg_ts)
            merged["End Time"] = _fmt_time(avg_ts)
            merged["Resolved"] = True
        else:
            merged["_resolved_dt"] = pd.NaT
            merged["End Date"] = ""
            merged["End Time"] = ""
            merged["Resolved"] = False

        st = merged["_start_dt"]
        if pd.notna(st):
            merged["Start Date"] = _fmt_date(st)
            merged["Start Time"] = _fmt_time(st)

        all_unit_ids = [str(d["Unit ID"]) for d in dicts if d["Unit ID"]]
        total_qty = sum(int(d["QTY"]) if d["QTY"] else 1 for d in dicts)
        if all_unit_ids:
            merged["Unit ID"] = range_compress_str(", ".join(all_unit_ids))
        merged["QTY"] = total_qty

        seen_comments = set()
        comments = []
        for d in dicts:
            cm = d["Comments"]
            if cm and cm not in seen_comments:
                comments.append(cm)
                seen_comments.add(cm)
        merged["Comments"] = " | ".join(comments) if comments else ""

        if "islanding" in str(merged.get("_desc_raw", "")).lower():
            merged["Equip"] = "Inverter" if merged["QTY"] == 1 else "Site"
            merged["Issue4Work"] = "Tripped Offline"
            merged["Bucket"] = "Outage"

        aggregated.append(merged)


# ── Fault + HV merge (same unit only) ────────────────────────────────
def merge_fault_hv(df):
    merged_indices = set()
    result = []

    for (site, date), group in df.groupby(["_site_raw", "_date"]):
        fault_rows = group[group["Issue4Work"] == "Fault"]
        hv_rows = group[group["Comments"].str.contains(r"[Hh]igh voltage.*HV|[Ll]ow voltage.*LV",
                                                        na=False, regex=True)]

        for fi, frow in fault_rows.iterrows():
            for hi, hrow in hv_rows.iterrows():
                if hi in merged_indices or fi in merged_indices:
                    continue
                if str(frow["Unit ID"]) == str(hrow["Unit ID"]) and frow["Unit ID"]:
                    merged = frow.to_dict()
                    hv_comment = hrow["Comments"]
                    hv_start = hrow["Start Time"]
                    merged["Comments"] = f"{frow['Comments']} | {hv_comment} [{hv_start}]"
                    merged["Issue4Work"] = "Fault"
                    merged_indices.add(hi)
                    result.append(merged)
                    merged_indices.add(fi)
                    break

    # Add remaining (not merged)
    remaining = df[~df.index.isin(merged_indices)]
    result_df = pd.concat([pd.DataFrame(result), remaining], ignore_index=True)
    return result_df.sort_values("_start_dt").reset_index(drop=True)


# ── Islanding duplicate detection (rule 8) ───────────────────────────
def drop_islanding_dupes(df):
    ignored = []
    keep_mask = pd.Series(True, index=df.index)

    for (site, date), group in df.groupby(["_site_raw", "_date"]):
        trip_exists = group["Issue4Work"].isin(
            ["Utility Trip", "Reclosed", "Reset"]
        ).any() or (group["event_type_code"] == 604).any()

        if not trip_exists:
            continue

        for idx, row in group.iterrows():
            if row["Equip"] == "Site" and row["Issue4Work"] == "Tripped Offline":
                desc_low = str(row.get("_desc_raw", "")).lower()
                if "islanding" in desc_low and "inverter" in desc_low:
                    keep_mask[idx] = False
                    row_dict = row.to_dict()
                    row_dict["_ignore_reason"] = "Duplicate of site/utility trip same day"
                    ignored.append(row_dict)

    kept = df[keep_mask].reset_index(drop=True)
    ignored_df = pd.DataFrame(ignored) if ignored else pd.DataFrame()
    return kept, ignored_df


# ── Output columns ───────────────────────────────────────────────────
OUTPUT_COLS = [
    "Contractor", "Project", "Equip", "SubPart", "Issue4Work", "Work",
    "CreateLoss", "Comments", "Repair (P)", "Unit ID", "QTY",
    "Bucket", "Start Date", "Start Time", "End Date", "End Time",
    "alert_id", "event_type_code", "event_type_name",
]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", default="ae_alerts.xlsx")
    ap.add_argument("--output", default="ae_alerts_clean.xlsx")
    args = ap.parse_args()

    print(f"Reading {args.input}...")
    df = pd.read_excel(args.input)
    print(f"  {len(df)} raw rows")

    # Transform
    print("Applying mapping rules...")
    cleaned = transform(df)
    pre_dedup = len(cleaned)
    print(f"  {pre_dedup} rows after filtering (dropped {len(df) - pre_dedup})")

    # Dedup
    print("Deduplicating...")
    cleaned = dedup(cleaned)
    print(f"  {len(cleaned)} rows after dedup (removed {pre_dedup - len(cleaned)})")

    # Aggregate storms
    print("Aggregating storms...")
    pre_agg = len(cleaned)
    cleaned = aggregate_storms(cleaned)
    print(f"  {len(cleaned)} rows after aggregation (collapsed {pre_agg - len(cleaned)})")

    # Fault + HV merge
    print("Merging Fault + HV rows...")
    pre_merge = len(cleaned)
    cleaned = merge_fault_hv(cleaned)
    print(f"  {len(cleaned)} rows after Fault+HV merge")

    # Islanding duplicate detection
    print("Checking islanding duplicates...")
    cleaned, ignored_df = drop_islanding_dupes(cleaned)
    if not ignored_df.empty:
        print(f"  Moved {len(ignored_df)} islanding dupes to Ignored")

    # Split resolved / unresolved
    resolved = cleaned[cleaned["Resolved"] == True].copy()
    unresolved = cleaned[cleaned["Resolved"] == False].copy()

    # Fill NaN with empty strings in text columns
    text_cols = ["SubPart", "Issue4Work", "Work", "Unit ID", "End Date", "End Time",
                 "Repair (P)", "Comments", "Contractor", "Project", "Equip", "Bucket"]
    for col in text_cols:
        if col in resolved.columns:
            resolved[col] = resolved[col].fillna("")
        if col in unresolved.columns:
            unresolved[col] = unresolved[col].fillna("")

    # Select output columns
    out_cols = [c for c in OUTPUT_COLS if c in resolved.columns]
    resolved_out = resolved[out_cols]
    unresolved_out = unresolved[out_cols]

    # Write
    print(f"\nWriting {args.output}...")
    with pd.ExcelWriter(args.output, engine="openpyxl") as writer:
        resolved_out.to_excel(writer, sheet_name="Resolved Alerts", index=False)
        unresolved_out.to_excel(writer, sheet_name="Unresolved Alerts", index=False)
        if not ignored_df.empty:
            ign_cols = [c for c in OUTPUT_COLS if c in ignored_df.columns]
            if "_ignore_reason" in ignored_df.columns:
                ign_cols = ign_cols + ["_ignore_reason"]
            ignored_df[ign_cols].to_excel(writer, sheet_name="Ignored Alerts", index=False)

    print(f"\nDone!")
    print(f"  Resolved:   {len(resolved_out)} rows")
    print(f"  Unresolved: {len(unresolved_out)} rows")
    if not ignored_df.empty:
        print(f"  Ignored:    {len(ignored_df)} rows")
    print(f"  Saved -> {args.output}")


if __name__ == "__main__":
    main()
