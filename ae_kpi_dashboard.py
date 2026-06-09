#!/usr/bin/env python3
"""
Generates per-site KPI dashboards (HTML) mirroring the AlsoEnergy system dashboard.

Fetches live data via POST /api/view/kpidashboard for all portfolio sites,
renders interactive HTML files with Chart.js, and overwrites previous versions.

Output:
  dashboards/index.html              — portfolio overview
  dashboards/SXXXXX_SiteName.html   — one per site

USAGE
-----
    python ae_kpi_dashboard.py                     # all sites
    python ae_kpi_dashboard.py --site S65787       # single site
    python ae_kpi_dashboard.py --out reports/kpi   # custom output dir
"""

import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

API_BASE  = "https://apps.alsoenergy.com/api"
PORTFOLIO = "C12941"
PORTFOLIO2 = "C47197"
EXCLUDE_SITES = {"S55935"}

DEPLOY_STATUS = {0: "Not In Service", 1: "Awaiting Approval", 2: "AlsoEnergy Approved", 3: "Fully Approved"}
DEPLOY_COLOR  = {0: "#aaa", 1: "#f0ad4e", 2: "#5bc0de", 3: "#5cb85c"}


def slug(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "_", name)


def get_session():
    from ae_auth import get_session as _gs
    return _gs()


def fetch_kpi(session, portfolio_keys):
    all_sites = []
    for pk in portfolio_keys:
        url = f"{API_BASE}/view/kpidashboard?lastChanged=1900-01-01T00:00:00.000Z"
        r = session.post(url, json={"keys": [pk]}, timeout=30)
        r.raise_for_status()
        data = r.json()
        sites = [s for s in data.get("sites", []) if s.get("key") not in EXCLUDE_SITES]
        all_sites.extend(sites)
    # Deduplicate by site key (C47197 overlaps with C12941)
    seen = set()
    unique = []
    for s in all_sites:
        if s["key"] not in seen:
            seen.add(s["key"])
            unique.append(s)
    return unique


def safe(d, key, default=0):
    v = d.get(key, default)
    if v is None:
        return default
    if isinstance(v, str):
        try:
            v = float(v)
        except (ValueError, TypeError):
            return default
    if isinstance(v, float) and v != v:  # NaN
        return default
    return v


def fmt_kw(v):
    if v >= 1000:
        return f"{v/1000:.2f} MW"
    return f"{v:.1f} kW"


def fmt_kwh(v):
    if v >= 1000:
        return f"{v/1000:.2f} MWh"
    return f"{v:.1f} kWh"


# ─── HTML templates ─────────────────────────────────────────────────────────

SITE_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{site_name} — KPI Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #f4f6f9; color: #333; }}
  header {{ background: #1F4E79; color: #fff; padding: 14px 24px; display: flex; align-items: center; justify-content: space-between; }}
  header h1 {{ font-size: 20px; font-weight: 600; }}
  header .meta {{ font-size: 12px; opacity: 0.75; text-align: right; }}
  .nav {{ background: #2E75B6; padding: 6px 24px; }}
  .nav a {{ color: #cde; text-decoration: none; font-size: 13px; margin-right: 16px; }}
  .nav a:hover {{ color: #fff; }}
  .grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; padding: 20px 24px 0; }}
  .grid2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; padding: 16px 24px 24px; }}
  .card {{ background: #fff; border-radius: 6px; box-shadow: 0 1px 4px rgba(0,0,0,.12); padding: 16px; }}
  .card-title {{ font-size: 11px; color: #888; text-transform: uppercase; letter-spacing: .5px; margin-bottom: 10px; }}
  .big-num {{ font-size: 36px; font-weight: 700; color: #1F4E79; }}
  .sub-num {{ font-size: 13px; color: #666; margin-top: 2px; }}
  .gauge-wrap {{ text-align: center; }}
  svg.gauge {{ overflow: visible; }}
  .rule-table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  .rule-table th {{ font-size: 11px; color: #888; font-weight: 500; padding: 4px 8px; border-bottom: 1px solid #eee; text-align: left; }}
  .rule-table td {{ padding: 6px 8px; border-bottom: 1px solid #f5f5f5; }}
  .badge {{ display: inline-block; min-width: 28px; padding: 1px 6px; border-radius: 3px; text-align: center; font-weight: 600; font-size: 12px; }}
  .badge-ok {{ background: #d4edda; color: #155724; }}
  .badge-warn {{ background: #fff3cd; color: #856404; }}
  .badge-fail {{ background: #f8d7da; color: #721c24; }}
  .loss-row {{ display: flex; justify-content: space-between; align-items: center; padding: 5px 0; border-bottom: 1px solid #f5f5f5; font-size: 13px; }}
  .loss-label {{ color: #555; }}
  .loss-val {{ font-weight: 600; }}
  .deploy-bar {{ margin-top: 8px; }}
  .deploy-label {{ font-size: 13px; font-weight: 600; color: #1F4E79; }}
  .progress-track {{ background: #e9ecef; border-radius: 4px; height: 8px; margin-top: 6px; }}
  .progress-fill {{ height: 8px; border-radius: 4px; transition: width .5s; }}
  .chart-container {{ position: relative; height: 280px; }}
  .pct-row {{ display: flex; justify-content: space-between; margin-top: 8px; font-size: 12px; color: #777; }}
  .pct-good {{ color: #155724; font-weight: 600; }}
  .pct-bad {{ color: #721c24; font-weight: 600; }}
  footer {{ text-align: center; font-size: 11px; color: #aaa; padding: 12px; }}
</style>
</head>
<body>
<header>
  <div>
    <h1>{site_name}</h1>
    <div style="font-size:13px;margin-top:2px;opacity:.8">{site_key} &bull; SolRiver Capital</div>
  </div>
  <div class="meta">
    Generated: {generated_at}<br>
    <a href="index.html" style="color:#cde">← Portfolio Overview</a>
  </div>
</header>
<div class="nav">
  <a href="index.html">Portfolio</a>
  <span style="color:#cde">{site_name}</span>
</div>

<div class="grid">
  <!-- Current Power -->
  <div class="card">
    <div class="card-title">Current Power</div>
    <div class="gauge-wrap">
      <svg class="gauge" width="160" height="100" viewBox="0 0 160 100">
        <path d="M20,90 A60,60,0,0,1,140,90" stroke="#e9ecef" stroke-width="14" fill="none" stroke-linecap="round"/>
        <path id="gaugeFill" d="M20,90 A60,60,0,0,1,140,90" stroke="#2E75B6" stroke-width="14" fill="none" stroke-linecap="round"
              stroke-dasharray="{gauge_dash} 188.5"/>
        <text x="80" y="85" text-anchor="middle" font-size="22" font-weight="700" fill="#1F4E79">{now_kw}</text>
        <text x="80" y="100" text-anchor="middle" font-size="11" fill="#888">Total Cap: {cap_kw}</text>
        <text x="20" y="106" text-anchor="middle" font-size="9" fill="#aaa">0</text>
        <text x="140" y="106" text-anchor="middle" font-size="9" fill="#aaa">{cap_raw}</text>
      </svg>
    </div>
    <div class="pct-row">
      <span>{sites_count} site{sites_s}</span>
      <span class="{pwr_class}">{pwr_pct}% capacity</span>
    </div>
  </div>

  <!-- Losses Past 24hr -->
  <div class="card">
    <div class="card-title">Losses Past 24hr</div>
    {losses_html}
  </div>

  <!-- Rule Tool Summary -->
  <div class="card">
    <div class="card-title">Rule Tool Summary</div>
    <table class="rule-table">
      <tr><th>Category</th><th>Warnings</th></tr>
      {rule_rows}
    </table>
  </div>

  <!-- Deployment Status -->
  <div class="card">
    <div class="card-title">Deployment Status</div>
    <div class="deploy-bar">
      <div class="deploy-label">{deploy_label}</div>
      <div style="font-size:12px;color:#888;margin-top:4px">System: {ac_size} AC / {dc_size} DC</div>
      <div class="progress-track" style="margin-top:10px">
        <div class="progress-fill" style="width:{deploy_pct}%;background:{deploy_color}"></div>
      </div>
      <div class="pct-row">
        <span>Active Alerts: <strong>{active_alerts}</strong></span>
        <span>Inverters: <strong>{inv_ok}/{inv_total}</strong></span>
      </div>
    </div>
    <div style="margin-top:12px">
      <div class="loss-row">
        <span class="loss-label">Availability</span>
        <span class="loss-val {avail_class}">{availability}%</span>
      </div>
      <div class="loss-row">
        <span class="loss-label">Inverter Avail.</span>
        <span class="loss-val">{inv_avail}%</span>
      </div>
    </div>
  </div>
</div>

<div class="grid2">
  <!-- Production Chart -->
  <div class="card">
    <div class="card-title">Production — Actual vs Expected (24h)</div>
    <div class="chart-container">
      <canvas id="prodChart"></canvas>
    </div>
    <div class="pct-row">
      <span>Measured: <strong>{meas_kwh}</strong></span>
      <span>Expected: <strong>{exp_kwh}</strong></span>
      <span class="{meas_class}">{meas_pct}% performance</span>
    </div>
  </div>

  <!-- Energy Summary -->
  <div class="card">
    <div class="card-title">Energy Summary</div>
    <div class="chart-container">
      <canvas id="energyChart"></canvas>
    </div>
    <div class="pct-row">
      <span>Today: <strong>{today_kwh}</strong> ({today_pct}%)</span>
      <span>Yesterday: <strong>{yest_kwh}</strong> ({yest_pct}%)</span>
    </div>
  </div>
</div>

<footer>SolRiver Capital &bull; AlsoEnergy PowerTrack &bull; Generated {generated_at}</footer>

<script>
const prodCtx = document.getElementById('prodChart').getContext('2d');
new Chart(prodCtx, {{
  type: 'bar',
  data: {{
    labels: ['Measured', 'Expected'],
    datasets: [{{
      label: 'kWh (24h)',
      data: [{meas_raw}, {exp_raw}],
      backgroundColor: ['#2E75B6', '#e9ecef'],
      borderColor: ['#1F4E79', '#ccc'],
      borderWidth: 1,
      borderRadius: 4,
    }}]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{ legend: {{ display: false }} }},
    scales: {{
      y: {{ beginAtZero: true, grid: {{ color: '#f0f0f0' }}, ticks: {{ callback: v => v >= 1000 ? (v/1000).toFixed(1)+'MWh' : v+'kWh' }} }},
      x: {{ grid: {{ display: false }} }}
    }}
  }}
}});

const energyCtx = document.getElementById('energyChart').getContext('2d');
new Chart(energyCtx, {{
  type: 'bar',
  data: {{
    labels: ['Today Actual', 'Today Est.', 'Yesterday', 'Yest. Est.', 'Month', 'Year'],
    datasets: [{{
      data: [{today_raw}, {today_est_raw}, {yest_raw}, {yest_est_raw}, {month_raw}, {year_raw}],
      backgroundColor: ['#2E75B6','#90c0e8','#5cb85c','#90d890','#f0ad4e','#9b59b6'],
      borderRadius: 3,
    }}]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{ legend: {{ display: false }} }},
    scales: {{
      y: {{ beginAtZero: true, grid: {{ color: '#f0f0f0' }},
            ticks: {{ callback: v => v >= 1000000 ? (v/1000000).toFixed(1)+'GWh' : v >= 1000 ? (v/1000).toFixed(0)+'MWh' : v+'kWh' }} }},
      x: {{ grid: {{ display: false }}, ticks: {{ font: {{ size: 10 }} }} }}
    }}
  }}
}});
</script>
</body>
</html>
"""

INDEX_HTML_HEAD = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SolRiver Capital — Portfolio KPI Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #f4f6f9; color: #333; }}
  header {{ background: #1F4E79; color: #fff; padding: 14px 24px; display: flex; align-items: center; justify-content: space-between; }}
  header h1 {{ font-size: 22px; font-weight: 600; }}
  header .meta {{ font-size: 12px; opacity: 0.75; text-align: right; }}
  .summary-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; padding: 20px 24px 0; }}
  .card {{ background: #fff; border-radius: 6px; box-shadow: 0 1px 4px rgba(0,0,0,.12); padding: 16px; }}
  .card-title {{ font-size: 11px; color: #888; text-transform: uppercase; letter-spacing: .5px; margin-bottom: 8px; }}
  .big-num {{ font-size: 32px; font-weight: 700; color: #1F4E79; }}
  .sub-num {{ font-size: 12px; color: #666; margin-top: 2px; }}
  .sites-section {{ padding: 16px 24px 24px; }}
  .sites-title {{ font-size: 15px; font-weight: 600; color: #1F4E79; margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center; }}
  .sites-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 12px; }}
  .site-card {{ background: #fff; border-radius: 6px; box-shadow: 0 1px 4px rgba(0,0,0,.1); padding: 14px; border-left: 4px solid #2E75B6; transition: box-shadow .2s; cursor: pointer; text-decoration: none; color: inherit; display: block; }}
  .site-card:hover {{ box-shadow: 0 3px 12px rgba(0,0,0,.18); }}
  .site-card.alert {{ border-left-color: #dc3545; }}
  .site-card.warn {{ border-left-color: #ffc107; }}
  .site-card.good {{ border-left-color: #28a745; }}
  .site-name {{ font-size: 14px; font-weight: 600; color: #1F4E79; margin-bottom: 6px; }}
  .site-key {{ font-size: 11px; color: #aaa; }}
  .site-metrics {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 6px; margin-top: 8px; }}
  .metric {{ text-align: center; }}
  .metric-val {{ font-size: 15px; font-weight: 700; color: #2E75B6; }}
  .metric-label {{ font-size: 10px; color: #888; text-transform: uppercase; }}
  .badge {{ display: inline-block; padding: 1px 6px; border-radius: 3px; font-size: 11px; font-weight: 600; }}
  .badge-ok {{ background: #d4edda; color: #155724; }}
  .badge-warn {{ background: #fff3cd; color: #856404; }}
  .badge-fail {{ background: #f8d7da; color: #721c24; }}
  .charts-row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; padding: 0 24px 16px; }}
  .chart-container {{ position: relative; height: 300px; }}
  footer {{ text-align: center; font-size: 11px; color: #aaa; padding: 12px; }}
  .search-box {{ padding: 6px 12px; border: 1px solid #ddd; border-radius: 4px; font-size: 13px; width: 220px; }}
</style>
</head>
<body>
<header>
  <div>
    <h1>SolRiver Capital — Portfolio KPI Dashboard</h1>
    <div style="font-size:13px;margin-top:2px;opacity:.8">C12941 &bull; {site_count} Active Sites</div>
  </div>
  <div class="meta">Generated: {generated_at}</div>
</header>

<div class="summary-grid">
  <div class="card">
    <div class="card-title">Total Current Power</div>
    <div class="big-num">{total_now}</div>
    <div class="sub-num">Capacity: {total_cap}</div>
  </div>
  <div class="card">
    <div class="card-title">Portfolio Performance (24h)</div>
    <div class="big-num">{port_pct}%</div>
    <div class="sub-num">{port_meas} measured / {port_exp} expected</div>
  </div>
  <div class="card">
    <div class="card-title">Active Alerts</div>
    <div class="big-num" style="color:{alert_color}">{total_alerts}</div>
    <div class="sub-num">Across {alert_sites} sites</div>
  </div>
  <div class="card">
    <div class="card-title">Rule Tool Failures</div>
    <div class="big-num" style="color:#e67e22">{total_rule_fails}</div>
    <div class="sub-num">Config: {rf_config} &bull; Comm: {rf_comm} &bull; Data: {rf_data} &bull; Perf: {rf_perf}</div>
  </div>
</div>

<div class="charts-row">
  <div class="card" style="margin-top:16px">
    <div class="card-title">Actual vs Expected Energy — Past 24h (kWh per site)</div>
    <div class="chart-container"><canvas id="scatterChart"></canvas></div>
  </div>
  <div class="card" style="margin-top:16px">
    <div class="card-title">Performance Index vs Availability — Past 24h</div>
    <div class="chart-container"><canvas id="availChart"></canvas></div>
  </div>
</div>

<div class="sites-section">
  <div class="sites-title">
    <span>All Sites ({site_count})</span>
    <input class="search-box" id="search" placeholder="Filter sites..." onkeyup="filterSites()">
  </div>
  <div class="sites-grid" id="sitesGrid">
"""

INDEX_HTML_FOOT = """
  </div>
</div>
<footer>SolRiver Capital &bull; AlsoEnergy PowerTrack &bull; Generated {generated_at}</footer>
<script>
function filterSites() {{
  const q = document.getElementById('search').value.toLowerCase();
  document.querySelectorAll('.site-card').forEach(c => {{
    c.style.display = c.textContent.toLowerCase().includes(q) ? '' : 'none';
  }});
}}

const scatter = document.getElementById('scatterChart').getContext('2d');
new Chart(scatter, {{
  type: 'scatter',
  data: {{
    datasets: [{{
      label: 'Sites',
      data: {scatter_data},
      backgroundColor: {scatter_colors},
      pointRadius: 8,
      pointHoverRadius: 10,
    }}]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{
      legend: {{ display: false }},
      tooltip: {{
        callbacks: {{
          label: ctx => {{
            const names = {scatter_names};
            return names[ctx.dataIndex] + ' — actual: ' + ctx.parsed.y.toFixed(0) + ' kWh';
          }}
        }}
      }}
    }},
    scales: {{
      x: {{ title: {{ display: true, text: 'Expected Energy (kWh)' }}, grid: {{ color: '#f0f0f0' }} }},
      y: {{ title: {{ display: true, text: 'Actual Energy (kWh)' }}, beginAtZero: true, grid: {{ color: '#f0f0f0' }} }}
    }}
  }}
}});

const avail = document.getElementById('availChart').getContext('2d');
new Chart(avail, {{
  type: 'bubble',
  data: {{
    datasets: [{{
      label: 'Sites',
      data: {bubble_data},
      backgroundColor: {scatter_colors},
    }}]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{
      legend: {{ display: false }},
      tooltip: {{
        callbacks: {{
          label: ctx => {{
            const names = {scatter_names};
            return names[ctx.dataIndex] + ' — PI: ' + ctx.parsed.x.toFixed(0) + '%, Avail: ' + ctx.parsed.y.toFixed(0) + '%';
          }}
        }}
      }}
    }},
    scales: {{
      x: {{ title: {{ display: true, text: 'Performance Index (%)' }}, grid: {{ color: '#f0f0f0' }} }},
      y: {{ title: {{ display: true, text: 'Availability (%)' }}, min: 0, max: 110, grid: {{ color: '#f0f0f0' }} }}
    }}
  }}
}});
</script>
</body>
</html>
"""


def rule_badge(v):
    v = int(v or 0)
    if v == 0:
        return f'<span class="badge badge-ok">0</span>'
    elif v <= 1:
        return f'<span class="badge badge-warn">{v}</span>'
    return f'<span class="badge badge-fail">{v}</span>'


def build_site_html(s, all_sites, generated_at):
    d = s["data"]
    name = s["name"]
    key  = s["key"]

    now  = safe(d, "now")
    cap  = safe(d, "systemSize", 1)
    pct  = min(100, (now / cap) * 100) if cap else 0
    # SVG gauge: semi-circle arc is ~188.5px circumference; dasharray = pct/100 * 188.5
    gauge_dash = pct / 100 * 188.5

    # Losses
    dl = safe(d, "downtimeLoss"); sl = safe(d, "soilLoss"); snl = safe(d, "snowLoss")
    ul = safe(d, "unclassifiedLoss")
    cl_raw = d.get("curtailmentLoss", 0)
    try:
        cl = float(cl_raw) if cl_raw is not None else 0.0
        cl = 0.0 if cl != cl else cl  # NaN check
    except (TypeError, ValueError):
        cl = 0.0
    total_loss = dl + sl + snl + ul + cl
    losses_html = f"""
    <div class="big-num" style="font-size:22px;color:#{'155724' if total_loss < 10 else '721c24'}">{fmt_kwh(total_loss)} Loss</div>
    <div style="margin-top:8px">
      <div class="loss-row"><span class="loss-label">Downtime Loss</span><span class="loss-val">{fmt_kwh(dl)}</span></div>
      <div class="loss-row"><span class="loss-label">Soil Loss</span><span class="loss-val">{fmt_kwh(sl)}</span></div>
      <div class="loss-row"><span class="loss-label">Snow Loss</span><span class="loss-val">{fmt_kwh(snl)}</span></div>
      <div class="loss-row"><span class="loss-label">Unclassified</span><span class="loss-val">{fmt_kwh(ul)}</span></div>
    </div>"""

    # Rule tool
    rc = int(safe(d, "ruleToolConfiguration"))
    rm = int(safe(d, "ruleToolCommunication"))
    rd = int(safe(d, "ruleToolData"))
    rp = int(safe(d, "ruleToolPerformance"))
    rule_rows = "".join([
        f"<tr><td>Configuration</td><td>{rule_badge(rc)}</td></tr>",
        f"<tr><td>Communication</td><td>{rule_badge(rm)}</td></tr>",
        f"<tr><td>Data</td><td>{rule_badge(rd)}</td></tr>",
        f"<tr><td>Performance</td><td>{rule_badge(rp)}</td></tr>",
    ])

    # Deploy
    ds = int(safe(d, "deploymentStatus"))
    deploy_label = DEPLOY_STATUS.get(ds, "Unknown")
    deploy_color = DEPLOY_COLOR.get(ds, "#aaa")
    deploy_pct   = {0: 10, 1: 33, 2: 66, 3: 100}.get(ds, 50)

    avail = safe(d, "availability", 0)
    avail_class = "pct-good" if avail >= 95 else ("pct-bad" if avail < 80 else "")
    inv_avail = safe(d, "calculatedInverterAvailability", 0)
    active_alerts = int(safe(d, "activeAlerts"))
    inv_total = int(safe(d, "totalInverters"))
    inv_faults = int(safe(d, "inverterFaults"))
    inv_ok = inv_total - inv_faults

    # Production
    meas = safe(d, "measKWh"); exp = safe(d, "expKWh")
    meas_pct = safe(d, "measKWhPct", 0)
    meas_class = "pct-good" if meas_pct >= 90 else ("pct-bad" if meas_pct < 70 else "")

    today = safe(d, "today"); today_est = safe(d, "todayEst")
    today_pct = round(safe(d, "todayPct", 0), 1)
    yest = safe(d, "yesterday"); yest_est = safe(d, "yesterdayEst")
    yest_pct = round(safe(d, "yesterdayPct", 0), 1)
    month = safe(d, "month"); year = safe(d, "year")

    pwr_pct = round(pct, 1)
    pwr_class = "pct-good" if pct >= 70 else ("pct-bad" if pct < 30 else "")

    return SITE_HTML.format(
        site_name=name, site_key=key, generated_at=generated_at,
        gauge_dash=f"{gauge_dash:.1f}",
        now_kw=fmt_kw(now), cap_kw=fmt_kw(cap), cap_raw=round(cap),
        sites_count=1, sites_s="",
        pwr_pct=pwr_pct, pwr_class=pwr_class,
        losses_html=losses_html,
        rule_rows=rule_rows,
        deploy_label=deploy_label, deploy_color=deploy_color, deploy_pct=deploy_pct,
        ac_size=fmt_kw(cap), dc_size=fmt_kw(safe(d, "dCsize")),
        active_alerts=active_alerts, inv_ok=inv_ok, inv_total=inv_total,
        availability=round(avail, 1), avail_class=avail_class,
        inv_avail=round(inv_avail, 1),
        meas_kwh=fmt_kwh(meas), exp_kwh=fmt_kwh(exp),
        meas_pct=round(meas_pct, 1), meas_class=meas_class,
        meas_raw=round(meas, 1), exp_raw=round(exp, 1),
        today_kwh=fmt_kwh(today), today_pct=today_pct,
        yest_kwh=fmt_kwh(yest), yest_pct=yest_pct,
        today_raw=round(today, 1), today_est_raw=round(today_est, 1),
        yest_raw=round(yest, 1), yest_est_raw=round(yest_est, 1),
        month_raw=round(month, 1), year_raw=round(year, 1),
    )


def build_site_card(s):
    d = s["data"]
    key = s["key"]
    name = s["name"]
    now  = safe(d, "now")
    cap  = safe(d, "systemSize", 1)
    pct  = round(min(100, (now / cap) * 100), 1) if cap else 0
    meas_pct = round(safe(d, "measKWhPct", 0), 1)
    alerts = int(safe(d, "activeAlerts"))
    rc = int(safe(d, "ruleToolConfiguration")) + int(safe(d, "ruleToolCommunication")) + \
         int(safe(d, "ruleToolData")) + int(safe(d, "ruleToolPerformance"))
    card_class = "alert" if alerts > 0 or rc > 3 else ("warn" if rc > 0 else "good")
    fname = f"{key}_{slug(name)}.html"

    return f"""
    <a class="site-card {card_class}" href="{fname}">
      <div class="site-name">{name} <span class="site-key">{key}</span></div>
      <div class="site-metrics">
        <div class="metric"><div class="metric-val">{fmt_kw(now)}</div><div class="metric-label">Now</div></div>
        <div class="metric"><div class="metric-val">{pct}%</div><div class="metric-label">Capacity</div></div>
        <div class="metric"><div class="metric-val">{meas_pct}%</div><div class="metric-label">Perf 24h</div></div>
      </div>
      <div style="margin-top:8px;font-size:12px">
        Alerts: {rule_badge(alerts)}
        Rule fails: {rule_badge(rc)}
        Avail: <strong>{round(safe(d, 'availability', 0), 0):.0f}%</strong>
      </div>
    </a>"""


def build_index_html(sites, generated_at):
    total_now = sum(safe(s["data"], "now") for s in sites)
    total_cap = sum(safe(s["data"], "systemSize") for s in sites)
    total_meas = sum(safe(s["data"], "measKWh") for s in sites)
    total_exp  = sum(safe(s["data"], "expKWh") for s in sites)
    port_pct   = round((total_meas / total_exp * 100) if total_exp else 0, 1)
    total_alerts = int(sum(safe(s["data"], "activeAlerts") for s in sites))
    alert_sites  = sum(1 for s in sites if safe(s["data"], "activeAlerts") > 0)
    rf_config = int(sum(safe(s["data"], "ruleToolConfiguration") for s in sites))
    rf_comm   = int(sum(safe(s["data"], "ruleToolCommunication") for s in sites))
    rf_data   = int(sum(safe(s["data"], "ruleToolData") for s in sites))
    rf_perf   = int(sum(safe(s["data"], "ruleToolPerformance") for s in sites))
    total_rule_fails = rf_config + rf_comm + rf_data + rf_perf

    alert_color = "#dc3545" if total_alerts > 10 else ("#ffc107" if total_alerts > 0 else "#28a745")

    # Scatter data
    scatter_pts = []
    bubble_pts  = []
    names = []
    colors = []
    for s in sites:
        d = s["data"]
        meas = safe(d, "measKWh"); exp = safe(d, "expKWh")
        avail = safe(d, "availability", 0); pi = safe(d, "measKWhPct", 0)
        rc = int(safe(d, "ruleToolConfiguration")) + int(safe(d, "ruleToolCommunication")) + \
             int(safe(d, "ruleToolData")) + int(safe(d, "ruleToolPerformance"))
        alerts = safe(d, "activeAlerts")
        col = "#dc3545" if alerts > 0 or rc > 3 else ("#ffc107" if rc > 0 else "#2E75B6")
        scatter_pts.append({"x": round(exp, 1), "y": round(meas, 1)})
        bubble_pts.append({"x": round(pi, 1), "y": round(avail, 1), "r": 8})
        names.append(s["name"])
        colors.append(col)

    site_cards = "\n".join(build_site_card(s) for s in sorted(sites, key=lambda s: safe(s["data"], "activeAlerts", 0) + safe(s["data"], "ruleToolConfiguration", 0), reverse=True))

    head = INDEX_HTML_HEAD.format(
        site_count=len(sites), generated_at=generated_at,
        total_now=fmt_kw(total_now), total_cap=fmt_kw(total_cap),
        port_pct=port_pct, port_meas=fmt_kwh(total_meas), port_exp=fmt_kwh(total_exp),
        total_alerts=total_alerts, alert_sites=alert_sites, alert_color=alert_color,
        total_rule_fails=total_rule_fails,
        rf_config=rf_config, rf_comm=rf_comm, rf_data=rf_data, rf_perf=rf_perf,
    )
    foot = INDEX_HTML_FOOT.format(
        generated_at=generated_at,
        scatter_data=json.dumps(scatter_pts),
        bubble_data=json.dumps(bubble_pts),
        scatter_colors=json.dumps(colors),
        scatter_names=json.dumps(names),
    )
    return head + site_cards + foot


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default=None, help="Single site key (e.g. S65787)")
    ap.add_argument("--out", default="dashboards", help="Output directory")
    args = ap.parse_args()

    out_dir = Path(args.out)

    session = get_session()
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    print("Fetching KPI data...")
    sites = fetch_kpi(session, [PORTFOLIO, PORTFOLIO2])
    print(f"  {len(sites)} sites loaded")

    if args.site:
        sites = [s for s in sites if s["key"] == args.site]
        if not sites:
            sys.exit(f"Site {args.site} not found in portfolio.")

    # Remove stale HTML files, then ensure dir exists
    if out_dir.exists():
        for f in out_dir.glob("*.html"):
            try:
                f.unlink()
            except Exception:
                pass
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"  Output dir reset: {out_dir}/")

    # Generate per-site HTML
    for s in sites:
        key  = s["key"]
        name = s["name"]
        fname = f"{key}_{slug(name)}.html"
        path  = out_dir / fname
        html  = build_site_html(s, sites, generated_at)
        path.write_text(html, encoding="utf-8")
        now_kw = safe(s["data"], "now")
        perf   = round(safe(s["data"], "measKWhPct", 0), 1)
        print(f"  [{key}] {name:35s}  {fmt_kw(now_kw):10s}  perf={perf}%  -> {fname}")

    # Generate portfolio index
    if not args.site:
        idx_path = out_dir / "index.html"
        idx_path.write_text(build_index_html(sites, generated_at), encoding="utf-8")
        print(f"\nSaved portfolio index -> {idx_path}")

    print(f"\nDone — {len(sites)} dashboard(s) written to {out_dir}/")
    print(f"Open: {out_dir / 'index.html'}")
