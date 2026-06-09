#!/usr/bin/env python3
"""
ae_site_report.py — Generate Site Validation Report PDFs matching AlsoEnergy format.

Data sources:
  GET /api/view/site/{key}          — address, AC/DC capacity, valid data date
  GET /api/ruleresults/{key}        — diagnostic rule results per site
  GET /api/scriptsite/{key}         — hardware inventory (inverters, strings)
  POST /api/view/kpidashboard       — production totals, energy ratio

Usage:
    python ae_site_report.py --site S65787          # one site
    python ae_site_report.py --all                  # all 34 sites
    python ae_site_report.py --all --out reports/   # save to a folder
"""

import argparse
import datetime
import io
import sys
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib.enums import TA_CENTER
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        HRFlowable, Image, PageBreak,
    )
except ImportError:
    sys.exit("reportlab not installed.  Run: pip install reportlab")

from ae_auth import get_session

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

API_BASE  = "https://apps.alsoenergy.com/api"
PORTFOLIO = "C12941"
EXCLUDE   = {"S55935"}

RULE_MAP = {
    # id -> (display name, category)
    "NetworkCom":        ("Network Communication",    "Communication"),
    "CheckUpload":       ("Upload",                   "Communication"),
    "Availability":      ("Availability",             "Communication"),
    "InverterUptime":    ("Inverter Uptime",          "Communication"),
    "CheckSysSize":      ("System Size",              "Configuration"),
    "HasPVmodel":        ("PV Model",                 "Configuration"),
    "HasWSmodel":        ("WS & PV Model",            "Configuration"),
    "DefaultAlerts":     ("Default Alerts",           "Configuration"),
    "CheckHW":           ("Hardware Configuration",   "Configuration"),
    "SiteConfig":        ("Site Configuration",       "Configuration"),
    "AlertRecipients":   ("Alert Recipients",         "Configuration"),
    "InvalidAlerts":     ("Invalid Alerts",           "Configuration"),
    "PVPMenergy":        ("Meter vs. Inverter Energy","Data"),
    "kWandkWh":          ("Power vs. Energy",         "Data"),
    "CheckMeterVoltage": ("Meter Voltages",           "Data"),
    "CheckWeather":      ("Weather Station Data",     "Data"),
    "DataCuration":      ("Data Curation",            "Data"),
    "CheckPMCTs":        ("Meter CT Check",           "Data"),
}

DISPLAY_CATEGORIES = ["Communication", "Configuration", "Data"]

RESULT_LABEL = {4: "Pass", 3: "Fail", 2: "Warning", 1: "N/A"}

RULE_DESCRIPTIONS = {
    "Network Communication": "Identifies local network failures by identifying common communication problems on devices connected via TCP and RS-485.",
    "Upload":                "Verifies that all devices have uploaded recently. Most devices are expected to upload at least once every 15 minutes.",
    "Availability":          "Verifies that there are no gaps in the 15-minute data from all devices.",
    "System Size":           "Verifies that system size is set on the site and inverters.",
    "PV Model":              "Verifies that the PV model is completely configured for every inverter.",
    "WS & PV Model":         "Makes sure that irradiance and module temperature data are available from the weather stations on the site.",
    "Default Alerts":        "Verify that the devices are configured with the default alerts.",
    "Hardware Configuration":"Check a number of hardware configuration details, including alerts settings, PV and DC combiner output settings and the PV models.",
    "Site Configuration":    "Check a number of site configuration details, including: Latitude, longitude, time zone, Allow alert email and Limited communication settings.",
    "Alert Recipients":      "Make sure alerts are set up to be generated from this site and that there is at least one alert notification recipient.",
    "Meter vs. Inverter Energy": "Verifies that the energy measurements correlate between each production meter and the inverters connected to it.",
    "Power vs. Energy":      "Verify that the integral of the power matches the energy to within 10%. This test is run individually on each inverter and meter.",
    "Meter Voltages":        "Makes sure that the phase voltages are within 5% of each other.",
    "Weather Station Data":  "Verifies that temperature and irradiance data is within expected ranges. Checks temperature variation, ambient vs. module temperatures, and irradiance vs. expected GHI.",
}

# ---------------------------------------------------------------------------
# COLORS
# ---------------------------------------------------------------------------

BLUE_DARK  = colors.HexColor("#1565C0")
BLUE_LIGHT = colors.HexColor("#E3F2FD")
GRAY_LIGHT = colors.HexColor("#F5F5F5")
GREEN      = colors.HexColor("#2E7D32")
RED        = colors.HexColor("#C62828")
ORANGE     = colors.HexColor("#E65100")

# ---------------------------------------------------------------------------
# DATA FETCHING
# ---------------------------------------------------------------------------

def fetch_site(session, key):
    r = session.get(f"{API_BASE}/view/site/{key}", timeout=20)
    r.raise_for_status()
    return r.json()


def fetch_rules(session, key):
    r = session.get(f"{API_BASE}/ruleresults/{key}?lastChanged=1900-01-01T00:00:00.000Z&mergeHash=", timeout=20)
    r.raise_for_status()
    sites = r.json().get("sites", [])
    return sites[0] if sites else {}


def fetch_hardware(session, key):
    r = session.get(f"{API_BASE}/scriptsite/{key}?lastChanged=1900-01-01T00:00:00.000Z", timeout=20)
    if r.status_code == 404:
        return {}
    r.raise_for_status()
    return r.json()


def fetch_kpi(session, key, days=7):
    today  = datetime.date.today()
    d_from = (today - datetime.timedelta(days=days)).isoformat()
    r = session.post(
        f"{API_BASE}/view/kpidashboard?lastChanged=1900-01-01T00:00:00.000Z",
        json={"keys": [key], "from": d_from, "to": today.isoformat()},
        timeout=20,
    )
    r.raise_for_status()
    sites = r.json().get("sites", [])
    return sites[0]["data"] if sites else {}


def count_hardware(hw):
    """Return (n_inverters, n_strings) from scriptsite hardware list."""
    inverters = [h for h in hw.get("hardware", []) if h.get("functionCode") == 1]
    n_inv = len(inverters)
    n_str = sum(sum(h.get("strings") or []) for h in inverters)
    return n_inv, n_str

# ---------------------------------------------------------------------------
# CHARTS
# ---------------------------------------------------------------------------

def _fmt_date(d):
    return f"{d.month}/{d.day}/{d.year}"


def chart_production(kpi):
    fig, ax = plt.subplots(figsize=(6.5, 2.8))
    labels = ["Yesterday\nActual", "Yesterday\nExpected"]
    vals   = [kpi.get("yesterday", 0) / 1000, kpi.get("yesterdayEst", 0) / 1000]
    bars   = ax.bar(labels, vals, color=["#1565C0", "#FF8F00"], width=0.4)
    ax.set_ylabel("MWh", fontsize=9)
    ax.set_title("Metered Production vs. Model (Yesterday)", fontsize=10, pad=6)
    ax.tick_params(labelsize=8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.yaxis.grid(True, alpha=0.3, linestyle="--")
    ax.set_axisbelow(True)
    for bar, v in zip(bars, vals):
        ax.text(bar.get_x() + bar.get_width() / 2, v + max(vals) * 0.02,
                f"{v:.1f}", ha="center", fontsize=8, fontweight="bold")
    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=130, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf


def chart_energy_ratio(kpi):
    pct = kpi.get("yesterdayPct", 0)
    color = "#2E7D32" if pct >= 90 else ("#E65100" if pct >= 70 else "#C62828")
    fig, ax = plt.subplots(figsize=(5.5, 1.8))
    ax.barh([""], [100], color="#E0E0E0", height=0.5)
    ax.barh([""], [min(pct, 120)], color=color, height=0.5)
    ax.axvline(100, color="gray", linewidth=1, linestyle="--", alpha=0.5)
    ax.set_xlim(0, 125)
    ax.set_xlabel("Energy Ratio %", fontsize=9)
    ax.set_title(f"Inverter Energy Ratio (Yesterday) — {pct:.1f}%", fontsize=10)
    ax.tick_params(labelsize=8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=130, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf

# ---------------------------------------------------------------------------
# PDF BUILD
# ---------------------------------------------------------------------------

def _date_str(iso_str):
    if not iso_str:
        return "—"
    try:
        dt = datetime.datetime.fromisoformat(iso_str.replace("Z", ""))
        return f"{dt.month}/{dt.day}/{dt.year}"
    except Exception:
        return iso_str


def build_pdf(site, rules, kpi, hw_counts, out_path):
    today_str = _date_str(datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))

    doc = SimpleDocTemplate(
        str(out_path), pagesize=letter,
        leftMargin=0.6 * inch, rightMargin=0.6 * inch,
        topMargin=0.5 * inch, bottomMargin=0.5 * inch,
    )
    styles = getSampleStyleSheet()

    def style(name, **kw):
        return ParagraphStyle(name, parent=styles["Normal"], **kw)

    section_s = style("section", fontSize=9, fontName="Helvetica-Bold", spaceBefore=10, spaceAfter=3)
    note_s    = style("note",    fontSize=7, textColor=colors.gray, spaceAfter=6)
    footer_s  = style("footer",  fontSize=7, textColor=colors.gray, alignment=TA_CENTER)

    def table(data, col_widths, header_row=True, zebra=True):
        t = Table(data, colWidths=col_widths)
        cmds = [
            ("FONTSIZE",     (0, 0), (-1, -1), 8),
            ("ALIGN",        (0, 0), (-1, -1), "CENTER"),
            ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
            ("BOX",          (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ("INNERGRID",    (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ("TOPPADDING",   (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
        ]
        if header_row:
            cmds += [
                ("BACKGROUND", (0, 0), (-1, 0), BLUE_LIGHT),
                ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
            ]
        if zebra:
            cmds.append(("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, GRAY_LIGHT]))
        t.setStyle(TableStyle(cmds))
        return t

    story = []

    # ── HEADER ──────────────────────────────────────────────────────────
    hdr = Table([["AlsoEnergy", today_str]], colWidths=[5.0 * inch, 2.2 * inch])
    hdr.setStyle(TableStyle([
        ("FONTNAME",  (0, 0), (0, 0), "Helvetica-Bold"),
        ("FONTSIZE",  (0, 0), (0, 0), 14),
        ("TEXTCOLOR", (0, 0), (0, 0), BLUE_DARK),
        ("FONTSIZE",  (1, 0), (1, 0), 9),
        ("ALIGN",     (1, 0), (1, 0), "RIGHT"),
        ("VALIGN",    (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(hdr)
    story.append(Spacer(1, 0.08 * inch))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.lightgrey))
    story.append(Spacer(1, 0.08 * inch))

    # ── TITLE ────────────────────────────────────────────────────────────
    story.append(Paragraph("Site Validation Report",
        style("title", fontSize=18, fontName="Helvetica-Bold",
              alignment=TA_CENTER, backColor=GRAY_LIGHT, spaceAfter=4)))

    addr   = site.get("address", {})
    addr1  = addr.get("address1", "")
    city   = f"{addr.get('city','')}, {addr.get('stateProvince','')} {addr.get('postalCode','')}".strip(", ")
    story.append(Paragraph(site.get("name", ""), style("sname", fontSize=13,
                 fontName="Helvetica-Bold", alignment=TA_CENTER, spaceAfter=2)))
    story.append(Paragraph(f"{addr1}<br/>{city}",
                 style("saddr", fontSize=9, alignment=TA_CENTER, spaceAfter=8)))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.lightgrey))
    story.append(Spacer(1, 0.1 * inch))

    # ── SITE ─────────────────────────────────────────────────────────────
    story.append(Paragraph("SITE", section_s))
    ac  = site.get("capacityAc", kpi.get("systemSize"))
    dc  = site.get("capacityDc", kpi.get("dCsize"))
    vdd = _date_str(site.get("validDataDate", ""))
    story.append(table(
        [["AC System Size", "DC System Size", "Valid Data Date"],
         [f"{int(ac):,}" if ac else "—", f"{int(dc):,}" if dc else "—", vdd]],
        [2.4 * inch] * 3,
    ))
    story.append(Spacer(1, 0.12 * inch))

    # ── PRODUCTION HIERARCHY ─────────────────────────────────────────────
    story.append(Paragraph("PRODUCTION HIERARCHY", section_s))
    n_inv, n_str = hw_counts
    if n_inv == 0:
        n_inv = int(kpi.get("totalInverters", 0))
    story.append(table(
        [["Inverters", "Strings", "Modules"],
         [f"{n_inv:,}", f"{n_str:,}" if n_str else "—", "—"]],
        [2.4 * inch] * 3,
    ))
    story.append(Spacer(1, 0.12 * inch))

    # ── RULE TOOL RESULTS ────────────────────────────────────────────────
    story.append(Paragraph("RULE TOOL RESULTS", section_s))

    by_id = {r["id"]: r for r in rules.get("results", []) if r.get("show", True)}
    rows  = [["Category", "Rule", "Result", "Success %"]]
    for cat in DISPLAY_CATEGORIES:
        cat_items = [(rid, info) for rid, info in RULE_MAP.items()
                     if info[1] == cat and rid in by_id]
        for i, (rid, (dname, _)) in enumerate(cat_items):
            res    = by_id[rid]
            rc     = res.get("result", 1)
            label  = RESULT_LABEL.get(rc, "—")
            succ   = res.get("success")
            rows.append([cat if i == 0 else "", dname, label,
                         f"{succ:.0f}" if succ is not None else "—"])

    rt = Table(rows, colWidths=[1.3 * inch, 2.6 * inch, 1.0 * inch, 1.3 * inch], repeatRows=1)
    cmds = [
        ("BACKGROUND",   (0, 0), (-1, 0), BLUE_LIGHT),
        ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",     (0, 0), (-1, -1), 8),
        ("ALIGN",        (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        ("BOX",          (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ("INNERGRID",    (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ("TOPPADDING",   (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [colors.white, GRAY_LIGHT]),
        ("ALIGN",        (1, 0), (1, -1), "LEFT"),
    ]
    for ri, row in enumerate(rows[1:], 1):
        lbl = row[2]
        c   = GREEN if lbl == "Pass" else (RED if lbl == "Fail" else ORANGE if lbl == "Warning" else colors.gray)
        cmds += [("TEXTCOLOR", (2, ri), (2, ri), c),
                 ("FONTNAME",  (2, ri), (2, ri), "Helvetica-Bold")]
    rt.setStyle(TableStyle(cmds))
    story.append(rt)

    # ── PAGE 2: PERFORMANCE ──────────────────────────────────────────────
    story.append(PageBreak())
    story.append(Paragraph("PERFORMANCE", section_s))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.lightgrey))
    story.append(Spacer(1, 0.08 * inch))

    prod_img = Image(chart_production(kpi), width=6.2 * inch, height=2.7 * inch)
    story.append(prod_img)
    story.append(Spacer(1, 0.08 * inch))

    yest    = kpi.get("yesterday", 0)
    yest_e  = kpi.get("yesterdayEst", 0)
    yest_p  = kpi.get("yesterdayPct", 0)
    story.append(table(
        [["Total Production", "Expected Production*", "Energy Ratio"],
         [f"{int(yest):,} kWh", f"{int(yest_e):,} kWh", f"{yest_p:.0f} %"]],
        [2.4 * inch] * 3,
    ))
    story.append(Spacer(1, 0.05 * inch))
    story.append(Paragraph(
        "*Expected production is based on Stem's PV model and weather data.", note_s))

    story.append(Paragraph("Inverter Energy Ratio*", section_s))
    story.append(Image(chart_energy_ratio(kpi), width=5.5 * inch, height=1.8 * inch))
    story.append(Spacer(1, 0.05 * inch))
    story.append(Paragraph(
        "*Inverter Energy Ratio is based on Stem's PV model and weather data.", note_s))

    # ── PAGE 3: RULE TOOL INFORMATION ────────────────────────────────────
    story.append(PageBreak())
    story.append(Paragraph("RULE TOOL INFORMATION", section_s))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.lightgrey))
    story.append(Spacer(1, 0.08 * inch))

    info_rows = [[name + ":", desc] for name, desc in RULE_DESCRIPTIONS.items()]
    it = Table(info_rows, colWidths=[2.0 * inch, 5.2 * inch])
    it.setStyle(TableStyle([
        ("FONTNAME",      (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1), 8),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW",     (0, 0), (-1, -2), 0.25, colors.lightgrey),
        ("ALIGN",         (1, 0), (1, -1), "LEFT"),
    ]))
    story.append(it)

    story.append(Spacer(1, 0.3 * inch))
    story.append(Paragraph("Rule Tool checks the past 24 hours for pass/failure", footer_s))
    story.append(Paragraph(
        "View the complete rule tool checklist and other site information via Powertrack: apps.alsoenergy.com",
        footer_s))

    doc.build(story)


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Generate Site Validation Report PDFs")
    grp = ap.add_mutually_exclusive_group(required=True)
    grp.add_argument("--site", help="site key, e.g. S65787")
    grp.add_argument("--all",  action="store_true", help="all portfolio sites")
    ap.add_argument("--out",   default=".", help="output directory")
    ap.add_argument("--days",  type=int, default=7, help="KPI look-back days (default 7)")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    session = get_session()

    if args.all:
        r = session.get(f"{API_BASE}/view/portfolio/{PORTFOLIO}", timeout=20)
        r.raise_for_status()
        sites = [s for s in r.json().get("sites", []) if s["key"] not in EXCLUDE]
    else:
        sites = [{"key": args.site, "name": args.site}]

    print(f"Generating {len(sites)} report(s) -> {out_dir}/")

    for i, s in enumerate(sites, 1):
        sk = s["key"]
        sn = s.get("name", sk)
        print(f"  [{i:2}/{len(sites)}] {sk} {sn}...", end=" ", flush=True)
        try:
            detail = fetch_site(session, sk)
            rules  = fetch_rules(session, sk)
            hw     = fetch_hardware(session, sk)
            kpi    = fetch_kpi(session, sk, args.days)
            counts = count_hardware(hw)
            real_name = detail.get("name", sn)
            fname  = f"SiteValidationReport_{sk}_{real_name.replace('/', '-').replace(' ', '_')}.pdf"
            build_pdf(detail, rules, kpi, counts, out_dir / fname)
            print(f"OK")
        except Exception as e:
            print(f"FAILED: {e}")
        if i < len(sites):
            time.sleep(0.4)

    print("Done.")


if __name__ == "__main__":
    main()
