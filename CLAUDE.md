# CLAUDE.md — SolRiver Brain: AlsoEnergy Data Platform

**For: Any Claude instance (including Claude Code / cowork) working on this project**

---

## CRITICAL: Authentication — No cURL Required

All scripts use `ae_auth.py` which handles sessions automatically.

```bash
python ae_auth.py          # test auth — run this first
```

**How it works:**
1. `ae_auth.py` saves a session to `ae_session.json` after the first successful auth
2. Every subsequent script reuses `ae_session.json` — no cURL needed
3. Sessions last **hours to days** (ASP.NET Identity cookies, not 20-min JWTs)
4. When the session genuinely expires, you get a clear error message

**Only paste a new cURL if you see:**
```
Authentication failed — Your cURL cookies have expired.
```

**To get a fresh cURL (rare — only when truly expired):**
1. Open Chrome/Edge, go to https://apps.alsoenergy.com/powertrack
2. F12 → Network tab → click any request
3. Right-click → **Copy as cURL (bash)**
4. Paste into `alsoenergy_curl.txt` (overwrite the whole file)
5. Run `python ae_auth.py` to verify and save the new session

---

## Install Dependencies

```bash
pip install -r requirements.txt
```

Or individually:
```bash
pip install requests openpyxl pandas scikit-learn matplotlib seaborn numpy
```

---

## Scripts and What They Produce

| Script | Output | Description |
|---|---|---|
| `ae_auth.py` | `ae_session.json` | Session manager — run first |
| `ae_alert_loader.py` | `ae_alerts.xlsx` | 482+ alerts with types, duration, resolution |
| `ae_hardware_loader.py` | `ae_hardware.xlsx` | 1,311 devices across 34 sites |
| `ae_sites_loader.py` | `ae_sites.xlsx` | 35 sites with capacity, location, live power |
| `ae_ruleresults_loader.py` | `ae_ruleresults.xlsx` | Diagnostic check results per site |
| `ae_ai_summaries.py` | `ae_ai_summaries.xlsx` | AI-generated natural language health summaries |
| `ae_ai_deep_read.py` | `ae_ai_deep.xlsx`, `ae_ai_deep.txt` | Deep extraction from AI summaries |
| `ae_summaries_analyzer.py` | `ae_summaries_deep.xlsx` | NLP analysis + embedded chart URLs |
| `ae_ml_analysis.py` | `ae_analysis.xlsx` | TF-IDF clustering + correlation analysis |
| `ae_master_dashboard.py` | `ae_master.xlsx` | Portfolio health dashboard joining all sources |
| `ae_schema_explorer.py` | `ae_schema.xlsx` | API endpoint discovery + DB schema design |

---

## Quick Start (Run Everything Fresh)

```bash
python ae_auth.py                                           # verify session
python ae_alert_loader.py --from 2026-01-01 --to 2026-06-09 --excel-only --excel ae_alerts.xlsx
python ae_hardware_loader.py
python ae_sites_loader.py
python ae_ruleresults_loader.py
python ae_ai_summaries.py
python ae_master_dashboard.py
```

---

## Portfolio Structure

- **Portfolio key:** `C12941` (35 sites)
- **Second portfolio:** `C47197` (1 site: C & B Graham Energy / S65918)
- **Sites:** School districts, commercial solar, agricultural — all in Ohio/Southeast US
- **Device types:** Inverters (fc=1), Production Meters (fc=2), Weather Stations (fc=5), Trackers (fc=24)

---

## Known Working API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `GET /api/view/portfolio/{key}` | GET | 35 sites + live power readings |
| `GET /api/view/site/{siteKey}` | GET | Full site detail (lat/lon, capacity, contracts) |
| `GET /api/scriptsite/{siteKey}?lastChanged=1900-01-01T00:00:00.000Z` | GET | Hardware inventory per site |
| `POST /api/view/alerthistory` | POST | Alert history `{"key","from","to","offset"}` |
| `GET /api/ruleresults/{key}?lastChanged=1900-01-01T00:00:00.000Z&mergeHash=` | GET | Diagnostic check results |
| `GET /api/ai-site-summary?siteId={key}&lang=en-US` | GET (SSE) | AI natural language site summary |
| `POST /api/view/kpidashboard?lastChanged=...` | POST | KPI dashboard data |
| `POST /api/view/chart?lastChanged=...` | POST | Chart configurations |
| `POST /api/node?lastChanged=...` | POST | Site/hardware node hierarchy |

**Auth headers required on all requests:** `ae_s`, `ae_v` (static per account)

---

## Data Discoveries

- **h parameter in chart URLs:** functionCode numbers (`1*2*5*11` = inverter+meter+weather+generic)
- **c parameter in chart URLs:** field/column ID (6=KwAC, 79=KWHnet, 15=KW)
- **weatherCondition codes:** 1=Sunny, 2=Partly Cloudy, 3=Overcast, 5=Rain
- **Rule result codes:** 4=Pass, 3=Fail, 2=Warning, 1=N/A
- **Asset codes:** INV=Inverter, MTR=Meter, MET=Weather Station, UNK=Unknown

---

## Troubleshooting

| Error | Fix |
|---|---|
| `FileNotFoundError: alsoenergy_curl.txt` | Paste fresh cURL (see section above) |
| `HTTP 500 empty body` | Session expired — paste fresh cURL |
| `ModuleNotFoundError` | `pip install -r requirements.txt` |
| `HTTP 404 on S55935` | That site (Manuel Lawrence Dairy) is inactive in the API |
