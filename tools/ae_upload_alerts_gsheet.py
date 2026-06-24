"""
ae_upload_alerts_gsheet.py
Upload the last 20 alerts from ae_alerts.xlsx to a Google Sheet on Drive.

FIRST-TIME SETUP:
  1. Go to https://console.cloud.google.com/
  2. Select/create a project
  3. Enable: Google Sheets API  +  Google Drive API
  4. Go to APIs & Services > Credentials > Create Credentials > OAuth 2.0 Client ID
  5. Application type: Desktop App  (name it anything)
  6. Download JSON  ->  save as  google_credentials.json  in this folder
  Then re-run this script. A browser window will open once for consent; after that it runs silently.
"""

import os
import sys
import pandas as pd
import gspread
from gspread.exceptions import SpreadsheetNotFound
from gspread_formatting import (
    CellFormat, Color, TextFormat, format_cell_range,
    set_frozen, set_column_width
)

CREDENTIALS_FILE = os.path.join(os.path.dirname(__file__), "google_credentials.json")
SHEET_TITLE = "SolRiver Alert Tracker"
WHO = "parker@solrivercapital.com"
ALERTS_FILE = os.path.join(os.path.dirname(__file__), "ae_alerts.xlsx")

ASSET_MAP = {
    "INV": "Inverter",
    "MTR": "Production Meter",
    "MET": "Weather Station",
    "TKR": "Tracker",
    "DA":  "UPS",
    "UNK": "Unknown",
}

EVENT_SHORTNAMES = {
    "device communication":      "Comm Error",
    "gamechange tracker alert":  "Tracker Alert",
    "fault alert":               "Fault",
    "power meter check":         "Meter Check",
    "offline":                   "Offline",
    "energy meter":              "Meter Issue",
    "battery":                   "Battery",
    "quint ups":                 "UPS Alert",
    "open phase":                "Open Phase",
    "external fan":              "Fan Damaged",
}

HEADERS = [
    "Timestamp",
    "Who",
    "Project Name",
    "Equipment",
    "SubPart",
    "Description of Issue\n(In 2 words or less)",
    "Does the issue cause\nProduction Loss?\n(1 - yes, 0 - no)",
    "Quantity",
    "Equipment ID",
    "Alert",
    "Comment",
    "Category",
    "Start Date",
    "Start Time\n(If available)",
    "End Date",
    "End time\n(If available)",
    "Action Taken",
]


def shorten(event_type: str) -> str:
    lower = event_type.lower()
    for key, label in EVENT_SHORTNAMES.items():
        if key in lower:
            return label
    words = event_type.replace(" -", " ").split()
    return " ".join(words[:2]) if len(words) >= 2 else event_type


def fmt_date(ts) -> str:
    if pd.isna(ts):
        return ""
    return ts.strftime("%#m/%#d/%Y")   # Windows: %# strips leading zeros


def fmt_time(ts) -> str:
    if pd.isna(ts):
        return ""
    return ts.strftime("%H:%M")


def build_rows(df: pd.DataFrame) -> list[list]:
    rows = []
    for _, r in df.iterrows():
        ts = r["alert_start"]
        ts_str = (ts.strftime("%#m/%#d/%Y %H:%M") if pd.notna(ts) else "")
        desc = r["description"] if pd.notna(r["description"]) else ""
        rows.append([
            ts_str,
            WHO,
            r["site_name"],
            ASSET_MAP.get(r["asset_code"], r["asset_code"]),
            "",                                          # SubPart (manual)
            shorten(r["event_type_name"]),
            1 if r["impact"] > 0 else 0,
            1,                                           # Quantity
            int(r["alert_id"]),
            r["event_type_name"],
            desc[:120].replace("\t", " "),
            "",                                          # Category (manual)
            fmt_date(r["alert_start"]),
            fmt_time(r["alert_start"]),
            fmt_date(r["alert_end"]),
            fmt_time(r["alert_end"]),
            "",                                          # Action Taken (manual)
        ])
    return rows


def apply_formatting(ws, num_data_rows: int):
    try:
        from gspread_formatting import (
            CellFormat, Color, TextFormat, format_cell_range,
            set_frozen, set_column_width
        )
    except ImportError:
        print("  (skipping styling — run: pip install gspread-formatting)")
        return

    # Purple header background + white bold text
    header_fmt = CellFormat(
        backgroundColor=Color(0.44, 0.19, 0.63),   # ~#70308E
        textFormat=TextFormat(bold=True, foregroundColor=Color(1, 1, 1), fontSize=9),
        wrapStrategy="WRAP",
        verticalAlignment="MIDDLE",
    )
    format_cell_range(ws, "A1:Q1", header_fmt)

    # Freeze header row
    set_frozen(ws, rows=1)

    # Light alternating row color for data rows
    light = CellFormat(backgroundColor=Color(0.95, 0.93, 0.97))
    for i in range(2, num_data_rows + 2, 2):
        format_cell_range(ws, f"A{i}:Q{i}", light)

    # Column widths (pixels)
    col_widths = {
        "A": 130, "B": 185, "C": 160, "D": 120, "E": 80,
        "F": 110, "G": 80,  "H": 70,  "I": 100, "J": 200,
        "K": 220, "L": 90,  "M": 90,  "N": 80,  "O": 80,
        "P": 80,  "Q": 110,
    }
    for col, width in col_widths.items():
        set_column_width(ws, col, width)


def main():
    # --- Credentials check ---
    if not os.path.exists(CREDENTIALS_FILE):
        print("=" * 60)
        print("ERROR: google_credentials.json not found.")
        print()
        print("One-time setup (5 min):")
        print("  1. Visit https://console.cloud.google.com/")
        print("  2. Create/select a project")
        print("  3. Enable 'Google Sheets API' and 'Google Drive API'")
        print("  4. APIs & Services > Credentials > Create Credentials")
        print("     > OAuth 2.0 Client ID > Desktop App")
        print("  5. Download JSON  ->  rename to 'google_credentials.json'")
        print("     and place it in this folder, then re-run.")
        print("=" * 60)
        sys.exit(1)

    # --- Load and sort alerts ---
    print(f"Reading {ALERTS_FILE} ...")
    df = pd.read_excel(ALERTS_FILE, parse_dates=["alert_start", "alert_end"])
    df = df.sort_values("alert_start", ascending=False).head(20)
    print(f"  Using {len(df)} most recent alerts.")

    # --- Authenticate ---
    print("Authenticating with Google (browser may open for first-time consent) ...")
    gc = gspread.oauth(credentials_filename=CREDENTIALS_FILE)

    # --- Create or reuse spreadsheet ---
    try:
        sh = gc.open(SHEET_TITLE)
        print(f"  Found existing sheet: '{SHEET_TITLE}'")
    except SpreadsheetNotFound:
        sh = gc.create(SHEET_TITLE)
        print(f"  Created new sheet: '{SHEET_TITLE}'")

    ws = sh.sheet1
    ws.clear()

    # --- Write data ---
    data_rows = build_rows(df)
    ws.update([HEADERS] + data_rows, value_input_option="USER_ENTERED")
    print(f"  Wrote {len(data_rows)} rows.")

    # --- Styling ---
    print("  Applying formatting ...")
    apply_formatting(ws, len(data_rows))

    # --- Share with user (if newly created) ---
    sh.share(WHO, perm_type="user", role="writer", notify=False)

    print()
    print("=" * 60)
    print(f"Done!  Open your sheet here:")
    print(f"  {sh.url}")
    print("=" * 60)


if __name__ == "__main__":
    main()
