# CLAUDE.md — SolRiver Monitoring System Setup Guide

**For: Any Claude instance assigned to this project**

This guide ensures you can run all scripts without errors. Follow in order.

---

## 1. Install Dependencies

```bash
pip install psycopg2-binary requests openpyxl pandas scikit-learn --break-system-packages
```

Verify:
```bash
python -c "import psycopg2, requests, openpyxl, pandas, sklearn; print('✓ All imports OK')"
```

---

## 2. Set Up Authentication

### What You Need
- Access to **AlsoEnergy PowerTrack dashboard**
- Ability to extract cURL from browser Network tab

### Steps

1. **Open browser and log into AlsoEnergy**
   - Go to https://apps.alsoenergy.com
   - Navigate to PowerTrack dashboard

2. **Capture the authenticated cURL**
   - Open browser **Network tab** (F12 → Network)
   - Look for a request named `alerthistory` or `/api/view/`
   - Right-click → **Copy as cURL (bash)**
   - **DO NOT include `curl` prefix; copy everything after it**

3. **Create/Update `alsoenergy_curl.txt`**
   - Paste the cURL into a new file named `alsoenergy_curl.txt` in the project root
   - Example format:
     ```
     -H "ae_s: <session_id>" \
     -H "ae_v: <version>" \
     -H "User-Agent: Mozilla/5.0..." \
     -b "AspNet.Cookies=...; .AspNet.CookiesC1=...; cf_clearance=..." \
     "https://apps.alsoenergy.com/api/view/alerthistory"
     ```

4. **Verify it's valid**
   ```bash
   python ae_alert_loader.py --probe --key C12941
   ```
   - If you see API response (no error): ✓ Auth works
   - If 401/403: cURL expired → get a fresh copy

### Token Lifecycle
- **Valid for**: 12–24 hours after last use
- **When to refresh**: Any 401/403 error → repeat steps 1–3
- **Why**: AlsoEnergy's session tokens expire automatically

---

## 3. Configure Database (If Running Alert Loaders)

### Prerequisites
- PostgreSQL installed and running on `localhost:5432`
- Database `solriver` created
- User `postgres` with access

### Quick Test
```bash
psql -h localhost -U postgres -d solriver -c "SELECT 1;"
```

If this fails, you need to:
1. Install PostgreSQL (or skip and use API-only scripts)
2. Create the database:
   ```bash
   createdb -h localhost -U postgres solriver
   ```

### Set Environment Variable (Optional but Recommended)
Instead of hardcoding credentials, use an env var:

```bash
export DB_DSN="host=localhost port=5432 dbname=solriver user=postgres password=postgres"
```

Scripts will auto-detect this and use it. If not set, they fall back to the hardcoded default.

---

## 4. Run Scripts (Choose Your Path)

### Path A: API Only (No Database Needed)
Perfect for initial exploration and Excel exports.

```bash
# Fetch site overview (35 solar sites, current power output)
python ae_sites_loader.py --output ae_sites.xlsx

# Fetch hardware inventory (inverters, meters, sensors per site)
python ae_hardware_loader.py --output ae_hardware.xlsx

# Decode AI summaries (health status, production metrics)
python ae_ai_summaries.py --output ae_summaries.xlsx
```

**Result**: 3 Excel files with live data, no database required.

### Path B: Full Pipeline (Database Required)
Includes alert history, ML analysis, and pattern detection.

```bash
# 1. Load alert history from date range
python ae_alert_loader.py --from 2025-01-01 --to 2026-06-08

# 2. Run ML clustering on alerts
python ae_ml_analysis.py

# 3. Export to Excel (for inspection)
python ae_alert_loader.py --from 2025-01-01 --to 2026-06-08 --excel ae_alerts.xlsx
```

**Result**: PostgreSQL `ae_alerts` table + Excel exports with clustering analysis.

### Path C: Probe API Schema (Debugging)
```bash
python ae_schema_explorer.py --key C12941
python ae_ruleresults_loader.py --key C12941
```

---

## 5. Troubleshooting

### Error: `ModuleNotFoundError: No module named 'psycopg2'`
```bash
→ Install: pip install psycopg2-binary --break-system-packages
```

### Error: `FileNotFoundError: alsoenergy_curl.txt`
```bash
→ Create the file (see step 2)
→ Or run API-only scripts (Path A)
```

### Error: `HTTP 401 Unauthorized` or `403 Forbidden`
```bash
→ Auth token expired
→ Copy fresh cURL from browser Network tab (step 2.2)
→ Paste into alsoenergy_curl.txt
→ Re-run script
```

### Error: `psycopg2.OperationalError: could not connect to server`
```bash
→ PostgreSQL not running or wrong host/port
→ If you don't need the database:
   - Use Path A (API only)
   - Or install PostgreSQL locally
```

### Error: `Database 'solriver' does not exist`
```bash
→ Create it:
   createdb -h localhost -U postgres solriver
→ Then scripts will auto-create tables on first run
```

### Error: `Traceback ... in ae_ml_analysis.py`
```bash
→ Run ae_alert_loader.py first (to populate data)
→ ML analysis requires alert records in the database
```

---

## 6. Common Tasks

### Refresh All Data
```bash
# Sites + Hardware (no DB needed)
python ae_sites_loader.py --output ae_sites.xlsx
python ae_hardware_loader.py --output ae_hardware.xlsx

# Alerts + Analysis (with DB)
python ae_alert_loader.py --from 2026-01-01 --to 2026-06-08
python ae_ml_analysis.py

# Export everything to Excel
python ae_alert_loader.py --from 2026-01-01 --to 2026-06-08 --excel ae_alerts.xlsx
```

### Check a Specific Site's Health
```bash
python ae_summaries_analyzer.py --key C12941  # Portfolio-level summary
```

### See What's Currently Down
```bash
python ae_sites_loader.py --output ae_sites.xlsx
# Open ae_sites.xlsx → "Live Power" sheet
# Look for power < 50% expected (red flags)
```

### Find Problem Patterns (Requires DB)
```bash
python ae_alert_loader.py --from 2025-01-01 --to 2026-06-08
python ae_ml_analysis.py
# Open ae_analysis.xlsx → "Cluster Summary" sheet
# See grouped alert types
```

---

## 7. What Each Script Does

| Script | Requires | Output | Purpose |
|--------|----------|--------|---------|
| `ae_sites_loader.py` | Auth | `ae_sites.xlsx` | Portfolio overview + live power |
| `ae_hardware_loader.py` | Auth | `ae_hardware.xlsx` | Device inventory per site |
| `ae_alert_loader.py` | Auth + DB | PostgreSQL + Excel | Ingest alert history |
| `ae_ml_analysis.py` | DB (populated) | `ae_analysis.xlsx` | Cluster alerts by pattern |
| `ae_ai_summaries.py` | Auth | `ae_ai_summaries.xlsx` | Raw AI health summaries |
| `ae_summaries_analyzer.py` | Auth | (console) | Parse summaries for metrics |
| `ae_schema_explorer.py` | Auth | (console) | Debug API response structure |
| `ae_ruleresults_loader.py` | Auth + DB | PostgreSQL | Load rule engine results |

---

## 8. Environment Variables Reference

| Variable | Purpose | Example |
|----------|---------|---------|
| `DB_DSN` | PostgreSQL connection (optional) | `host=localhost port=5432 dbname=solriver user=postgres password=postgres` |
| `PORTFOLIO_KEY` | Override default portfolio (optional) | `C12941` (default) |

Set before running:
```bash
export DB_DSN="host=localhost port=5432 dbname=solriver user=postgres password=postgres"
python ae_alert_loader.py --from 2025-01-01 --to 2026-06-08
```

---

## 9. Security Notes

⚠️ **DO NOT COMMIT** these files:
- `alsoenergy_curl.txt` (contains session tokens)
- Database credentials in environment

✓ **Already in .gitignore** (verify):
```bash
grep -E "alsoenergy_curl|DB_DSN|session|password" .gitignore
```

---

## 10. Next Steps for Claude

When assigned to this project:

1. **First run**: 
   ```bash
   pip install psycopg2-binary requests openpyxl pandas scikit-learn --break-system-packages
   python ae_sites_loader.py --output ae_sites.xlsx
   ```

2. **If auth fails**, ask user to provide fresh cURL from browser

3. **If DB connection fails**, check PostgreSQL is running or skip to API-only tasks

4. **Check FAILURE_ROOT_CAUSES.md** and SYSTEM_OVERVIEW.md for context on what problems to look for

5. **Run the full pipeline** only if both auth and DB are verified

---

**Last Updated**: 2026-06-08  
**System**: AlsoEnergy PowerTrack API, 35 solar sites, US/Eastern timezone  
**Portfolio**: C12941
