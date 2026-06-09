# Installation Status — June 8, 2026

## Dependencies Installed ✓

```
✓ psycopg2-binary    (PostgreSQL connection)
✓ requests           (HTTP client)
✓ openpyxl           (Excel generation)
✓ pandas             (Data analysis)
✓ scikit-learn       (ML clustering + analysis)
```

All 8 scripts now import cleanly:
- `ae_sites_loader.py` ✓
- `ae_hardware_loader.py` ✓
- `ae_alert_loader.py` ✓
- `ae_ml_analysis.py` ✓
- `ae_ai_summaries.py` ✓
- `ae_summaries_analyzer.py` ✓
- `ae_schema_explorer.py` ✓
- `ae_ruleresults_loader.py` ✓

## Pre-Run Checklist

Before running scripts, verify:

### 1. Authentication (Required)
- [ ] `alsoenergy_curl.txt` exists and has valid session
  - Currently: **15 KB, 13 lines** (looks valid)
  - To refresh: Open browser → AlsoEnergy PowerTrack → Network tab → Right-click `alerthistory` request → Copy as cURL → Paste into file
  - Token expires: 12–24 hours after last use

### 2. Database (Required for ae_alert_loader.py)
- [ ] PostgreSQL running on `localhost:5432`
- [ ] Database `solriver` exists
- [ ] User `postgres` has access
- [ ] To test: `psql -h localhost -U postgres -d solriver -c "SELECT 1;"`

### 3. Environment (Optional but Recommended)
- [ ] Move DB credentials to env vars instead of hardcoding:
  ```bash
  export DB_DSN="host=localhost port=5432 dbname=solriver user=postgres password=postgres"
  ```

## Command Reference

### Quick Test (No DB needed)
```bash
# Fetch site overview only (Excel export)
python ae_sites_loader.py --output sites.xlsx

# Fetch hardware inventory only
python ae_hardware_loader.py --output hardware.xlsx
```

### Full Alerting Pipeline (Requires DB + Auth)
```bash
# 1. Load alerts from 2025-01-01 to today
python ae_alert_loader.py --from 2025-01-01 --to 2026-06-08

# 2. Analyze alert patterns (ML clustering)
python ae_ml_analysis.py

# 3. Export to Excel
python ae_alert_loader.py --from 2025-01-01 --to 2026-06-08 --excel alerts.xlsx
```

### Schema Exploration
```bash
# Probe API response structure
python ae_schema_explorer.py --key C12941

# Decode AI summaries
python ae_ai_summaries.py --key C12941
```

## Known Issues

| Issue | Workaround | Timeline |
|-------|-----------|----------|
| **Auth expires frequently** | Re-copy cURL when 401 occurs | Manual for now |
| **DB creds hardcoded** | Use env var override (`DB_DSN`) | Fix in next PR |
| **No contract expiry alerts** | Add weekly scan script | Implement this week |
| **No weather baseline** | Flag all underperformance alerts | Add ML model in 2 weeks |
| **Slow API throttle** | SLEEP=1.5s between calls (safe) | Monitor rate limits |

## Next Steps

1. **Verify DB connection**
   ```bash
   python -c "import psycopg2; conn = psycopg2.connect('host=localhost port=5432 dbname=solriver user=postgres password=postgres'); print('✓ DB OK')"
   ```

2. **Run sites loader** (no DB needed)
   ```bash
   python ae_sites_loader.py --output ae_sites.xlsx
   ```

3. **Check cURL validity** (no DB needed)
   ```bash
   python ae_alert_loader.py --probe --key C12941
   ```

4. **If auth fails**: Copy fresh cURL and retry

---

**Last Updated**: 2026-06-08  
**All Python imports**: Passing  
**Database**: Pending verification
