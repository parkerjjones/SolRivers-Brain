# SolRiver Energy Monitoring System Overview

## System Architecture

This is a solar energy site monitoring system built on **AlsoEnergy PowerTrack API** monitoring 35 solar installations across the portfolio.

### Portfolio Identifier
- **Portfolio Key**: C12941 (US Eastern Time)
- **Total Sites**: 35 solar installations
- **API Endpoint**: https://apps.alsoenergy.com/api

---

## Data Collection Pipeline

### 1. **ae_sites_loader.py** — Site Overview & Live Power
**Purpose**: Fetches complete site inventory and current power output

**What it collects:**
- Site metadata (names, addresses, coordinates, timezone)
- Current power output (kW) across all sites
- Capacity metrics (AC/DC kW ratings)
- Production estimates (daily/monthly kWh)
- Contract status (monitoring + cellular modem contracts)
- Commission dates and valid data ranges

**Output**: `ae_sites.xlsx` (4 sheets)
- Sites Overview — 35 sites with capacity, location, contracts
- Live Power — current output per site with red flags for underperformance (<50% expected)
- Contract Status — monitoring & modem contract expiry dates  
- Capacity Summary — AC/DC breakdown per site

**Authentication**: Reads cURL session from `alsoenergy_curl.txt`

**Performance**: 35 sites × 2 API calls (portfolio + detail) @ 0.4s throttle = ~30 seconds

---

### 2. **ae_hardware_loader.py** — Device Inventory
**Purpose**: Maps all physical hardware (inverters, meters, sensors, modems) per site

**What it collects:**
- Hardware key, name, function code (type), status
- Archive columns (telemetry fields each device logs)
- Device count per site

**Output**: `ae_hardware.xlsx` (4 sheets)
- Hardware Inventory — all devices across 35 sites
- Archive Columns — telemetry fields per device
- Site Summary — device counts by type (inverters, meters, weather stations, etc.)
- Function Code Map — reference table for device types

**Device Types (Function Codes)**:
- 1 = Inverter, 2 = Production Meter, 5 = Weather/Pyranometer
- 6 = DC Zone/String Monitor, 10 = Datalogger, 11 = Generic Module
- 14 = Camera, 19 = Consumption Meter, 24 = Tracker Controller
- 28 = String Inverter Group, 31 = Cellular Modem

---

### 3. **ae_alert_loader.py** — Alert History & Failures
**Purpose**: Ingests operational alerts (faults, warnings, anomalies) into local PostgreSQL + Excel

**What it captures:**
- Alert ID, site, hardware involved
- Event type (614 = Rule Tool Alert, etc.)
- Severity & impact metrics
- Resolution status & who resolved
- Alert duration (start → end → resolved)
- Timezone context

**Data Flow**:
1. Fetches from `/api/view/alerthistory` in 31-day windows
2. Normalizes timestamps (handles UTC 'Z' suffix)
3. Upserts into PostgreSQL (idempotent, merges updates)
4. Exports to `ae_alerts.xlsx`

**Database Schema**: `ae_alerts` table in `solriver` Postgres instance  
**Indexing**: By site_key, hardware_key, alert_start, event_type_code

**Auth Refresh**: When API returns 401/403, must re-copy fresh cURL from browser

---

### 4. **ae_ml_analysis.py** — Alert Pattern Analysis
**Purpose**: Applies NLP + ML to discover root causes and alert clustering

**Analysis Outputs** → `ae_analysis.xlsx`:
- **Cluster Summary** — TF-IDF KMeans (k=7) clusters of alert descriptions
- **Top Terms** — highest-TF-IDF words per cluster
- **Alerts by Site** — frequency, resolution rate (%), avg duration (hrs)
- **Alerts by Type** — same, ranked by volume
- **Hourly Pattern** — alert counts by hour-of-day (UTC)
- **Numeric Extraction** — values parsed from alert text (kW, %, temps, etc.)
- **Correlation Matrix** — Pearson correlations between numeric columns

**Key Metrics Extracted**:
- Duration (hours) = alert_end - alert_start
- Resolution rate = is_resolved count / total count per site
- Numeric tokens: severity, impact, capacity, temperatures, percentages

---

### 5. **ae_summaries_analyzer.py** — AI-Powered Site Health
**Purpose**: Extracts structured health status from AlsoEnergy's AI-generated summaries

**Health Classification**:
- **All Communicating**: All hardware responding normally
- **Partial Communication**: Some devices offline or intermittent
- **Production OK**: Tracking at or above expected
- **Production Low**: Below expected, underperforming
- **Alerts**: Current faults or anomalies
- **Weather Impact**: Conditions affecting output

**Extracted Values**:
- Production (kWh), Power (kW), % of Expected
- Performance Index scores
- Temperature readings (°F, °C)
- Percentage losses vs. expected
- Device names (inverter models, meter brands)
- Embedded chart URLs decoded into site/hardware/date

**Output**: `ae_summaries_deep.xlsx`  
**Urgency Scoring** (0-3): Critical → Severe → Alert → Normal

---

## Data Files & Their Meaning

| File | Size | Purpose | Frequency |
|------|------|---------|-----------|
| ae_sites.xlsx | Updated live | Site metadata + power output | On-demand |
| ae_hardware.xlsx | Updated live | Device inventory + telemetry schema | On-demand |
| ae_alerts.xlsx | Growing | All alerts from start date to today | Incremental upsert |
| ae_analysis.xlsx | Derived | NLP clustering + correlations | Post ae_alerts |
| ae_summaries_deep.xlsx | Updated live | AI health summaries per site | On-demand |
| ae_schema.xlsx | Reference | Raw API response schema | Manual doc |
| ae_ai_summaries.xlsx | Cached | Raw AI summary text from API | Optional cache |
| ae_ruleresults.xlsx | Data | Rule engine evaluation results | Data-driven |
| alsoenergy_curl.txt | Auth | Session tokens (DO NOT COMMIT) | Refresh when 401 |

---

## Known Issues & Why Mistakes Happen

### 1. **Authentication Expiration (401/403 errors)**
**Root Cause**: Session tokens in `alsoenergy_curl.txt` expire after inactivity  
**Impact**: Scripts halt; requires manual refresh from browser Network tab  
**Prevention**: Add token refresh logic or detect 401 → prompt for re-copy

### 2. **Data Gaps from Connection Loss**
**Root Cause**: Cellular modems lose network; hardware goes offline  
**Evidence**: 
- `hardware_status` field in inventory
- Cells with status=0 (Offline) or 8 (Partial) in live power sheet
- Unacknowledged alerts that linger weeks without resolution

**Impact**: Missing telemetry = blind spots in production analysis

### 3. **Alert Timestamp Ambiguity**
**Root Cause**: Multiple timestamp fields in alerts (alert_start, alert_end, resolved_time, trigger_time, last_changed)  
**Problem**: 
- ISO-8601 vs MM/DD/YYYY format mixing
- Timezone conversion (API returns UTC, but sites in US Eastern)
- Duration calculations fail if start/end not set

**Prevention**: Standardize on UTC + explicit TZ offset

### 4. **Performance Underestimation**
**Root Cause**: `powerAvg15Exp` (expected power) is stale; doesn't account for season/weather  
**Impact**: Red flags (kW < 50% expected) are noisy; false alarms  
**Fix**: Use dynamic weather-adjusted baseline or ML model

### 5. **API Rate Limiting / Throttle Sensitivity**
**Root Cause**: Script uses hardcoded `SLEEP = 0.4` seconds between calls  
**Issue**: 35 sites × 2 calls = 28 seconds; if changed slightly, API may 429  
**Mitigation**: Monitor response headers for rate-limit hints

### 6. **Hardware Communication vs. Data Quality**
**Root Cause**: Device marked "communicating" but telemetry fields missing or stale  
**Evidence**: `archive_columns` count varies; archiveColumns list may be incomplete  
**Impact**: Charts show hardware as healthy; reality = no power data flowing

### 7. **Cluster/Pattern Brittleness**
**Root Cause**: TF-IDF KMeans (k=7) clusters are deterministic but sensitive to  
- New alert types (changes cluster centers)
- Seasonal alert patterns (winter = more alerts, shift the clusters)
- Data size growth (refit needed periodically)

**Impact**: Historical cluster assignments become stale; analysis drifts

### 8. **Modem Contract Expirations Not Monitored**
**Root Cause**: Contract end dates exist in schema but no alerting logic  
**Risk**: Cellular modem contracts auto-expire → site goes dark suddenly  
**Prevention**: Weekly scan for contract_end < today + 30 days

---

## Health Check Indicators (What to Monitor)

### GREEN (Healthy)
- Power output > 80% of expected ✓
- All hardware status = "communicating" ✓
- Alert count = 0 or resolved within 24h ✓
- Monitoring contract = Active (status 0) ✓
- Modem contract = Active (status 0) ✓

### YELLOW (Warning)
- Power output 50–80% of expected ⚠
- Partial communication (1–2 devices offline) ⚠
- Unresolved alert > 7 days ⚠
- Monitoring contract expiring within 30 days ⚠
- Modem contract expiring within 60 days ⚠

### RED (Critical)
- Power output < 50% expected ❌
- Site status = Offline (0) ❌
- Unresolved critical alert > 24h ❌
- Contract expired ❌
- Modem not communicating ❌

---

## Recovery & Remediation

1. **Offline Site**: Check cellular modem status; verify contract active
2. **Missing Data**: Review hardware inventory for stale timestamps
3. **High Alert Rate**: Extract top clusters; assign to site manager
4. **Performance Drop**: Cross-reference weather; check for equipment recalls
5. **Contract Expiry**: Trigger renewal workflow; escalate to ops

---

## Next Steps to Implement

- [ ] Create automated health dashboard (refresh hourly)
- [ ] Add contract expiry alerting
- [ ] Implement token auto-refresh
- [ ] Build anomaly detector for production (ARIMA/Prophet)
- [ ] Create site-specific SLOs (uptime, performance targets)
- [ ] Export to Grafana/Datadog for real-time monitoring
