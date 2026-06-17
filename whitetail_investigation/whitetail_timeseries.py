#!/usr/bin/env python3
"""
Whitetail (S59656) morning time-series extraction.

Uses the chart endpoint (POST /api/view/chart) to pull 15-minute interval
data for specified inverters, POA pyranometer, and production meter across
all target late-start mornings.

Outputs:
  morning_timeseries.csv  — per-inverter DC V, DC I, AC kW, fault code + POA
  meter_morning.csv       — production meter kW, kWh, voltages
"""

import csv
import json
import sys
import time
from datetime import datetime, timedelta

from ae_auth import get_session

API_BASE = "https://apps.alsoenergy.com/api"
SITE_KEY = "S59656"

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

INV_MAP = {
    7: "H312394", 35: "H312422", 51: "H312439", 78: "H312466",
    2: "H312389", 40: "H312427",
}
POA_KEY = "H312487"
METER_KEY = "H312384"

MEASUREMENT_CATS = [
    {"value": 1, "enabled": True, "checked": True, "modelOptions": None},     # AC Power (kW)
    {"value": 2, "enabled": True, "checked": True, "modelOptions": None},     # Energy (kWh)
    {"value": 4, "enabled": True, "checked": True, "modelOptions": None},     # Irradiance/Weather
    {"value": 8, "enabled": True, "checked": True, "modelOptions": None},     # Irradiance (POA/GHI)
    {"value": 16, "enabled": True, "checked": True, "modelOptions": None},    # DC Current
    {"value": 32, "enabled": True, "checked": True, "modelOptions": None},    # DC Voltage
    {"value": 64, "enabled": True, "checked": True, "modelOptions": None},    # AC Current
    {"value": 128, "enabled": True, "checked": True, "modelOptions": None},   # AC Voltage
    {"value": 256, "enabled": True, "checked": True, "modelOptions": None},   # Power Factor
    {"value": 512, "enabled": False, "checked": False, "modelOptions": None},
    {"value": 1024, "enabled": True, "checked": True, "modelOptions": None},  # Fault/Status
    {"value": 2048, "enabled": False, "checked": False, "modelOptions": None},
    {"value": 4096, "enabled": True, "checked": False, "modelOptions": None},
    {"value": 8192, "enabled": False, "checked": False, "modelOptions": None},
]

INLINE_OPTIONS = {
    "aggregationMode": 3, "autoSource": False, "lineType": 0,
    "weatherMode": 0, "modelIndex": 0,
    "useOnSiteWeatherStations": True, "primaryWeatherSource": 10,
    "showNetEnergy": True, "powerAverage": True,
    "includePOA": True, "includeGHI": False, "fillGaps": False,
    "showExternalTemperature": True, "showDeviceTemperature": False,
    "showAggregateLayers": True, "showSourceLayers": False,
    "xSeriesKey": None,
}

SLEEP = 1.5


def build_chart_payload(hw_keys, start_date, end_date):
    return {
        "chartType": 1,
        "binSize": 15,
        "context": "site",
        "start": start_date,
        "end": end_date,
        "futureDays": 0,
        "hardwareSet": hw_keys,
        "sectionCode": 0,
        "query": {
            "name": "CustomChart",
            "title": "Custom Chart",
            "initialSpan": 1,
            "dataItems": [],
            "kpiChart": {
                "siteKeys": [SITE_KEY],
                "categories": {
                    "measurements": MEASUREMENT_CATS,
                    "calculations": [],
                    "losses": [],
                    "financials": [],
                    "events": [],
                    "special": [],
                },
                "availabilityReferenceMode": 0,
                "availabilityPassMode": 0,
                "availabilityPowerThreshold": 0,
                "weatherModes": [],
                "weatherSources": [0],
                "inlineOptions": INLINE_OPTIONS,
            },
        },
        "source": [SITE_KEY],
    }


def fetch_chart(session, hw_keys, start_date, end_date):
    payload = build_chart_payload(hw_keys, start_date, end_date)
    r = session.post(
        f"{API_BASE}/view/chart?lastChanged=1900-01-01T00:00:00.000Z",
        json=payload, timeout=120,
    )
    if not r.ok:
        print(f"  WARN: chart HTTP {r.status_code} for {start_date}", file=sys.stderr)
        return None
    return r.json()


def parse_series(chart_data, start_date, bin_min=15):
    series_list = chart_data.get("series", [])
    start_dt = datetime.fromisoformat(start_date)

    rows_by_ts = {}
    for s in series_list:
        name = str(s.get("name", ""))
        data = s.get("dataBinned", [])
        if not data:
            continue

        for idx, val in enumerate(data):
            ts = start_dt + timedelta(minutes=idx * bin_min)
            ts_str = ts.strftime("%Y-%m-%d %H:%M")

            if ts_str not in rows_by_ts:
                rows_by_ts[ts_str] = {"timestamp": ts_str}

            if isinstance(val, list):
                v = val[0] if val else None
            else:
                v = val

            rows_by_ts[ts_str][name] = v

    return list(rows_by_ts.values())


def extract_inverter_rows(all_rows, inv_num, inv_hw):
    prefix = f"SunGrow SG125HV - Inverter {inv_num}"
    out = []
    for row in all_rows:
        ts = row["timestamp"]
        r = {"timestamp": ts, "inverter": f"Inverter {inv_num}"}

        for key, val in row.items():
            if key == "timestamp":
                continue
            if prefix in key:
                if "Line kW" in key:
                    r["ac_power_kw"] = val
                elif "DC Voltage1" in key or "DC Voltage," in key:
                    r["dc_voltage_v"] = val
                elif "DC Current1" in key or "DC Current," in key:
                    r["dc_current_a"] = val
                elif "Iac" in key:
                    r["ac_current_a"] = val
                elif "Total KWH" in key and "energy" not in key.lower():
                    r["energy_kwh"] = val
                elif "Fault" in key:
                    r["fault_code"] = val
            elif "POA" in key and "GHI" not in key:
                r["poa_wm2"] = val

        if any(k in r for k in ["ac_power_kw", "dc_voltage_v", "dc_current_a"]):
            out.append(r)
        elif r.get("poa_wm2") is not None:
            out.append(r)

    return out


def extract_meter_rows(all_rows):
    out = []
    for row in all_rows:
        ts = row["timestamp"]
        r = {"timestamp": ts}

        for key, val in row.items():
            if key == "timestamp":
                continue
            if "Production Meter" in key:
                if "Real power" in key:
                    r["meter_kw"] = val
                elif "Total energy" in key:
                    r["meter_kwh_cumul"] = val
                elif "Volts A-N" in key:
                    r["volts_an"] = val
                elif "Volts B-N" in key:
                    r["volts_bn"] = val
                elif "Volts C-N" in key:
                    r["volts_cn"] = val
                elif "Amps A" in key:
                    r["amps_a"] = val

        if any(k in r for k in ["meter_kw", "meter_kwh_cumul"]):
            out.append(r)

    return out


def morning_filter(rows, hour_start=5, hour_end=11):
    out = []
    for r in rows:
        ts = datetime.strptime(r["timestamp"], "%Y-%m-%d %H:%M")
        if hour_start <= ts.hour < hour_end:
            out.append(r)
    return out


def main():
    session = get_session()

    all_hw = list(INV_MAP.values()) + [POA_KEY, METER_KEY]
    print(f"Whitetail morning time-series extraction")
    print(f"  Inverters: {list(INV_MAP.keys())}")
    print(f"  Hardware keys: {len(all_hw)} devices")
    print(f"  Target dates: {len(TARGET_DATES)}")
    print(f"  Interval: 15-minute")
    print()

    # Batch dates into groups of 3 to reduce API calls
    # (each call for 3 days returns ~288 bins per series)
    all_inv_rows = []
    all_meter_rows = []

    batch_size = 3
    date_batches = []
    i = 0
    while i < len(TARGET_DATES):
        batch = TARGET_DATES[i:i + batch_size]
        date_batches.append(batch)
        i += batch_size

    for bi, batch in enumerate(date_batches):
        for d in batch:
            print(f"  [{bi*batch_size + batch.index(d) + 1:2d}/{len(TARGET_DATES)}] {d} ...", end=" ", flush=True)
            chart = fetch_chart(session, all_hw, d, d)
            if not chart:
                print("FAILED")
                continue

            all_rows = parse_series(chart, d)
            morning = morning_filter(all_rows)

            for inv_num, inv_hw in INV_MAP.items():
                inv_rows = extract_inverter_rows(morning, inv_num, inv_hw)
                all_inv_rows.extend(inv_rows)

            meter_rows = extract_meter_rows(morning)
            all_meter_rows.extend(meter_rows)

            series_count = len(chart.get("series", []))
            print(f"{len(morning)} morning bins, {series_count} series")
            time.sleep(SLEEP)

    # Write inverter time-series
    inv_fields = [
        "timestamp", "inverter", "dc_voltage_v", "dc_current_a",
        "ac_power_kw", "ac_current_a", "energy_kwh", "fault_code", "poa_wm2",
    ]
    with open("morning_timeseries.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=inv_fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(all_inv_rows)

    print(f"\nSaved: morning_timeseries.csv")
    print(f"  {len(all_inv_rows)} rows across {len(INV_MAP)} inverters, {len(TARGET_DATES)} dates")

    # Write meter time-series
    meter_fields = [
        "timestamp", "meter_kw", "meter_kwh_cumul",
        "volts_an", "volts_bn", "volts_cn", "amps_a",
    ]
    with open("meter_morning.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=meter_fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(all_meter_rows)

    print(f"\nSaved: meter_morning.csv")
    print(f"  {len(all_meter_rows)} rows, {len(TARGET_DATES)} dates")


if __name__ == "__main__":
    main()
