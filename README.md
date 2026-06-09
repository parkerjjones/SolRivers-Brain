# SolRiver Energy Monitoring System

Real-time monitoring and alert analysis for 35 solar installations across SolRiver Capital's portfolio.

## Quick Links

- **New to this project?** → Read [START_HERE.md](START_HERE.md)
- **Claude instances?** → Read [CLAUDE.md](CLAUDE.md)
- **Technical details?** → See [SYSTEM_OVERVIEW.md](SYSTEM_OVERVIEW.md)
- **What can go wrong?** → Check [FAILURE_ROOT_CAUSES.md](FAILURE_ROOT_CAUSES.md)
- **How auth works?** → Review [AUTHENTICATION_AND_API.md](AUTHENTICATION_AND_API.md)

## What This Does

Pulls data from AlsoEnergy PowerTrack API and loads it into a local PostgreSQL database for analysis:

1. **Site Overview** — 35 solar installations, current power output, capacity, contracts
2. **Hardware Inventory** — All inverters, meters, sensors, modems, dataloggers
3. **Alert History** — Operational faults, warnings, anomalies (with root cause analysis)
4. **ML Analysis** — Clustering alerts by pattern, correlation detection

## Scripts Overview

| Script | Purpose | Input | Output |
|--------|---------|-------|--------|
| `ae_sites_loader.py` | Portfolio overview + live power | Auth | `ae_sites.xlsx` |
| `ae_hardware_loader.py` | Device inventory | Auth | `ae_hardware.xlsx` |
| `ae_alert_loader.py` | Alert history → DB | Auth + DB | PostgreSQL + Excel |
| `ae_ml_analysis.py` | Alert clustering | DB | `ae_analysis.xlsx` |
| `ae_ai_summaries.py` | Raw AI summaries | Auth | `ae_ai_summaries.xlsx` |
| `ae_summaries_analyzer.py` | Parse health summaries | Auth | Console output |
| `ae_schema_explorer.py` | Debug API structure | Auth | Console output |
| `ae_ruleresults_loader.py` | Rule engine results | Auth + DB | PostgreSQL |

## Getting Started

### 1. Install
```bash
pip install -r requirements.txt
```

### 2. Authenticate
- Open https://apps.alsoenergy.com → PowerTrack dashboard
- Capture cURL from Network tab
- Save to `alsoenergy_curl.txt`

### 3. Run
```bash
python ae_sites_loader.py --output ae_sites.xlsx
```

See [START_HERE.md](START_HERE.md) for detailed walkthrough.

## Key Features

✅ **Idempotent** — Run multiple times, no duplicate data  
✅ **Incremental** — `--since` flag for fast updates  
✅ **Excel export** — All data available in spreadsheets  
✅ **ML-ready** — TF-IDF clustering, Pearson correlations  
✅ **Root cause analysis** — 8 failure categories documented  
✅ **Timezone-aware** — API returns UTC, data converted to US/Eastern  

## Architecture

```
AlsoEnergy API
    ↓
  cURL session (browser auth tokens)
    ↓
Python scripts (parse + normalize)
    ↓
PostgreSQL (solriver database)
    ↓
Excel exports (for inspection)
```

## Known Limitations

⚠️ **Manual auth refresh** — Tokens expire every 12–24h  
⚠️ **No OAuth2** — AlsoEnergy doesn't offer API keys yet  
⚠️ **Rate limiting** — 0.4–1.5s sleep between calls  
⚠️ **No predictive ML** — Currently clustering only (no forecast)  
⚠️ **No contract alerting** — Must manually scan expiry dates  

See [FAILURE_ROOT_CAUSES.md](FAILURE_ROOT_CAUSES.md#gap-analysis-whats-not-being-monitored) for gaps.

## Database Setup

If using alert loaders:
```bash
# Create database
createdb -h localhost -U postgres solriver

# Verify
psql -h localhost -U postgres -d solriver -c "SELECT 1;"
```

Or set environment variable:
```bash
export DB_DSN="host=localhost port=5432 dbname=solriver user=postgres password=postgres"
```

## Troubleshooting

| Error | Solution |
|-------|----------|
| `ModuleNotFoundError: psycopg2` | `pip install -r requirements.txt` |
| `FileNotFoundError: alsoenergy_curl.txt` | Create auth file (see [START_HERE.md](START_HERE.md)) |
| `HTTP 401/403` | Token expired → get fresh cURL |
| `psycopg2.OperationalError` | PostgreSQL not running; install or skip DB-only scripts |

See [CLAUDE.md](CLAUDE.md#5-troubleshooting) for more.

## Security

⚠️ **DO NOT COMMIT**:
- `alsoenergy_curl.txt` (contains session tokens)
- `.env` (database credentials)

✅ **Already in .gitignore**:
- `*.session`
- `*.log`
- `*.xlsx` (generated exports)

See [AUTHENTICATION_AND_API.md](AUTHENTICATION_AND_API.md#security-concerns) for details.

## For Claude Instances

When assigned to this project:

1. **Read**: [CLAUDE.md](CLAUDE.md) (complete setup guide)
2. **Install**: `pip install -r requirements.txt`
3. **Authenticate**: Ask user for `alsoenergy_curl.txt` from browser
4. **Test**: `python ae_sites_loader.py --output ae_sites.xlsx`
5. **Context**: Review [FAILURE_ROOT_CAUSES.md](FAILURE_ROOT_CAUSES.md) for domain knowledge

## Project Status

**Current Version**: 2026-06-08  
**Python**: 3.8+  
**Dependencies**: psycopg2, requests, pandas, scikit-learn, openpyxl  
**API**: AlsoEnergy PowerTrack (reverse-engineered)  
**Portfolio**: C12941 (35 sites, US/Eastern timezone)  

## Next Steps

1. **Contract monitoring** — Add weekly scan for expiry dates
2. **Token auto-refresh** — Reduce manual cURL copying
3. **Anomaly detection** — ARIMA/Prophet for forecasting
4. **Automation** — Scheduled runs with email alerts
5. **Web UI** — Dashboard for live monitoring

---

**For questions**, check the documentation files listed at the top.
