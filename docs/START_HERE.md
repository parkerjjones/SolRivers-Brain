# START HERE — SolRiver Monitoring System

Welcome! This guide will get you up and running in 5 minutes.

## Quick Start (3 Steps)

### Step 1: Install Dependencies
Choose your OS:

**Linux/Mac:**
```bash
./setup.sh
```

**Windows:**
```bash
setup.bat
```

Or manually:
```bash
pip install -r requirements.txt
```

### Step 2: Set Up Authentication
1. Open browser → https://apps.alsoenergy.com
2. Log in and go to **PowerTrack dashboard**
3. Press **F12** to open Network tab
4. Look for a request named `alerthistory` or `/api/view/`
5. Right-click → **Copy as cURL (bash)**
6. Create file: `alsoenergy_curl.txt`
7. Paste the entire cURL command (everything after `curl `)

**Example of what to paste** (without the `curl` prefix):
```
-H "ae_s: abc123..." \
-H "ae_v: 1.0" \
-b "AspNet.Cookies=xyz..." \
"https://apps.alsoenergy.com/api/view/alerthistory"
```

### Step 3: Run a Script
No database needed for this one:
```bash
python ae_sites_loader.py --output ae_sites.xlsx
```

If it works, you'll see: `Saved 35 rows to ae_sites.xlsx`

---

## What Happens Next?

### You get:
- ✓ **ae_sites.xlsx** — All 35 solar sites + current power output (red flags for underperformance)
- ✓ **ae_hardware.xlsx** — Inventory of inverters, meters, sensors, modems per site
- ✓ **ae_analysis.xlsx** — ML clustering of alert patterns (requires database)

### Files Created:
| File | Purpose | Requires DB? |
|------|---------|-------------|
| CLAUDE.md | Detailed setup for future Claude instances | No |
| setup.sh / setup.bat | Automated environment setup | No |
| requirements.txt | Python dependencies | No |
| .env.example | Configuration template | No |
| .gitignore | Protect credentials | No |

---

## Troubleshooting

### "ModuleNotFoundError: No module named 'psycopg2'"
```bash
→ Run: pip install -r requirements.txt
```

### "FileNotFoundError: alsoenergy_curl.txt"
```bash
→ You haven't created the auth file yet (see Step 2 above)
→ Or use API-only scripts that don't need it
```

### "HTTP 401 Unauthorized" or "403 Forbidden"
```bash
→ Your auth token expired (happens after 12-24h of inactivity)
→ Get a fresh cURL from browser (repeat Step 2.1-6)
→ Paste into alsoenergy_curl.txt
→ Try again
```

### "psycopg2.OperationalError: could not connect to server"
```bash
→ PostgreSQL not running or not installed
→ Option 1: Install PostgreSQL (createdb -h localhost -U postgres solriver)
→ Option 2: Use API-only scripts (they don't need the database)
```

---

## Common Tasks

### See Live Power Output (No DB needed)
```bash
python ae_sites_loader.py --output ae_sites.xlsx
# Open in Excel, go to "Live Power" sheet
# Red rows = power < 50% of expected
```

### See Hardware Inventory (No DB needed)
```bash
python ae_hardware_loader.py --output ae_hardware.xlsx
```

### Load Alert History (Requires PostgreSQL)
```bash
python ae_alert_loader.py --from 2025-01-01 --to 2026-06-08
```

### Analyze Alert Patterns (Requires PostgreSQL)
```bash
python ae_alert_loader.py --from 2025-01-01 --to 2026-06-08
python ae_ml_analysis.py
# Output: ae_analysis.xlsx with clusters and patterns
```

### Export Everything to Excel (No DB needed)
```bash
python ae_sites_loader.py --output ae_sites.xlsx
python ae_hardware_loader.py --output ae_hardware.xlsx
python ae_ai_summaries.py --output ae_summaries.xlsx
```

---

## What This System Does

**Portfolio**: 35 solar installations (SolRiver Capital)  
**API**: AlsoEnergy PowerTrack (reverse-engineered)  
**Data**: Site metadata, hardware inventory, alert history, ML analysis

### 8 Common Failure Modes Being Monitored:
1. **Communication failures** — Modem down, device offline
2. **Production underperformance** — Output < 50% expected
3. **Sensor failures** — Meter stuck, irradiance probe dirty
4. **Inverter trips** — String inverter, overvoltage, ground fault
5. **Contract expirations** — Monitoring or modem contracts end
6. **Datalogger offline** — Site goes completely dark
7. **Data integrity** — Missing fields, timestamp parsing
8. **Maintenance windows** — Planned shutdowns, grid curtailment

See **FAILURE_ROOT_CAUSES.md** for details.

---

## Documentation

- **CLAUDE.md** — Full setup guide for Claude instances (detailed)
- **SYSTEM_OVERVIEW.md** — Architecture, data flow, known issues
- **FAILURE_ROOT_CAUSES.md** — Root cause analysis (8 categories)
- **AUTHENTICATION_AND_API.md** — How auth works, troubleshooting
- **INSTALLATION_STATUS.md** — Current dependency status
- **.env.example** — Environment variable template

---

## For Future Claude Instances

When assigned to this project:

1. Read **CLAUDE.md** (complete setup instructions)
2. Run: `pip install -r requirements.txt`
3. Ask user for **alsoenergy_curl.txt** (browser auth capture)
4. Run: `python ae_sites_loader.py --output ae_sites.xlsx`
5. Check FAILURE_ROOT_CAUSES.md and SYSTEM_OVERVIEW.md for context

---

## Help!

If something breaks:
1. Check **CLAUDE.md** → Troubleshooting section
2. Look at the error message — scripts give helpful hints
3. Check if auth token expired (401/403) → get fresh cURL
4. Verify PostgreSQL is running (if using alert loader)
5. Confirm alsoenergy_curl.txt exists and is not empty

---

**Last Updated**: 2026-06-08  
**Python Version**: 3.8+  
**Dependencies**: Installed via `pip install -r requirements.txt`
