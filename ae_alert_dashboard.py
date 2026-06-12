#!/usr/bin/env python3
"""
Automated Operational Alert Dashboard for the SolRiver portfolio.

Pulls the most recent alert history (default 7 days), filters to the alerts
that matter (inverter faults, production stops, grid events, tracker/TCU
faults), and renders dashboards/alerts.html with:

  - KPI strip            : alert volume, critical count, unresolved, sites hit
  - Critical alert table : faults / production stops, severity-ranked
  - Inverter heatmaps    : per affected site — inverter x day grid colored by
                           fault-hours (red) vs comm-loss-hours (orange)
  - Tracker / TCU section: per-site alarm-per-day charts + parsed TCU faults
  - Grid & meter events  : recloser / islanding / power-meter checks

Chart selection logic (alert category -> visualization + measurement unit):
  INVERTER_FAULT  -> inverter heatmap          (context: Power kW / AC Current A)
  INVERTER_COMM   -> inverter heatmap (orange) (context: comm hours)
  TRACKER         -> alarms-per-day bar chart  (context: tracker count / angle deg)
  GRID            -> event timeline            (context: AC Voltage V)
  METER           -> event table               (context: Power kW per phase)
  PERFORMANCE     -> event table               (context: Performance Index %)

Measurement -> unit map mirrors the PowerTrack Chart Builder:
  AC Current=A, AC Voltage=V, DC Current=A, DC Voltage=V, Power=kW,
  Energy=kWh, Irradiance=W/m^2, Temperature=degC, Availability=%,
  Performance Index=%, Energy Ratio=%, Capacity Factor=%, Phase Angle=deg

USAGE
-----
    python ae_alert_dashboard.py                 # last 7 days, live fetch
    python ae_alert_dashboard.py --days 14       # 14-day look-back
    python ae_alert_dashboard.py --offline       # use cached ae_alerts.xlsx
    python ae_alert_dashboard.py --out dashboards/alerts.html
"""

import argparse
import json
import re
import sys
import time
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

API_BASE       = "https://apps.alsoenergy.com/api"
PORTFOLIO_KEYS = ["C12941", "C47197"]
TZ_OFFSET_MIN  = 360
SLEEP          = 0.5
HERE           = Path(__file__).parent
CHARTJS_FILE   = HERE / "assets" / "chart.umd.min.js"
HW_XLSX        = HERE / "ae_hardware.xlsx"
ALERTS_XLSX    = HERE / "ae_alerts.xlsx"

# ── Measurement -> unit map (PowerTrack Chart Builder) ────────────────────
MEASUREMENT_UNITS = {
    "AC Current": "A", "AC Voltage": "V", "DC Current": "A", "DC Voltage": "V",
    "Power": "kW", "Energy": "kWh", "Energy (cumulative)": "kWh",
    "Estimated Power": "kW", "Estimated Energy": "kWh",
    "Expected Power": "kW", "Expected Energy": "kWh",
    "Irradiance": "W/m²", "Temperature": "°C", "Weather": "code",
    "Availability": "%", "Capacity Factor": "%", "Energy Ratio": "%",
    "Performance Index": "%", "Phase Angle": "°", "Faults": "count",
    "Control Setpoints": "kW", "Power On Time": "h", "String Current": "A",
}

SEVERITY_LABEL = {0: "Normal", 1: "Info", 2: "Warning", 3: "Critical",
                  4: "Emergency", 5: "High"}

# ── Alert classification ──────────────────────────────────────────────────
# (regex on event_type_name + description, asset_code) -> category
# First match wins. Category drives chart type, measurement and importance.

CATEGORY_META = {
    # category        weight  label                      measurement            chart
    "INVERTER_FAULT": (100, "Inverter Fault / Stop",     "Power",               "heatmap"),
    "GRID":           (95,  "Grid / Protection Event",   "AC Voltage",          "timeline"),
    "TRACKER_FAULT":  (80,  "Tracker TCU Fault",         "Phase Angle",         "tracker"),
    "METER":          (70,  "Production Meter Issue",    "Power",               "table"),
    "INVERTER_COMM":  (60,  "Inverter Comm Loss",        "Availability",        "heatmap"),
    "TRACKER_COMM":   (50,  "Tracker Comm Loss",         "Availability",        "tracker"),
    "PERFORMANCE":    (45,  "Performance / Irradiance",  "Performance Index",   "table"),
    "EQUIPMENT":      (40,  "Balance-of-Plant Equipment","Temperature",         "table"),
    "COMMS_LOW":      (10,  "Site Comms / Gateway",      "Availability",        "none"),
    "OTHER":          (5,   "Other",                     "Availability",        "none"),
}

def classify(event_type, description, asset):
    et   = (event_type or "").lower()
    desc = (description or "").lower()
    a    = (asset or "").upper()

    # Grid / protection first — these stop whole-site production
    if any(k in et or k in desc for k in
           ("recloser", "islanding", "grid power outage", "breaker status")):
        return "GRID"

    # Inverter faults & stops
    if a == "INV" or "inverter" in et or "inv fault" in et or "string inv" in et:
        if any(k in et for k in ("fault", "stopped", "inverter alerts")) \
           or any(k in desc for k in ("fault", "stop", "islanding", "shut")):
            return "INVERTER_FAULT"
        if any(k in et for k in ("communication", "heartbeat")):
            return "INVERTER_COMM"
        if "irradiance" in et or "performance" in et:
            return "PERFORMANCE"
        return "INVERTER_FAULT"   # unknown inverter alert: treat as important

    # Trackers
    if a == "TKR" or "tracker" in et or "tcu" in desc:
        if any(k in et for k in ("communication", "heartbeat")) and "tracker alert" not in et:
            return "TRACKER_COMM"
        if "no communication" in desc and "fault" not in desc:
            return "TRACKER_COMM"
        return "TRACKER_FAULT"

    # Meters
    if a == "MTR" or "power meter" in et or "meter" in et:
        return "METER"

    # Performance / rule tool
    if any(k in et for k in ("performance index", "irradiance check", "rule tool",
                             "data comparison")):
        return "PERFORMANCE"

    # Balance of plant
    if any(k in et for k in ("ups", "transformer", "sel ", "recloser", "controller health")):
        return "EQUIPMENT"

    # Low-value comms noise
    if any(k in et for k in ("communication", "heartbeat", "gateway")):
        return "COMMS_LOW"

    return "OTHER"


def importance(alert):
    """Score an alert: category weight + severity + duration + unresolved."""
    cat_w = CATEGORY_META[alert["category"]][0]
    sev   = alert.get("severity") or 0
    score = cat_w + sev * 4
    if not alert.get("is_resolved"):
        score += 20
    score += min(alert.get("duration_h") or 0, 48) * 0.5
    if alert.get("capacity"):
        score += min(float(alert["capacity"]) / 100.0, 10)
    return round(score, 1)


# ── Data fetching ─────────────────────────────────────────────────────────

def get_session():
    from ae_auth import get_session as _gs
    return _gs()


def fetch_alerts_live(session, d_from, d_to):
    rows = []
    for key in PORTFOLIO_KEYS:
        payload = {"key": key, "offset": TZ_OFFSET_MIN,
                   "from": d_from.isoformat(), "to": d_to.isoformat()}
        r = session.post(f"{API_BASE}/view/alerthistory", json=payload, timeout=60)
        if r.status_code == 204:
            continue
        r.raise_for_status()
        data = r.json()
        recs = data if isinstance(data, list) else next(
            (data[k] for k in ("list", "data", "alerts", "items", "rows")
             if isinstance(data.get(k), list)), [])
        for rec in recs:
            rows.append(normalize_live(rec))
        time.sleep(SLEEP)
    return rows


def parse_ts(v):
    if not v:
        return None
    if isinstance(v, datetime):
        return v
    s = str(v).strip()
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S", "%m/%d/%Y %I:%M:%S %p"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def split_event_code(s):
    if not s:
        return None
    m = re.match(r"^\s*(\d+)\s*-\s*(.+)$", str(s))
    return m.group(2).strip() if m else str(s).strip()


def normalize_live(rec):
    return {
        "site_key":      rec.get("siteKey"),
        "site_name":     rec.get("siteName"),
        "hardware_key":  rec.get("hardwareKey") or None,
        "hardware_name": rec.get("hardwareName") or None,
        "asset_code":    rec.get("assetCode") or None,
        "event_type":    split_event_code(rec.get("eventCode")),
        "description":   rec.get("description") or "",
        "severity":      rec.get("severity") or 0,
        "is_resolved":   bool(rec.get("isResolved")),
        "capacity":      rec.get("capacity"),
        "start":         parse_ts(rec.get("start")),
        "end":           parse_ts(rec.get("end")),
    }


def fetch_alerts_offline(d_from, d_to):
    import openpyxl
    wb = openpyxl.load_workbook(ALERTS_XLSX, read_only=True)
    ws = wb.active
    rows_iter = ws.values
    hdr = next(rows_iter)
    idx = {h: i for i, h in enumerate(hdr)}
    out = []
    for r in rows_iter:
        start = r[idx["alert_start"]]
        if isinstance(start, str):
            start = parse_ts(start)
        if not start or not (d_from <= start.date() <= d_to):
            continue
        out.append({
            "site_key":      None,
            "site_name":     r[idx["site_name"]],
            "hardware_key":  None,
            "hardware_name": r[idx["hardware_name"]],
            "asset_code":    r[idx["asset_code"]],
            "event_type":    r[idx["event_type_name"]],
            "description":   r[idx["description"]] or "",
            "severity":      r[idx["severity"]] or 0,
            "is_resolved":   bool(r[idx["is_resolved"]]),
            "capacity":      r[idx["capacity"]],
            "start":         start,
            "end":           r[idx["alert_end"]] if isinstance(r[idx["alert_end"]], datetime)
                             else parse_ts(r[idx["alert_end"]]),
        })
    return out


def load_hardware():
    """site_name -> {'inverters': [names...], 'trackers': [names...]}"""
    import openpyxl
    hw = defaultdict(lambda: {"inverters": [], "trackers": []})
    if not HW_XLSX.exists():
        return hw
    wb = openpyxl.load_workbook(HW_XLSX, read_only=True)
    ws = wb["Hardware Inventory"]
    rows_iter = ws.values
    hdr = next(rows_iter)
    idx = {h: i for i, h in enumerate(hdr)}
    for r in rows_iter:
        fc = r[idx["Function Code"]]
        site = r[idx["Site Name"]]
        name = r[idx["HW Name"]]
        if fc == 1:
            hw[site]["inverters"].append(name)
        elif fc == 24:
            hw[site]["trackers"].append(name)
    return hw


# ── Enrichment ────────────────────────────────────────────────────────────

def enrich(alerts, d_to):
    now = datetime.utcnow()
    for a in alerts:
        a["category"] = classify(a["event_type"], a["description"], a["asset_code"])
        end = a["end"] or now
        a["duration_h"] = round(max((end - a["start"]).total_seconds() / 3600, 0), 1) \
                          if a["start"] else 0
        a["score"] = importance(a)
        meta = CATEGORY_META[a["category"]]
        a["cat_label"], a["measurement"] = meta[1], meta[2]
        a["unit"] = MEASUREMENT_UNITS.get(meta[2], "")
    return alerts


# ── Aggregations for charts ──────────────────────────────────────────────

def day_range(d_from, d_to):
    days = []
    cur = d_from
    while cur <= d_to:
        days.append(cur)
        cur += timedelta(days=1)
    return days


def overlap_hours(a_start, a_end, day):
    """Hours of [a_start, a_end] overlapping calendar `day`."""
    d0 = datetime(day.year, day.month, day.day)
    d1 = d0 + timedelta(days=1)
    s = max(a_start, d0)
    e = min(a_end or datetime.utcnow(), d1)
    return max((e - s).total_seconds() / 3600, 0)


def build_inverter_heatmaps(alerts, hw, days):
    """site -> {inverter -> {day -> {'fault': h, 'comm': h, 'titles': set}}}"""
    sites = defaultdict(lambda: defaultdict(lambda: defaultdict(
        lambda: {"fault": 0.0, "comm": 0.0, "titles": set()})))
    for a in alerts:
        if a["category"] not in ("INVERTER_FAULT", "INVERTER_COMM"):
            continue
        if not a["hardware_name"] or not a["start"]:
            continue
        kind = "fault" if a["category"] == "INVERTER_FAULT" else "comm"
        for d in days:
            h = overlap_hours(a["start"], a["end"], d)
            if h > 0.01:
                cell = sites[a["site_name"]][a["hardware_name"]][d]
                cell[kind] += h
                cell["titles"].add(f"{a['event_type']}: {a['description'][:80]}")
    # ensure every inverter of an affected site shows (healthy rows too)
    for site in list(sites.keys()):
        for inv in hw.get(site, {}).get("inverters", []):
            _ = sites[site][inv]
    return sites


TCU_PATTERNS = [
    (re.compile(r"TCU Fault\s*(\d+)", re.I), "TCU Fault {}"),
    (re.compile(r"Individual Tracker Alarm\s*(\d+):\s*([^\t\n]+)", re.I), "Tracker {}: {}"),
    (re.compile(r"Slave Alarms?\s*S?\s*(\d+):\s*([^\t\n]+)", re.I), "Slave {}: {}"),
]

def parse_tcu_details(description):
    out = []
    for rx, fmt in TCU_PATTERNS:
        for m in rx.finditer(description or ""):
            out.append(fmt.format(*m.groups()))
    return out


def build_tracker_data(alerts, days):
    """site -> {'per_day': {day: {'fault': n, 'comm': n}}, 'details': [..]}"""
    sites = defaultdict(lambda: {"per_day": defaultdict(lambda: {"fault": 0, "comm": 0}),
                                 "details": []})
    for a in alerts:
        if a["category"] not in ("TRACKER_FAULT", "TRACKER_COMM"):
            continue
        kind = "fault" if a["category"] == "TRACKER_FAULT" else "comm"
        d = a["start"].date() if a["start"] else None
        if d and d in [x for x in days]:
            sites[a["site_name"]]["per_day"][d][kind] += 1
        det = parse_tcu_details(a["description"])
        for item in det[:12]:
            sites[a["site_name"]]["details"].append({
                "when": a["start"].strftime("%m-%d %H:%M") if a["start"] else "",
                "hw": a["hardware_name"] or "", "item": item,
                "resolved": a["is_resolved"],
            })
    return sites


# ── HTML rendering ────────────────────────────────────────────────────────

def esc(s):
    return (str(s or "").replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def heat_color(fault_h, comm_h):
    """Red scale for fault hours, orange for comm-only."""
    if fault_h > 0.05:
        a = min(0.15 + fault_h / 12.0, 1.0)
        return f"rgba(198,40,40,{a:.2f})"
    if comm_h > 0.05:
        a = min(0.15 + comm_h / 16.0, 0.9)
        return f"rgba(239,140,30,{a:.2f})"
    return "#eef3ea"


def build_strip_data(site, inv_map, hw, d_from, d_to):
    """Hourly availability strips per inverter (PowerTrack inverter-heatmap style).

    Returns dict for JS canvas renderer:
      invs   : inverter names
      bins   : number of hourly bins
      vals   : per inverter, per hour: 100=available .. 0=fault; -1=comm loss (no data)
      alerts : per inverter, list of alert strings
    """
    start = datetime(d_from.year, d_from.month, d_from.day)
    end = datetime(d_to.year, d_to.month, d_to.day) + timedelta(days=1)
    bins = int((end - start).total_seconds() // 3600)
    extra = inv_map or {}
    inv_names = sorted(set(hw.get(site, {}).get("inverters", [])) | set(extra),
                       key=lambda x: (len(str(x)), str(x)))
    return {"invs": inv_names, "bins": bins,
            "start": start.strftime("%Y-%m-%d %H:%M"),
            "vals": [[100] * bins for _ in inv_names],
            "alerts": [[] for _ in inv_names]}


def apply_alerts_to_strips(strip, site_alerts, d_from):
    """Burn alert windows into hourly strips: fault->0, comm->-1 (grey)."""
    start = datetime(d_from.year, d_from.month, d_from.day)
    idx = {name: i for i, name in enumerate(strip["invs"])}
    now = datetime.utcnow()
    for a in site_alerts:
        if a["category"] not in ("INVERTER_FAULT", "INVERTER_COMM"):
            continue
        i = idx.get(a["hardware_name"])
        if i is None or not a["start"]:
            continue
        a_end = a["end"] or now
        b0 = max(int((a["start"] - start).total_seconds() // 3600), 0)
        b1 = min(int((a_end - start).total_seconds() // 3600), strip["bins"] - 1)
        mark = 0 if a["category"] == "INVERTER_FAULT" else -1
        for b in range(b0, b1 + 1):
            if mark == 0 or strip["vals"][i][b] == 100:  # fault wins over comm
                strip["vals"][i][b] = mark
        t = a["start"].strftime("%m-%d %H:%M")
        state = "OPEN" if not a["is_resolved"] else f"{a['duration_h']:.1f}h"
        strip["alerts"][i] = (strip["alerts"][i] +
            [f"{t} · {a['event_type']} ({state})"])[:8]
    return strip


def render_diag_card(d, rank=None):
    ev = "".join(f"<li>{esc(e)}</li>" for e in d["evidence"][:6])
    badge = {"High": "diag-high", "Medium": "diag-med", "Low": "diag-low"}[d["conf_label"]]
    impact = f"{d['impact_kw']:.0f} kW at risk" if d["impact_kw"] else "monitoring impact"
    openpill = "<span class='pill pill-inverter_fault'>OPEN</span>" if d["open"] else ""
    rk = f"<span class='diag-rank'>#{rank}</span>" if rank else ""
    return f"""
    <div class="diag-card">
      <div class="diag-head">{rk}<b>{esc(d['site'])}</b> — {esc(d['title'])}
        <span class="diag-badge {badge}">{d['conf_label']} confidence</span>
        {openpill}<span class="diag-impact">{impact}</span></div>
      <ul class="diag-ev">{ev}</ul>
      <div class="diag-action">→ {esc(d['action'])}</div>
    </div>"""


def render_site_accordion(sid, site, strip, site_diags, fault_h, comm_h):
    """Clickable <details> per site: badge + canvas strip heatmap + diagnoses."""
    n_inv = len(strip["invs"])
    if fault_h > 1:
        badge = f"<span class='acc-badge acc-red'>{fault_h:.0f}h fault</span>"
    elif comm_h > 1:
        badge = f"<span class='acc-badge acc-orange'>{comm_h:.0f}h comm</span>"
    else:
        badge = "<span class='acc-badge acc-green'>healthy</span>"
    diag_html = "".join(render_diag_card(d) for d in site_diags[:3])
    open_attr = " open" if fault_h > 1 or any(d["open"] for d in site_diags) else ""
    return f"""
    <details class="site-acc" data-site="{esc(site.lower())}"{open_attr}>
      <summary><span class="acc-name">{esc(site)}</span>
        <span class="acc-meta">{n_inv} inverters</span>{badge}</summary>
      <div class="acc-body">
        {diag_html}
        <div class="strip-wrap">
          <div class="strip-labels" id="lb{sid}"></div>
          <div style="flex:1;min-width:0"><canvas id="hm{sid}" class="strip-canvas"></canvas></div>
        </div>
        <div class="legend" style="display:flex;align-items:center;gap:14px">
          <span style="font-size:11px;color:#666">Capacity Factor / Availability (%)</span>
          <span class="scalebar"></span>
          <span style="font-size:10px;color:#888">0%&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;100%</span>
          <span class="legend"><i style="background:#cfcfcf"></i>Comm loss / no data</span>
        </div>
      </div>
      <script type="application/json" id="d{sid}">{json.dumps(strip)}</script>
    </details>"""


def render_tracker_html(site, data, days, chart_id):
    labels = [d.strftime("%m/%d") for d in days]
    faults = [data["per_day"].get(d, {}).get("fault", 0) for d in days]
    comms  = [data["per_day"].get(d, {}).get("comm", 0) for d in days]
    det_rows = "".join(
        f"<tr><td>{esc(d['when'])}</td><td>{esc(d['hw'])}</td><td>{esc(d['item'])}</td>"
        f"<td>{'✔' if d['resolved'] else '<b class=red>open</b>'}</td></tr>"
        for d in data["details"][:25])
    details_tbl = (f"<table class='mini'><tr><th>When</th><th>Controller</th>"
                   f"<th>TCU / tracker detail</th><th>Resolved</th></tr>{det_rows}</table>"
                   if det_rows else "<div class='muted'>No per-TCU details parsed.</div>")
    return f"""
    <div class="card">
      <div class="card-title">Tracker / TCU — {esc(site)}
        <span class="unit-tag">alarms per day · context: tracker angle (°), SOC (%)</span></div>
      <div class="chart-wrap"><canvas id="{chart_id}"></canvas></div>
      {details_tbl}
    </div>
    <script>
    new Chart(document.getElementById('{chart_id}'), {{
      type: 'bar',
      data: {{ labels: {json.dumps(labels)},
        datasets: [
          {{label: 'TCU faults', data: {json.dumps(faults)}, backgroundColor: 'rgba(198,40,40,.75)'}},
          {{label: 'Comm loss', data: {json.dumps(comms)}, backgroundColor: 'rgba(239,140,30,.7)'}}
        ]}},
      options: {{ responsive: true, maintainAspectRatio: false,
        scales: {{ x: {{stacked: true}}, y: {{stacked: true, beginAtZero: true,
          title: {{display: true, text: 'Alarm count'}}, ticks: {{precision: 0}}}}}},
        plugins: {{legend: {{position: 'bottom'}}}}}}
    }});
    </script>"""


def render_critical_table(alerts, top_n=40):
    crit = [a for a in alerts if a["category"] in
            ("INVERTER_FAULT", "GRID", "TRACKER_FAULT", "METER")]
    crit.sort(key=lambda a: -a["score"])
    rows = []
    for a in crit[:top_n]:
        sev = SEVERITY_LABEL.get(a["severity"], a["severity"])
        status = "✔ resolved" if a["is_resolved"] else "<b class='red'>OPEN</b>"
        rows.append(f"""<tr>
          <td><span class="pill pill-{a['category'].lower()}">{esc(a['cat_label'])}</span></td>
          <td>{esc(a['site_name'])}</td>
          <td title="{esc(a['hardware_name'])}">{esc((a['hardware_name'] or '—')[:34])}</td>
          <td title="{esc(a['description'])}">{esc(a['event_type'])}<div class="desc">{esc(a['description'][:120])}</div></td>
          <td>{a['start'].strftime('%m-%d %H:%M') if a['start'] else '—'}</td>
          <td>{a['duration_h']:.1f} h</td>
          <td>{esc(sev)}</td>
          <td>{status}</td>
          <td class="muted">{esc(a['measurement'])} ({esc(a['unit'])})</td>
        </tr>""")
    if not rows:
        rows = ["<tr><td colspan='9' class='muted'>No critical alerts in window 🎉</td></tr>"]
    return f"""<table class="big">
      <tr><th>Category</th><th>Site</th><th>Device</th><th>Alert</th>
          <th>Start</th><th>Duration</th><th>Severity</th><th>Status</th><th>Check unit</th></tr>
      {''.join(rows)}</table>"""


PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Operational Alerts — SolRiver Capital</title>
<script>/* Chart.js v4.4.1 inlined for offline use */
{chartjs}
</script>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #f4f6f9; color: #333; }}
  header {{ background: #1F4E79; color: #fff; padding: 14px 24px; display: flex; justify-content: space-between; align-items: center; }}
  header h1 {{ font-size: 20px; }}
  header .meta {{ font-size: 12px; opacity: .75; text-align: right; }}
  .nav {{ background: #2E75B6; padding: 6px 24px; }}
  .nav a {{ color: #cde; text-decoration: none; font-size: 13px; margin-right: 16px; }}
  .kpis {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 14px; padding: 18px 24px 0; }}
  .card {{ background: #fff; border-radius: 6px; box-shadow: 0 1px 4px rgba(0,0,0,.12); padding: 16px; }}
  .card-title {{ font-size: 12px; color: #777; text-transform: uppercase; letter-spacing: .5px; margin-bottom: 10px; }}
  .unit-tag {{ float: right; text-transform: none; letter-spacing: 0; color: #2E75B6; font-size: 11px; }}
  .big-num {{ font-size: 32px; font-weight: 700; color: #1F4E79; }}
  .big-num.red {{ color: #c62828; }}
  .big-num.orange {{ color: #ef8c1e; }}
  .sub {{ font-size: 12px; color: #888; margin-top: 2px; }}
  section {{ padding: 16px 24px 0; }}
  section:last-of-type {{ padding-bottom: 24px; }}
  h2 {{ font-size: 15px; color: #1F4E79; margin: 4px 0 10px; }}
  table.big {{ width: 100%; border-collapse: collapse; font-size: 12.5px; background:#fff; }}
  table.big th {{ background: #1F4E79; color: #fff; font-size: 11px; padding: 6px 8px; text-align: left; position: sticky; top: 0; }}
  table.big td {{ padding: 6px 8px; border-bottom: 1px solid #eef; vertical-align: top; }}
  table.big tr:nth-child(even) td {{ background: #f6f9fd; }}
  .desc {{ color: #888; font-size: 11px; margin-top: 2px; }}
  .red {{ color: #c62828; }}
  .muted {{ color: #999; font-size: 12px; }}
  .pill {{ display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; white-space: nowrap; }}
  .pill-inverter_fault {{ background: #fde3e3; color: #b71c1c; }}
  .pill-grid {{ background: #ede3fd; color: #4a148c; }}
  .pill-tracker_fault {{ background: #fff0db; color: #a35e00; }}
  .pill-meter {{ background: #e0f0ff; color: #0d47a1; }}
  .grid2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
  .hm-card {{ overflow-x: auto; }}
  .hm {{ display: block; min-width: 520px; }}
  .hm-r {{ display: grid; grid-template-columns: 210px repeat(var(--days), 1fr); gap: 3px; margin-bottom: 3px; }}
  .hm-l {{ font-size: 11px; color: #555; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; line-height: 26px; }}
  .hm-h {{ font-size: 10px; color: #888; text-align: center; }}
  .hm-c {{ height: 26px; border-radius: 3px; font-size: 10px; color: #333; display: flex; align-items: center; justify-content: center; }}
  .legend {{ margin-top: 10px; font-size: 11px; color: #666; }}
  .legend span {{ margin-right: 16px; }}
  .legend i {{ display: inline-block; width: 12px; height: 12px; border-radius: 2px; vertical-align: -2px; margin-right: 4px; }}
  .chart-wrap {{ position: relative; height: 220px; margin-bottom: 10px; }}
  table.mini {{ width: 100%; border-collapse: collapse; font-size: 11.5px; }}
  table.mini th {{ background: #eef3fa; color: #1F4E79; padding: 4px 6px; text-align: left; font-size: 10.5px; }}
  table.mini td {{ padding: 4px 6px; border-bottom: 1px solid #f0f0f0; }}
  /* diagnosis / recommender */
  .diag-card {{ background: #fff; border-left: 4px solid #1F4E79; border-radius: 4px;
               box-shadow: 0 1px 3px rgba(0,0,0,.1); padding: 12px 14px; margin-bottom: 10px; }}
  .diag-head {{ font-size: 13.5px; color: #222; }}
  .diag-rank {{ display: inline-block; background: #1F4E79; color: #fff; border-radius: 50%;
               width: 22px; height: 22px; text-align: center; line-height: 22px;
               font-size: 11px; font-weight: 700; margin-right: 8px; }}
  .diag-badge {{ font-size: 10.5px; font-weight: 700; padding: 2px 8px; border-radius: 10px; margin-left: 8px; }}
  .diag-high {{ background: #fde3e3; color: #b71c1c; }}
  .diag-med  {{ background: #fff0db; color: #a35e00; }}
  .diag-low  {{ background: #eef3fa; color: #2E75B6; }}
  .diag-impact {{ float: right; font-size: 11px; color: #c62828; font-weight: 600; }}
  .diag-ev {{ margin: 8px 0 6px 18px; font-size: 11.5px; color: #555; }}
  .diag-ev li {{ margin-bottom: 2px; }}
  .diag-action {{ font-size: 12.5px; color: #155724; background: #f0f8f1;
                 border-radius: 4px; padding: 6px 10px; }}
  /* site accordion */
  .site-acc {{ background: #fff; border-radius: 6px; box-shadow: 0 1px 4px rgba(0,0,0,.12);
              margin-bottom: 8px; overflow-x: auto; }}
  .site-acc summary {{ cursor: pointer; padding: 12px 16px; font-size: 14px;
                      display: flex; align-items: center; gap: 12px; user-select: none; }}
  .site-acc summary:hover {{ background: #f6f9fd; }}
  .acc-name {{ font-weight: 600; color: #1F4E79; min-width: 240px; }}
  .acc-meta {{ font-size: 11px; color: #999; }}
  .acc-badge {{ font-size: 11px; font-weight: 700; padding: 2px 10px; border-radius: 10px; margin-left: auto; }}
  .acc-red {{ background: #fde3e3; color: #b71c1c; }}
  .acc-orange {{ background: #fff0db; color: #a35e00; }}
  .acc-green {{ background: #e3f4e4; color: #1b6e23; }}
  .acc-body {{ padding: 4px 16px 14px; }}
  /* strip heatmap (PowerTrack inverter-heatmap style) */
  .strip-wrap {{ display: flex; gap: 8px; margin: 8px 0 6px; }}
  .strip-labels {{ display: flex; flex-direction: column; }}
  .strip-labels div {{ height: 18px; line-height: 18px; font-size: 11px; color: #555;
                      white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
                      max-width: 200px; min-width: 140px; }}
  .strip-labels div.avg {{ font-weight: 700; color: #1F4E79; }}
  .strip-canvas {{ width: 100%; display: block; }}
  .scalebar {{ display: inline-block; width: 140px; height: 12px; border-radius: 2px;
    background: linear-gradient(90deg,#00007f,#0000ff,#007fff,#00ffff,#7fff7f,#ffff00,#ff7f00,#ff0000,#7f0000); }}
  .hm-tip {{ position: fixed; background: rgba(20,30,40,.95); color: #fff; font-size: 11px;
            padding: 6px 9px; border-radius: 4px; pointer-events: none; z-index: 99;
            max-width: 340px; display: none; line-height: 1.5; }}
  .controls {{ display: flex; gap: 10px; align-items: center; margin-bottom: 10px; }}
  .controls input {{ padding: 6px 10px; border: 1px solid #ccd; border-radius: 4px;
                    font-size: 13px; width: 260px; }}
  .controls button {{ padding: 6px 12px; border: 1px solid #2E75B6; background: #fff;
                     color: #2E75B6; border-radius: 4px; font-size: 12px; cursor: pointer; }}
  .controls button:hover {{ background: #2E75B6; color: #fff; }}
  footer {{ text-align: center; font-size: 11px; color: #aaa; padding: 14px; }}
</style>
</head>
<body>
<header>
  <div>
    <h1>Operational Alerts — Last {days_n} Days</h1>
    <div style="font-size:13px;margin-top:2px;opacity:.8">SolRiver Capital · {window_label}</div>
  </div>
  <div class="meta">Generated: {generated_at}<br><a href="index.html" style="color:#cde">← Portfolio Overview</a></div>
</header>
<div class="nav"><a href="index.html">Portfolio</a><span style="color:#cde">Operational Alerts</span></div>

<div class="kpis">
  <div class="card"><div class="card-title">Total Alerts</div><div class="big-num">{n_total}</div><div class="sub">{n_filtered} after noise filter</div></div>
  <div class="card"><div class="card-title">Critical (faults / stops)</div><div class="big-num red">{n_critical}</div><div class="sub">inverter, grid, meter</div></div>
  <div class="card"><div class="card-title">Tracker / TCU</div><div class="big-num orange">{n_tracker}</div><div class="sub">faults + comm loss</div></div>
  <div class="card"><div class="card-title">Unresolved</div><div class="big-num red">{n_open}</div><div class="sub">still open now</div></div>
  <div class="card"><div class="card-title">Sites Affected</div><div class="big-num">{n_sites}</div><div class="sub">of {n_sites_total} sites</div></div>
</div>

<section>
  <h2>⚕ Diagnosis &amp; Recommended Actions
    <span class="muted">(cross-referenced: alerts + rule tool + AI summaries + live power)</span></h2>
  {recommender}
</section>

<section>
  <h2>Critical Alerts — faults, production stops, grid events</h2>
  <div class="card" style="padding:0; max-height: 520px; overflow-y:auto">{critical_table}</div>
</section>

<section>
  <h2>Inverter Heatmaps — All Sites
    <span class="muted">— click a site to expand · hourly strips, jet scale (blue = 0%, red = 100%)</span></h2>
  <div class="controls">
    <input id="siteSearch" type="text" placeholder="Search sites…" oninput="filterSites(this.value)">
    <button onclick="setAll(true)">Expand all</button>
    <button onclick="setAll(false)">Collapse all</button>
    <span class="muted">{strip_note}</span>
  </div>
  {heatmaps}
</section>
<div class="hm-tip" id="hmTip"></div>

<section>
  <h2>Tracker / TCU Issues</h2>
  <div class="grid2">{trackers}</div>
</section>

<section>
  <h2>Category Breakdown</h2>
  <div class="grid2">
    <div class="card"><div class="card-title">Alerts by category</div>
      <div class="chart-wrap"><canvas id="catChart"></canvas></div></div>
    <div class="card"><div class="card-title">Alerts per day (all categories)</div>
      <div class="chart-wrap"><canvas id="dayChart"></canvas></div></div>
  </div>
</section>

<script>
new Chart(document.getElementById('catChart'), {{
  type: 'doughnut',
  data: {{ labels: {cat_labels}, datasets: [{{ data: {cat_counts},
    backgroundColor: ['#c62828','#7b1fa2','#ef8c1e','#0d47a1','#f4b942','#888','#5cb85c','#2E75B6','#aaa','#ccc'] }}] }},
  options: {{ responsive: true, maintainAspectRatio: false, plugins: {{legend: {{position: 'right'}}}} }}
}});
new Chart(document.getElementById('dayChart'), {{
  type: 'line',
  data: {{ labels: {day_labels}, datasets: [
    {{label: 'Critical', data: {day_crit}, borderColor: '#c62828', backgroundColor: 'rgba(198,40,40,.15)', fill: true, tension: .3}},
    {{label: 'All (filtered)', data: {day_all}, borderColor: '#2E75B6', backgroundColor: 'rgba(46,117,182,.1)', fill: true, tension: .3}}
  ]}},
  options: {{ responsive: true, maintainAspectRatio: false,
    scales: {{y: {{beginAtZero: true, title: {{display: true, text: 'Alert count'}}, ticks: {{precision: 0}}}}}},
    plugins: {{legend: {{position: 'bottom'}}}} }}
}});

/* ── PowerTrack-style strip heatmaps ─────────────────────────────── */
function jet(v) {{
  const r = Math.max(0, Math.min(255, Math.round(255*(1.5 - Math.abs(4*v - 3)))));
  const g = Math.max(0, Math.min(255, Math.round(255*(1.5 - Math.abs(4*v - 2)))));
  const b = Math.max(0, Math.min(255, Math.round(255*(1.5 - Math.abs(4*v - 1)))));
  return [r, g, b];
}}
const ROW_H = 18, GAP = 1, AXIS_H = 22;

function drawStrip(sid) {{
  const dEl = document.getElementById('d' + sid);
  const cv = document.getElementById('hm' + sid);
  if (!dEl || !cv || cv.dataset.drawn) return;
  const data = JSON.parse(dEl.textContent);
  const nRows = data.invs.length + 1;
  const wCss = Math.max(cv.parentElement.clientWidth, 400);
  const dpr = window.devicePixelRatio || 1;
  cv.width = wCss * dpr; cv.height = (nRows * ROW_H + AXIS_H) * dpr;
  cv.style.height = (nRows * ROW_H + AXIS_H) + 'px';
  const ctx = cv.getContext('2d'); ctx.scale(dpr, dpr);
  const bw = wCss / data.bins;

  const avg = [];
  for (let b = 0; b < data.bins; b++) {{
    let s = 0, n = 0;
    for (const row of data.vals) if (row[b] >= 0) {{ s += row[b]; n++; }}
    avg.push(n ? s / n : -1);
  }}
  const paint = (rowVals, y) => {{
    for (let b = 0; b < data.bins; b++) {{
      const v = rowVals[b];
      if (v < 0) ctx.fillStyle = '#cfcfcf';
      else {{ const c = jet(v / 100); ctx.fillStyle = `rgb(${{c[0]}},${{c[1]}},${{c[2]}})`; }}
      ctx.fillRect(b * bw, y, Math.ceil(bw), ROW_H - GAP);
    }}
  }};
  paint(avg, 0);
  data.vals.forEach((row, i) => paint(row, (i + 1) * ROW_H));

  ctx.fillStyle = '#888'; ctx.font = '10px Segoe UI'; ctx.textAlign = 'center';
  const t0 = new Date(data.start.replace(' ', 'T'));
  for (let h = 0; h < data.bins; h += 24) {{
    const d = new Date(t0.getTime() + h * 3600e3);
    const x = (h + 12) * bw;
    ctx.fillText((d.getMonth()+1) + '/' + d.getDate(), x, nRows * ROW_H + 14);
    ctx.fillStyle = '#ddd';
    ctx.fillRect(h * bw, 0, 1, nRows * ROW_H);
    ctx.fillStyle = '#888';
  }}

  const lb = document.getElementById('lb' + sid);
  lb.innerHTML = '<div class="avg">Average of All Inverters</div>' +
    data.invs.map(n => `<div title="${{n}}">${{n}}</div>`).join('');
  cv.dataset.drawn = '1';

  const tip = document.getElementById('hmTip');
  cv.onmousemove = e => {{
    const r = cv.getBoundingClientRect();
    const b = Math.floor((e.clientX - r.left) / bw);
    const row = Math.floor((e.clientY - r.top) / ROW_H);
    if (b < 0 || b >= data.bins || row >= nRows) {{ tip.style.display = 'none'; return; }}
    const t = new Date(t0.getTime() + b * 3600e3);
    const when = t.toLocaleString([], {{month:'numeric', day:'numeric', hour:'numeric'}});
    let html;
    if (row === 0) {{
      const v = avg[b];
      html = `<b>Average of all inverters</b><br>${{when}} — ` +
             (v < 0 ? 'no data' : v.toFixed(0) + '%');
    }} else {{
      const i = row - 1, v = data.vals[i][b];
      html = `<b>${{data.invs[i]}}</b><br>${{when}} — ` +
             (v < 0 ? 'comm loss / no data' : v.toFixed(0) + '%');
      if (data.alerts[i].length)
        html += '<br><span style="color:#ffb3b3">' +
                data.alerts[i].slice(0, 4).join('<br>') + '</span>';
    }}
    tip.innerHTML = html; tip.style.display = 'block';
    tip.style.left = Math.min(e.clientX + 14, window.innerWidth - 360) + 'px';
    tip.style.top = (e.clientY + 14) + 'px';
  }};
  cv.onmouseleave = () => tip.style.display = 'none';
}}

document.querySelectorAll('details.site-acc').forEach(d => {{
  const cvEl = d.querySelector('canvas');
  if (!cvEl) return;
  const sid = cvEl.id.slice(2);
  if (d.open) requestAnimationFrame(() => drawStrip(sid));
  d.addEventListener('toggle', () => {{ if (d.open) drawStrip(sid); }});
}});

function filterSites(q) {{
  q = q.toLowerCase();
  document.querySelectorAll('details.site-acc').forEach(d =>
    d.style.display = d.dataset.site.includes(q) ? '' : 'none');
}}
function setAll(open) {{
  document.querySelectorAll('details.site-acc').forEach(d => {{
    if (d.style.display === 'none') return;
    d.open = open;
  }});
}}
</script>
<footer>ae_alert_dashboard.py · data: AlsoEnergy PowerTrack alerthistory API · units per PowerTrack Chart Builder</footer>
</body>
</html>
"""


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--offline", action="store_true",
                    help="use cached ae_alerts.xlsx instead of the live API")
    ap.add_argument("--out", default=str(HERE / "dashboards" / "alerts.html"))
    args = ap.parse_args()

    d_to = date.today()
    d_from = d_to - timedelta(days=args.days - 1)

    if args.offline:
        print(f"[offline] reading {ALERTS_XLSX.name} ...")
        alerts = fetch_alerts_offline(d_from, d_to)
        if not alerts:
            all_alerts = fetch_alerts_offline(date(2000, 1, 1), d_to)
            if all_alerts:
                maxd = max(a["start"].date() for a in all_alerts if a["start"])
                d_to, d_from = maxd, maxd - timedelta(days=args.days - 1)
                alerts = [a for a in all_alerts
                          if a["start"] and d_from <= a["start"].date() <= d_to]
                print(f"[offline] window shifted to cached data: {d_from} .. {d_to}")
    else:
        session = get_session()
        print(f"Fetching alerts {d_from} .. {d_to} ...")
        alerts = fetch_alerts_live(session, d_from, d_to)

    print(f"{len(alerts)} alerts pulled")
    alerts = enrich(alerts, d_to)

    filtered = [a for a in alerts if not (
        a["category"] in ("COMMS_LOW", "OTHER") or
        (a["is_resolved"] and a["duration_h"] < 0.084 and
         a["category"] in ("INVERTER_COMM", "TRACKER_COMM")))]

    days = day_range(d_from, d_to)
    hw = load_hardware()
    heatmap_data = build_inverter_heatmaps(filtered, hw, days)
    tracker_data = build_tracker_data(filtered, days)

    crit_cats = ("INVERTER_FAULT", "GRID", "TRACKER_FAULT", "METER")
    n_critical = sum(1 for a in filtered if a["category"] in
                     ("INVERTER_FAULT", "GRID", "METER"))
    n_tracker = sum(1 for a in filtered if a["category"].startswith("TRACKER"))
    n_open = sum(1 for a in filtered if not a["is_resolved"])
    sites_hit = {a["site_name"] for a in filtered}

    # ── diagnosis + recommender ───────────────────────────────────────
    try:
        from ae_diagnosis import diagnose_portfolio
        diags = diagnose_portfolio(filtered, hw)
    except Exception as e:
        print(f"[warn] diagnosis engine failed: {e}")
        diags = []
    by_site_diag = defaultdict(list)
    for d in diags:
        if d["site"] != "PORTFOLIO":
            by_site_diag[d["site"]].append(d)
    recommender_html = "".join(
        render_diag_card(d, i + 1) for i, d in enumerate(diags[:10])) or \
        "<div class='card muted'>No diagnoses generated for this window.</div>"

    # ── per-site strip heatmaps for EVERY site ────────────────────────
    alerts_by_site = defaultdict(list)
    for a in filtered:
        alerts_by_site[a["site_name"]].append(a)
    all_sites = sorted(set(hw.keys()) | set(heatmap_data.keys()))

    def hours(site, kind):
        return sum(c[kind] for invs in heatmap_data.get(site, {}).values()
                   for c in invs.values() if isinstance(c, dict))

    site_order = sorted(all_sites,
                        key=lambda s: (-hours(s, "fault"), -hours(s, "comm"), s))
    heatmaps_html = ""
    for sid, site in enumerate(site_order):
        strip = build_strip_data(site, heatmap_data.get(site, {}), hw, d_from, d_to)
        if not strip["invs"]:
            continue
        strip = apply_alerts_to_strips(strip, alerts_by_site.get(site, []), d_from)
        heatmaps_html += render_site_accordion(
            sid, site, strip, by_site_diag.get(site, []),
            hours(site, "fault"), hours(site, "comm"))

    trackers_html = "".join(
        render_tracker_html(s, tracker_data[s], days, f"trk{i}")
        for i, s in enumerate(sorted(
            tracker_data.keys(),
            key=lambda s: -sum(v['fault'] + v['comm']
                               for v in tracker_data[s]['per_day'].values())))) or \
        "<div class='card muted'>No tracker/TCU alerts in this window.</div>"

    from collections import Counter
    cat_counter = Counter(a["cat_label"] for a in filtered)
    day_all = [sum(1 for a in filtered if a["start"] and a["start"].date() == d)
               for d in days]
    day_crit = [sum(1 for a in filtered if a["start"] and a["start"].date() == d
                    and a["category"] in crit_cats) for d in days]

    chartjs = CHARTJS_FILE.read_text(encoding="utf-8") if CHARTJS_FILE.exists() else ""
    if not chartjs:
        print("[warn] assets/chart.umd.min.js missing — charts will not render offline")

    html = PAGE.format(
        chartjs=chartjs,
        days_n=args.days,
        window_label=f"{d_from.strftime('%b %d')} – {d_to.strftime('%b %d, %Y')}",
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        n_total=len(alerts), n_filtered=len(filtered),
        n_critical=n_critical, n_tracker=n_tracker, n_open=n_open,
        n_sites=len(sites_hit), n_sites_total=35,
        critical_table=render_critical_table(filtered),
        recommender=recommender_html,
        heatmaps=heatmaps_html,
        strip_note="Strips show alert-derived availability on the CF scale; "
                   "real per-inverter Capacity Factor activates once the chart "
                   "API payload is captured.",
        trackers=trackers_html,
        cat_labels=json.dumps([k for k, _ in cat_counter.most_common()]),
        cat_counts=json.dumps([v for _, v in cat_counter.most_common()]),
        day_labels=json.dumps([d.strftime("%m/%d") for d in days]),
        day_all=json.dumps(day_all), day_crit=json.dumps(day_crit),
    )

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"Wrote {out}  ({len(html)/1024:.0f} KB)")


if __name__ == "__main__":
    main()
