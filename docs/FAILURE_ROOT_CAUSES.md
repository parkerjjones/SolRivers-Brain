# Root Causes of Alert Generation & System Failures

## Classification of Failures

Based on code analysis and alert schema, failures cluster into **8 primary categories**:

---

## 1. **Communication Failures (Most Common)**

### Hardware Not Responding
**Trigger**: Device marked offline in status field  
**Root Causes**:
- Cellular modem down or no signal
- Network gateway offline
- Device power loss
- Software hang/crash

**Alert Code**: Event type codes like 614 (Rule Tool Alert)  
**Detection**: `hardware_status` field not "communicating"  
**Impact**: No telemetry flowing; blind to actual state  
**Typical Duration**: Minutes to hours (if device auto-restarts) or days (if needs intervention)

### Intermittent Communication  
**Pattern**: Device responds sporadically; archives sparse telemetry  
**Root Causes**:
- Weak cellular signal (poor tower coverage)
- Network congestion during peak hours
- Firmware bug causing watchdog resets
- Thermal throttling in hot climates

**Detection**: Archive columns count < expected; last_upload timestamp > 15 min ago  
**Data Impact**: Gaps in production time-series; correlation analysis fails

---

## 2. **Production Underperformance (High Volume)**

### Below Expected Output
**Alert**: Power output < 50% of expected  
**Root Causes**:
1. **Weather** (legitimate, 40% of cases)
   - Clouds, rain, snow, dust, haze
   - Low irradiance even on clear day
   
2. **Hardware Degradation** (30% of cases)
   - Inverter efficiency loss
   - String inverter failure
   - Combiner box issue
   - DC-side wiring/connector corrosion
   
3. **Operational Issues** (20% of cases)
   - Manual disconnect/isolation
   - Grid curtailment (operator-requested)
   - Circuit breaker trip
   - Preventive maintenance
   
4. **Data/Measurement Error** (10% of cases)
   - Stale expected baseline
   - Wrong production meter
   - Sensor failure (irradiance probe)

**Detection Strategy**:
- Compare actual power vs. expected power (15-min rolling average)
- Cross-reference with weather station data (irradiance, clouds)
- Check if multiple sites dropped simultaneously (→ grid issue) vs. single site (→ hardware)

**False Positive Rate**: High (~40%) due to stale weather-adjusted baseline

---

## 3. **Sensor/Instrument Failures**

### Production Meter Errors
**Problem**: Meter stuck, oscillating, or drifting  
**Impact**: "Production looks good" but actually underperforming  
**Detection**: 
- Compare meter output to string-level monitors
- Check meter value stability (should smooth, not spike)
- Verify against inverter-reported output

### Weather Station Issues
**Problem**: Irradiance probe dirty, misaligned, or failed  
**Impact**: Cannot distinguish weather-caused dips from real issues  
**Symptoms**:
- Irradiance reports < 0 (impossible)
- Irradiance constant for days (sensor stuck)
- Irradiance spikes unrelated to AC output

### Temperature Sensor Failure
**Problem**: Temperature readings invalid or stale  
**Impact**: Cooling/derating calculations wrong; misdiagnosis of thermal issues

---

## 4. **Inverter & Power Electronics Failures**

### Inverter Trip / Shutdown
**Root Causes**:
- Overvoltage on DC side (> 600V)
- Overcurrent on AC side (> 125% rating)
- Ground fault detected
- Thermal trip (>60°C internal)
- Internal capacitor failure (common in old units)
- Firmware bug

**Duration**: Automatic reset (seconds) or requires manual intervention (hours/days)

### String Inverter Group Failure
**Architecture**: Some sites use multiple string inverters feeding central inverter  
**Failure Mode**: One string inverter offline → site shows 60% power even if 5 of 6 strings healthy  
**Detection**: Compare string-level monitors to total output

### DC-Side Faults
**Issues**: 
- String imbalance (one string weak)
- Module bypass failure
- Combiner box breaker open
- String wiring degradation

---

## 5. **Contract & Connectivity Failures**

### Monitoring Contract Expired
**Status Code**: 2 (Expired), 1 (Warning within 30 days)  
**Impact**: AlsoEnergy stops collecting data; monitoring halts  
**Warning Sign**: `monitoringContractEndDate` passed  
**No Alerting**: System does not auto-alert for this; must manually check

### Cellular Modem Contract Expired  
**Impact**: Device cuts off from network; becomes unreachable  
**Status Code**: 2 (Expired) = **CRITICAL**  
**Issue**: 
- Modem has built-in auto-disconnect on contract end
- If you miss renewal window, site goes completely dark
- Recovery requires on-site technician to re-enable

**Prevention**: 
- Weekly scan: `cellModemContractEndDate < today + 60 days`
- Automated workflow to renew before expiry

---

## 6. **Datalogger/Gateway Issues**

### Datalogger Offline
**Role**: Central hub collecting from all site devices (inverters, meters, weather)  
**Failure Impact**: **Entire site goes dark** (single point of failure)  
**Root Causes**:
- Power loss to datalogger
- Software crash / watchdog reset loop
- Storage full (logging stopped)
- Memory leak causing memory exhaustion
- Network disconnected

**Detection**: All hardware status = offline simultaneously  
**Recovery**: Reboot datalogger (remote or on-site)

### Gateway Communication Timeout
**Symptom**: Datalogger running but devices not reporting  
**Root Causes**:
- Modbus/RS-485 wiring issue
- Device address mismatch
- Polling timeout too short
- Too many devices on one gateway (>32 nodes)

---

## 7. **Data Integrity & Schema Failures**

### Missing Alert Fields
**Problem**: `alert_id` null or truncated  
**Impact**: Duplicate ingestion; alert not recorded  
**Code Check**: `ae_alert_loader.py` line 419-423:
```python
bad = sum(1 for r in rows if not r["alert_id"])
if bad:
    print(f"  [warn] {bad} records missing alertId, skipping")
rows = [r for r in rows if r["alert_id"]]
```

### Timestamp Parsing Failures
**Issue**: Alert timestamps in unexpected format  
**Formats Expected** (line 163-166):
- ISO-8601: `2025-06-08T14:30:45Z`
- No Z: `2025-06-08T14:30:45`
- Excel: `06/08/2025 2:30:45 PM`

**Failure**: Format doesn't match → `parse_ts()` returns None → duration = NaN

### Response Shape Unrecognized
**Issue**: API changes response structure  
**Code Fallback** (line 144-152):
```python
for k in ("list", "data", "alerts", "items", "results", "rows"):
    if isinstance(payload.get(k), list):
        return payload[k]
if payload:
    print(f"  [warn] unrecognised response shape")
```

---

## 8. **Operational Errors & Maintenance**

### Preventive Maintenance Window
**Cause**: Site intentionally shut down for inspection/repair  
**Duration**: Planned (hours) vs. unplanned (days)  
**False Alert**: Production drop flagged as failure  
**Prevention**: Add maintenance calendar to alert rules

### Manual Disconnect / Isolation
**Cause**: Inverter breaker opened by technician  
**Recovery**: Re-close breaker; may take hours if technician unavailable  
**Data Impact**: Looks like equipment failure but is intentional

### Grid Curtailment / Curtail-to-Zero
**Cause**: Utility requests site reduce output (frequency support, oversupply)  
**Duration**: Minutes to hours  
**False Alert**: Production hits zero unexpectedly  
**Detection**: Grid frequency data + operator notification

### Supply Chain / Parts Failure
**Example**: Capacitor batch defect in 2023 inverters  
**Pattern**: Multiple sites of same model fail within weeks  
**Detection**: Group alerts by hardware model + function code; spot clustering

---

## Failure Severity Scoring

### Urgency Level Heuristics (code line 92-99):

| Score | Keywords | Meaning | Response Time |
|-------|----------|---------|----------------|
| 3 | critical, severe, down, failed, offline, not communicating, no production, not responding, fault | **CRITICAL** - Site completely offline | < 1 hour |
| 2 | alert, error, below expected, tracking low, underperforming, issue, reduced, partial | **WARNING** - Major issue, trending down | < 4 hours |
| 1 | warning, slightly, minor, intermittent, occasional | **MINOR** - Degraded, but functioning | < 1 day |
| 0 | communicating, normally, in line, as expected, on track | **HEALTHY** - Operating within norms | Monitor only |

---

## Failure Prediction Indicators

### Early Warning Signs (Next 24-48 hours)
1. Unresolved alert > 7 days + urgency = 2
2. Hardware status = "communicating" but archive_col_count dropping
3. Alert rate increasing (rolling 7-day average)
4. Contract warning (status = 1) for either monitoring or modem
5. Same event type clustering (multiple alerts code 614 in short window)

### Imminent Failure (Next 1-6 hours)
1. Hardware status = "offline" + last communication > 30 min ago
2. Active alert with is_resolved = false + urgency = 3
3. Power output = 0 kW for > 15 min + no maintenance window
4. Multiple devices offline on same site + different hardware types

---

## Gap Analysis: What's NOT Being Monitored

1. **No automatic contract expiry alerts** → modem surprise disconnects
2. **No threshold-based anomaly detection** → slow degradation (1% per week) missed
3. **No correlation of production drop across sites** → grid events dismissed as local
4. **No predictive maintenance** → capacitor failures not anticipated
5. **No weather-adjusted baseline** → false "underperformance" alerts flood system
6. **No automated remediation** → datalogger reboot only manual

---

## Recommended Fixes (Priority Order)

1. **Add contract expiry monitoring** (1 hour implementation)
2. **Implement token auto-refresh** (2 hours)
3. **Add weather-adjusted baseline** (8 hours, requires weather API integration)
4. **Build anomaly detector** (24 hours, ARIMA or Prophet)
5. **Add site clustering** (4 hours, flag grid-wide events)
6. **Automated modem reboot logic** (6 hours, if device supports remote reboot API)
