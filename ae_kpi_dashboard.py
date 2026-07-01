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

# Reuse the alert dashboard's proven inverter-heatmap data builder so the per-site
# strip is IDENTICAL to the one on the alerts dashboard (same CF, same handling of
# missing data). Import is side-effect-free (its main() is guarded).
import ae_alert_dashboard as aad

API_BASE  = "https://apps.alsoenergy.com/api"
PORTFOLIO = "C12941"
PORTFOLIO2 = "C47197"
EXCLUDE_SITES = {"S55935"}

DEPLOY_STATUS = {0: "Not In Service", 1: "Awaiting Approval", 2: "AlsoEnergy Approved", 3: "Fully Approved"}
DEPLOY_COLOR  = {0: "#aaa", 1: "#f0ad4e", 2: "#5bc0de", 3: "#5cb85c"}


HERE = Path(__file__).parent


def slug(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "_", name)


# ─── Project metadata (Projects-export.csv) ─────────────────────────────────
# Rich per-site specs (system design, commercial terms, location) joined to the
# live AlsoEnergy site via the CSV's AE_Name column. Shown on each site page.
PROJECT_CSV = HERE / "Projects-export.csv"

# The export's real header row is wrapped in HTML <span> tags, so we define the
# column order explicitly and skip the first row. Data rows carry a leading empty
# selector column that we strip.
PROJECT_COLUMNS = [
    "ProjectID", "Project", "State", "Contractor", "Status", "COD", "OnM_Exp_Date",
    "FC_Date", "SizeKwDC", "SizeKwAC", "PanelCt", "PanelMke", "PanelSizeW", "FixedvTOU",
    "InverterCt", "InvertMfgr", "InverterSizekWAC", "StringCt", "ModsPString", "Xfmr_Ct",
    "Xfmr_Mfgr", "XfmrSizekV", "CombinerBoxCt", "Racking", "RackType", "Rows", "Utility",
    "Rev_Rate_MWH", "PPA_MWh", "REC", "AE_Name", "SPR", "Image", "PVSyst_Size",
    "Group_Name", "Organization", "Proximity", "Street_Address", "City", "State2",
    "Zip2", "Address", "Address1", "Zip", "GPS", "County", "Latitude", "Longitude",
]


def _norm_name(s: str) -> str:
    """Normalize a site name for fuzzy joining (e.g. 'RRH 1 & 2' == 'RRH 1&2')."""
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def load_project_meta():
    """Read Projects-export.csv → {normalized AE_Name: {column: value}}.

    Returns {} if the CSV is missing so the dashboard degrades gracefully.
    """
    import csv
    if not PROJECT_CSV.exists():
        print(f"  [warn] {PROJECT_CSV.name} not found — site specs will be omitted.")
        return {}
    out = {}
    try:
        with open(PROJECT_CSV, newline="", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            next(reader, None)                       # skip the HTML-wrapped header
            for row in reader:
                if not any(c.strip() for c in row):  # blank line
                    continue
                if row and row[0].strip() == "" and len(row) >= len(PROJECT_COLUMNS) + 1:
                    row = row[1:]                    # drop leading selector column
                d = dict(zip(PROJECT_COLUMNS, row))
                ae = _norm_name(d.get("AE_Name"))
                if ae:
                    out[ae] = d
    except Exception as e:
        print(f"  [warn] failed to parse {PROJECT_CSV.name}: {e}")
        return {}
    print(f"  project metadata: {len(out)} sites from {PROJECT_CSV.name}")
    return out


def _spec_txt(v):
    """Clean a raw CSV value; '' for blanks / N/A placeholders."""
    if v is None:
        return ""
    s = str(v).strip()
    return "" if s.upper() in ("N/A", "NA", "NONE", "NULL") else s


def _spec_float(v):
    s = _spec_txt(v)
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _spec_int(v):
    """Integer-ish display: '1,308' from '1308', passes text through unchanged."""
    f = _spec_float(v)
    if f is None:
        return _spec_txt(v)
    return f"{int(round(f)):,}"


def _spec_size(v):
    """kW value → 'X.XX MW' when ≥1 MW, else 'N,NNN kW'."""
    f = _spec_float(v)
    if f is None:
        return ""
    return f"{f / 1000:.2f} MW" if f >= 1000 else f"{f:,.0f} kW"


def _spec_money(v):
    f = _spec_float(v)
    if f is None:
        return ""
    return f"${f:,.2f}/MWh"


def _combo(*parts):
    """Join non-empty parts, e.g. '80 × Sungrow @ 125 kW' skipping missing pieces."""
    parts = [p for p in parts if p]
    return " ".join(parts).strip()


def build_site_specs_html(name, meta_map):
    """Project-spec panel (system design / commercial / location) for one site."""
    m = meta_map.get(_norm_name(name))
    if not m:
        return ('<div class="spec-none">No project record found in '
                'Projects-export.csv for this site.</div>')

    g = lambda k: _spec_txt(m.get(k))  # noqa: E731

    def group(title, pairs):
        rows = "".join(
            f'<div class="spec-row"><span class="k">{k}</span>'
            f'<span class="v">{v}</span></div>'
            for k, v in pairs if v
        )
        return f'<div class="spec-group"><h4>{title}</h4>{rows}</div>' if rows else ""

    panels = _combo(_spec_int(m.get("PanelCt")),
                    "×" if g("PanelMke") else "", g("PanelMke"),
                    f"{g('PanelSizeW')}W" if g("PanelSizeW") else "")
    inverters = _combo(_spec_int(m.get("InverterCt")),
                       "×" if g("InvertMfgr") else "", g("InvertMfgr"),
                       f"@ {g('InverterSizekWAC')} kW" if g("InverterSizekWAC") else "")
    strings = _combo(_spec_int(m.get("StringCt")),
                     f"× {g('ModsPString')} mods" if g("ModsPString") else "")
    xfmr = _combo(_spec_int(m.get("Xfmr_Ct")),
                  "×" if g("Xfmr_Mfgr") else "", g("Xfmr_Mfgr"),
                  f"@ {g('XfmrSizekV')} kVA" if g("XfmrSizekV") else "")
    racking = _combo(g("Racking"), f"({g('RackType')})" if g("RackType") else "")

    system = group("System Design", [
        ("DC Size", _spec_size(m.get("SizeKwDC"))),
        ("AC Size", _spec_size(m.get("SizeKwAC"))),
        ("PVSyst Size", _spec_size(m.get("PVSyst_Size"))),
        ("Panels", panels),
        ("Inverters", inverters),
        ("Strings", strings),
        ("Combiner Boxes", _spec_int(m.get("CombinerBoxCt"))),
        ("Transformers", xfmr),
        ("Racking", racking),
        ("Rows", _spec_int(m.get("Rows"))),
        ("Tariff", g("FixedvTOU")),
    ])

    commercial = group("Commercial", [
        ("Status", g("Status")),
        ("COD", g("COD")),
        ("O&M Expiration", g("OnM_Exp_Date")),
        ("Financial Close", g("FC_Date")),
        ("Contractor", g("Contractor")),
        ("Utility", g("Utility")),
        ("Revenue Rate", _spec_money(m.get("Rev_Rate_MWH"))),
        ("PPA Rate", _spec_money(m.get("PPA_MWh"))),
        ("REC", _spec_money(m.get("REC"))),
        ("Organization", g("Organization")),
        ("Group", g("Group_Name")),
    ])

    lat, lon = _spec_float(m.get("Latitude")), _spec_float(m.get("Longitude"))
    if lat is not None and lon is not None:
        coords = (f'<a href="https://www.google.com/maps?q={lat},{lon}" '
                  f'target="_blank" rel="noopener">{lat:.5f}, {lon:.5f}</a>')
    else:
        coords = ""
    address = _combo(g("Street_Address"),
                     f"{g('City')}," if g("City") else "",
                     g("State2") or g("State"), g("Zip2") or g("Zip"))
    location = group("Location", [
        ("Address", address),
        ("City", g("City")),
        ("County", g("County")),
        ("State", g("State2") or g("State")),
        ("Coordinates", coords),
    ])

    img = g("Image")
    photo = (f'<img class="spec-photo" src="{img}" alt="{name}" '
             f'loading="lazy" onerror="this.style.display=\'none\'">'
             if img.startswith("http") else "")

    return f'{photo}<div class="specs-grid">{system}{commercial}{location}</div>'


def load_active_alerts():
    """Real active-alert counts per site from ae_alerts.xlsx (is_resolved == False).

    The KPI API's `activeAlerts` field comes back 0, so we count unresolved
    alerts from the alert history instead — same source the alerts dashboard uses.
    Returns {site_name: unresolved_count}.
    """
    from collections import Counter
    f = HERE / "ae_alerts.xlsx"
    if not f.exists():
        return {}
    import openpyxl
    ws = openpyxl.load_workbook(f, read_only=True)["Alerts"]
    it = ws.values
    hdr = {h: i for i, h in enumerate(next(it))}
    si, ri = hdr.get("site_name"), hdr.get("is_resolved")
    if si is None or ri is None:
        return {}
    counts = Counter()
    for r in it:
        if r[ri] is False:                    # unresolved / active
            counts[r[si]] += 1
    return dict(counts)


def load_production():
    """Per-inverter 15-min production from ae_production_cache.json (written by
    ae_alert_dashboard.py). Returns (prod, prod_bins, d_from, d_to)."""
    from datetime import date
    f = HERE / "ae_production_cache.json"
    if not f.exists():
        return {}, {}, None, None
    try:
        c = json.loads(f.read_text(encoding="utf-8"))
        return (c.get("prod", {}), c.get("bins", {}),
                date.fromisoformat(c["d_from"]), date.fromisoformat(c["d_to"]))
    except Exception as e:
        print(f"  [warn] production cache load failed: {e}")
        return {}, {}, None, None


def load_site_alerts():
    """All alerts per site from ae_alerts.xlsx → {site_name: [row dicts]}."""
    from collections import defaultdict
    f = HERE / "ae_alerts.xlsx"
    if not f.exists():
        return {}
    import openpyxl
    it = openpyxl.load_workbook(f, read_only=True)["Alerts"].values
    hdr = {h: i for i, h in enumerate(next(it))}

    def g(r, col):
        i = hdr.get(col)
        return r[i] if i is not None else None

    out = defaultdict(list)
    for r in it:
        out[g(r, "site_name")].append({
            "start": str(g(r, "alert_start") or "")[:16],
            "event": g(r, "event_type_name") or "",
            "device": g(r, "hardware_name") or "",
            "severity": g(r, "severity") or "",
            "resolved": bool(g(r, "is_resolved")),
            "desc": (g(r, "description") or "")[:120],
        })
    for rows in out.values():
        rows.sort(key=lambda a: a["start"], reverse=True)
    return dict(out)


def build_heatmap_html(site, hw, prod, prod_bins, d_from, d_to):
    """Inverter heatmap identical to the alerts dashboard: per-inverter hourly
    capacity-factor strip (jet colormap), grey where there's no data. Reuses the
    alert dashboard's build_strip_data so the two never drift."""
    if not d_from or site not in prod:
        return ('<div class="hm-empty">No per-inverter production data cached for this '
                'site (run the alerts dashboard to populate it).</div>')
    strip = aad.build_strip_data(site, hw, d_from, d_to,
                                 production=prod.get(site),
                                 n_bins_api=prod_bins.get(site, 0))
    if not strip.get("invs"):
        return '<div class="hm-empty">No inverters found for this site.</div>'
    return (
        '<div class="strip-wrap"><div class="strip-labels" id="lbS"></div>'
        '<div style="flex:1;min-width:0"><canvas id="hmS" class="strip-canvas"></canvas></div></div>'
        '<div class="strip-legend"><span class="scale-ruler"><span class="scalebar"></span>'
        '<span class="scale-ticks"><span>0%</span><span>20%</span><span>40%</span>'
        '<span>60%</span><span>80%</span><span>100%</span></span></span>'
        '<span class="strip-legendlbl">Capacity Factor (%) &middot; hatched = night &middot; grey = no data</span></div>'
        f'<script type="application/json" id="dS">{json.dumps(strip)}</script>')


# Focused CF-only strip renderer (same jet colormap + missing-data handling as the
# alerts dashboard). Passed into SITE_HTML as a .format value, so braces stay single.
STRIP_JS = r"""
const ROW_H=14, GAP=1, AVG_H=16, AXIS_H=36;
function jet(v){
  const r=Math.max(0,Math.min(255,Math.round(255*(1.5-Math.abs(4*v-3)))));
  const g=Math.max(0,Math.min(255,Math.round(255*(1.5-Math.abs(4*v-2)))));
  const b=Math.max(0,Math.min(255,Math.round(255*(1.5-Math.abs(4*v-1)))));
  return [r,g,b];
}
function drawStrip(sid){
  const dEl=document.getElementById('d'+sid), cv=document.getElementById('hm'+sid);
  if(!dEl||!cv) return;
  const data=JSON.parse(dEl.textContent);
  const nInv=data.invs.length; if(!nInv) return;
  const bm=data.binMin||60, binsPerHour=60/bm;
  const totalH=AVG_H+nInv*ROW_H+AXIS_H;
  const wCss=Math.max(cv.parentElement.clientWidth,500);
  const dpr=window.devicePixelRatio||1;
  cv.width=wCss*dpr; cv.height=totalH*dpr; cv.style.height=totalH+'px';
  const ctx=cv.getContext('2d'); ctx.scale(dpr,dpr);
  const bw=wCss/data.bins;
  const t0=new Date(data.start.replace(' ','T'));
  function isNight(b){ const hr=(t0.getHours()+b/binsPerHour)%24; return hr<5.5||hr>=20.5; }
  const nightPat=(()=>{ const pc=document.createElement('canvas'); pc.width=4;pc.height=4;
    const p=pc.getContext('2d'); p.fillStyle='#fff';p.fillRect(0,0,4,4);
    p.strokeStyle='#d0d0d0';p.lineWidth=.5; p.beginPath();p.moveTo(0,4);p.lineTo(4,0);p.stroke();
    return ctx.createPattern(pc,'repeat'); })();
  const rows=data.vals;
  const avg=[]; for(let b=0;b<data.bins;b++){ let s=0,n=0;
    for(let i=0;i<rows.length;i++){ const v=rows[i][b]; if(v!==null&&v!==undefined&&v>=0){s+=v;n++;} }
    avg.push(n?s/n:null); }
  function paintRow(rv,y,h){ for(let b=0;b<data.bins;b++){ const v=rv[b]; const night=isNight(b);
    if(v===null||v===undefined){ctx.fillStyle=night?nightPat:'#e8e8e8';}
    else if(night&&v<1){ctx.fillStyle=nightPat;}
    else { const c=jet(Math.min(v/100,1)); ctx.fillStyle='rgb('+c[0]+','+c[1]+','+c[2]+')'; }
    ctx.fillRect(b*bw,y,Math.ceil(bw)+0.5,h-GAP); } }
  let y=0;
  paintRow(avg,y,AVG_H); y+=AVG_H;
  for(let i=0;i<nInv;i++){ paintRow(rows[i],y+i*ROW_H,ROW_H); }
  const gridTop=AVG_H+nInv*ROW_H;
  const tickHours=[5,8,12,16,20], tickLabels=['5a','8a','12p','4p','8p'];
  ctx.font='11px Segoe UI, Arial';
  for(let b=0;b<data.bins;b++){ const dt=new Date(t0.getTime()+b*bm*60000);
    const hr=dt.getHours(),mn=dt.getMinutes();
    if(hr===0&&mn===0){ctx.fillStyle='rgba(0,0,0,.2)';ctx.fillRect(b*bw,0,1,gridTop);}
    const ti=tickHours.indexOf(hr);
    if(ti>=0&&mn===0){ctx.fillStyle='#777';ctx.textAlign='center';ctx.fillText(tickLabels[ti],b*bw,gridTop+14);} }
  ctx.fillStyle='#444';ctx.font='bold 12px Segoe UI, Arial';ctx.textAlign='center';
  for(let b=0;b<data.bins;b+=binsPerHour*24){ const d=new Date(t0.getTime()+b*bm*60000);
    ctx.fillText((d.getMonth()+1)+'/'+d.getDate(),(b+binsPerHour*12)*bw,gridTop+30); }
  const lb=document.getElementById('lb'+sid);
  let h='<div class="avg" style="height:'+AVG_H+'px;line-height:'+AVG_H+'px">Average</div>';
  h+=data.invs.map(n=>'<div title="'+n+'">'+n+'</div>').join('');
  lb.innerHTML=h;
  const tip=document.getElementById('hmTip');
  cv.onmousemove=e=>{ const rect=cv.getBoundingClientRect();
    const mx=e.clientX-rect.left,my=e.clientY-rect.top; const b=Math.floor(mx/bw);
    if(b<0||b>=data.bins){tip.style.display='none';return;}
    const tS=new Date(t0.getTime()+b*bm*60000);
    const fmtT=d=>{let h=d.getHours(),m=d.getMinutes(),ap='am';if(h>=12){ap='pm';if(h>12)h-=12;}if(h===0)h=12;return h+':'+(m<10?'0':'')+m+ap;};
    const timeStr=fmtT(tS)+' '+((tS.getMonth()+1)+'/'+tS.getDate());
    let html;
    if(my<AVG_H){const v=avg[b];html='<b>Average of all inverters</b><br>'+timeStr+'<br>'+(v===null?'No data':'<b>CF: '+v.toFixed(1)+'%</b>');}
    else { const ri=Math.floor((my-AVG_H)/ROW_H); if(ri<0||ri>=nInv){tip.style.display='none';return;}
      const cf=data.vals[ri]?data.vals[ri][b]:null; const kw=data.kw&&data.kw[ri]?data.kw[ri][b]:null;
      const cap=data.caps?data.caps[ri]:0;
      html='<b>'+data.invs[ri]+'</b><br>'+timeStr+'<br>';
      if(cf===null&&kw===null){html+='<span style="color:#bbb">No data</span>';}
      else{if(cf!==null)html+='<b>CF: '+cf.toFixed(1)+'%</b><br>';if(kw!==null)html+=kw.toFixed(1)+' kW';if(cap>0)html+=' / '+Math.round(cap)+' kW';} }
    tip.innerHTML=html;tip.style.display='block';
    tip.style.left=Math.min(e.clientX+14,window.innerWidth-360)+'px';tip.style.top=(e.clientY+14)+'px'; };
  cv.onmouseleave=()=>tip.style.display='none';
}
window.addEventListener('DOMContentLoaded',()=>{try{drawStrip('S');}catch(e){}});
let _hmRt; window.addEventListener('resize',()=>{clearTimeout(_hmRt);_hmRt=setTimeout(()=>{try{drawStrip('S');}catch(e){}},200);});
"""


def build_site_alerts_html(site, site_alerts):
    """Alert table for a single site."""
    rows = site_alerts.get(site, [])
    if not rows:
        return '<div class="hm-empty">No alerts recorded for this site in the window.</div>'
    n_open = sum(1 for a in rows if not a["resolved"])
    trs = []
    for a in rows[:40]:
        status = ('<span class="al-open">OPEN</span>' if not a["resolved"]
                  else '<span class="al-res">resolved</span>')
        trs.append(f"<tr><td>{a['start']}</td><td><b>{a['event']}</b>"
                   f"<div class='al-desc'>{a['desc']}</div></td>"
                   f"<td>{a['device']}</td><td>{status}</td></tr>")
    more = (f"<div class='hm-empty'>Showing 40 of {len(rows)}.</div>"
            if len(rows) > 40 else "")
    return (f"<div class='al-summary'>{n_open} open · {len(rows)} total in window</div>"
            f"<table class='al-table'><tr><th>Start</th><th>Event</th>"
            f"<th>Device</th><th>Status</th></tr>{''.join(trs)}</table>{more}")


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
  .full {{ padding: 0 24px 16px; }}
  .full .card {{ padding: 16px; }}
  /* inverter heatmap strip (identical to alerts dashboard) */
  .strip-wrap {{ display: flex; gap: 8px; margin: 8px 0 6px; }}
  .strip-labels {{ display: flex; flex-direction: column; }}
  .strip-labels div {{ height: 14px; line-height: 14px; font-size: 10px; color: #555;
                      white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
                      max-width: 200px; min-width: 140px; }}
  .strip-labels div.avg {{ font-weight: 700; color: #1F4E79; }}
  .strip-canvas {{ width: 100%; display: block; }}
  .strip-legend {{ display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-top: 8px; }}
  .scale-ruler {{ display: inline-flex; flex-direction: column; }}
  .scalebar {{ width: 200px; height: 12px; border-radius: 2px;
    background: linear-gradient(90deg,#00007f,#0000ff,#007fff,#00ffff,#7fff7f,#ffff00,#ff7f00,#ff0000,#7f0000); }}
  .scale-ticks {{ display: flex; justify-content: space-between; width: 200px; }}
  .scale-ticks span {{ font-size: 9px; color: #888; }}
  .strip-legendlbl {{ font-size: 11px; color: #666; }}
  .hm-tip {{ position: fixed; background: rgba(20,30,40,.95); color: #fff; font-size: 11px;
            padding: 6px 9px; border-radius: 4px; pointer-events: none; z-index: 99;
            max-width: 340px; display: none; line-height: 1.5; }}
  .hm-empty {{ color: #888; font-size: 12px; padding: 8px 0; }}
  /* per-site alerts */
  .al-summary {{ font-size: 12px; color: #666; margin-bottom: 8px; }}
  .al-table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
  .al-table th {{ text-align: left; font-size: 10px; color: #888; text-transform: uppercase; padding: 4px 8px; border-bottom: 1px solid #eee; }}
  .al-table td {{ padding: 6px 8px; border-bottom: 1px solid #f5f5f5; vertical-align: top; }}
  .al-desc {{ color: #999; font-size: 11px; }}
  .al-open {{ color: #c62828; font-weight: 700; }}
  .al-res {{ color: #2e9e5b; }}
  /* site specifications (from Projects-export.csv) */
  .specs-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; }}
  .spec-group h4 {{ font-size: 11px; text-transform: uppercase; letter-spacing: .5px;
                    color: #2E75B6; margin-bottom: 6px; padding-bottom: 4px;
                    border-bottom: 1px solid #eef1f5; }}
  .spec-row {{ display: flex; justify-content: space-between; gap: 12px; padding: 5px 0;
               font-size: 13px; border-bottom: 1px solid #f7f8fa; }}
  .spec-row .k {{ color: #777; white-space: nowrap; }}
  .spec-row .v {{ font-weight: 600; color: #333; text-align: right; }}
  .spec-row .v a {{ color: #2E75B6; text-decoration: none; }}
  .spec-photo {{ float: right; width: 260px; max-width: 42%; border-radius: 6px;
                 margin: 0 0 12px 18px; box-shadow: 0 1px 4px rgba(0,0,0,.15); }}
  .spec-none {{ color: #888; font-size: 12px; padding: 8px 0; }}
  @media (max-width: 900px) {{ .specs-grid {{ grid-template-columns: 1fr; }}
                               .spec-photo {{ float: none; width: 100%; max-width: 100%; margin: 0 0 12px; }} }}
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

<div class="full">
  <div class="card">
    <div class="card-title">Site Specifications</div>
    {site_specs_html}
  </div>
</div>

<div class="full">
  <div class="card">
    <div class="card-title">Inverter Heatmap — hourly capacity factor</div>
    {heatmap_html}
  </div>
</div>

<div class="full">
  <div class="card">
    <div class="card-title">Alerts — this site</div>
    {site_alerts_html}
  </div>
</div>

<div class="hm-tip" id="hmTip"></div>
<script>{strip_js}</script>

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
  header h1 {{ font-size: 20px; font-weight: 600; }}
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
  /* per-site 24h actual-vs-expected donut */
  .donut-wrap {{ position: relative; width: 46px; height: 46px; margin: 0 auto; }}
  .donut {{ width: 46px; height: 46px; }}
  .donut-bg {{ fill: none; stroke: #eef1f5; stroke-width: 3.6; }}
  .donut-fg {{ fill: none; stroke-width: 3.6; stroke-linecap: round; }}
  .donut-label {{ position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; font-size: 11px; font-weight: 700; }}
  .donut-missing {{ width: 46px; height: 46px; margin: 0 auto; display: flex; flex-direction: column; align-items: center; justify-content: center; color: #b0b7c3; font-size: 9px; line-height: 1.1; text-align: center; }}
  .donut-missing span:first-child {{ font-size: 14px; }}
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
  <div class="meta">Generated: {generated_at}<br><a href="alerts.html" style="color:#ffd54f;font-weight:600">⚠ Operational Alerts</a></div>
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


def build_site_html(s, all_sites, generated_at, hw=None, prod=None, prod_bins=None,
                    site_alerts=None, d_from=None, d_to=None, project_meta=None):
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
    active_alerts = int(s.get("active_alerts", 0))
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

    heatmap_html = build_heatmap_html(name, hw or {}, prod or {}, prod_bins or {},
                                      d_from, d_to)
    site_alerts_html = build_site_alerts_html(name, site_alerts or {})
    site_specs_html = build_site_specs_html(name, project_meta or {})

    return SITE_HTML.format(
        site_name=name, site_key=key, generated_at=generated_at,
        heatmap_html=heatmap_html, site_alerts_html=site_alerts_html,
        site_specs_html=site_specs_html,
        strip_js=STRIP_JS,
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


def donut_24h(meas, exp):
    """Small SVG donut: past-24h actual vs expected energy (real KPI data).

    Filled fraction = actual/expected (capped at 100% for the ring). Green when
    on-target (90–115%), amber otherwise (under- or over-performing/suspect).
    'No data' when expected energy is unavailable — never a fabricated value.
    """
    if not exp or exp <= 0:
        return ('<div class="donut-missing" title="No expected-energy data for the last 24h">'
                '<span>&#9888;</span><span>No&nbsp;data</span></div>')
    ratio = meas / exp * 100
    frac = max(0.0, min(ratio, 100.0))
    color = "#2e9e5b" if 90 <= ratio <= 115 else "#e08a00"
    return (f'<div class="donut-wrap" title="Past 24h: {meas:,.0f} kWh actual vs '
            f'{exp:,.0f} kWh expected ({ratio:.0f}%)">'
            f'<svg viewBox="0 0 36 36" class="donut">'
            f'<circle class="donut-bg" cx="18" cy="18" r="15.9"/>'
            f'<circle class="donut-fg" cx="18" cy="18" r="15.9" stroke="{color}" '
            f'stroke-dasharray="{frac:.1f} {100 - frac:.1f}" transform="rotate(-90 18 18)"/>'
            f'</svg><div class="donut-label" style="color:{color}">{ratio:.0f}%</div></div>')


def build_site_card(s):
    d = s["data"]
    key = s["key"]
    name = s["name"]
    now  = safe(d, "now")
    cap  = safe(d, "systemSize", 1)
    pct  = round(min(100, (now / cap) * 100), 1) if cap else 0
    meas = safe(d, "measKWh"); exp = safe(d, "expKWh")
    alerts = int(s.get("active_alerts", 0))
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
        <div class="metric">{donut_24h(meas, exp)}<div class="metric-label">24h vs Exp</div></div>
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
    total_alerts = int(sum(s.get("active_alerts", 0) for s in sites))
    alert_sites  = sum(1 for s in sites if s.get("active_alerts", 0) > 0)
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
        alerts = s.get("active_alerts", 0)
        col = "#dc3545" if alerts > 0 or rc > 3 else ("#ffc107" if rc > 0 else "#2E75B6")
        scatter_pts.append({"x": round(exp, 1), "y": round(meas, 1)})
        bubble_pts.append({"x": round(pi, 1), "y": round(avail, 1), "r": 8})
        names.append(s["name"])
        colors.append(col)

    site_cards = "\n".join(build_site_card(s) for s in sorted(sites, key=lambda s: s.get("active_alerts", 0) + safe(s["data"], "ruleToolConfiguration", 0), reverse=True))

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

    # Attach real active-alert counts (KPI API activeAlerts field returns 0)
    amap = load_active_alerts()
    for s in sites:
        s["active_alerts"] = amap.get(s["name"], 0)
    print(f"  active alerts: {sum(s['active_alerts'] for s in sites)} "
          f"across {sum(1 for s in sites if s['active_alerts'] > 0)} sites")

    # Export real per-site capacity (systemSize = AC nameplate) for other dashboards
    cap_cache = {s["name"]: {"key": s["key"],
                             "ac_kw": round(safe(s["data"], "systemSize"), 1),
                             "dc_kw": round(safe(s["data"], "dCsize"), 1)}
                 for s in sites}
    (HERE / "ae_site_capacity.json").write_text(json.dumps(cap_cache), encoding="utf-8")
    print(f"  capacity cache saved ({len(cap_cache)} sites, "
          f"{sum(c['ac_kw'] for c in cap_cache.values())/1000:.1f} MW AC total)")

    if args.site:
        sites = [s for s in sites if s["key"] == args.site]
        if not sites:
            sys.exit(f"Site {args.site} not found in portfolio.")

    # Remove stale KPI HTML files only (S*.html + index.html), preserve alerts.html etc.
    if out_dir.exists():
        for f in out_dir.glob("S*.html"):
            try:
                f.unlink()
            except Exception:
                pass
    out_dir.mkdir(parents=True, exist_ok=True)

    # Per-site inverter heatmaps + alerts for the site detail pages
    prod, prod_bins, d_from, d_to = load_production()
    hw = aad.load_hardware()
    site_alerts = load_site_alerts()
    project_meta = load_project_meta()
    print(f"  production cache: {len(prod)} sites ({d_from}..{d_to}) | "
          f"hardware: {len(hw)} sites | alert history: {len(site_alerts)} sites")

    # Generate per-site HTML
    for s in sites:
        key  = s["key"]
        name = s["name"]
        fname = f"{key}_{slug(name)}.html"
        path  = out_dir / fname
        html  = build_site_html(s, sites, generated_at, hw, prod, prod_bins,
                                site_alerts, d_from, d_to, project_meta)
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
