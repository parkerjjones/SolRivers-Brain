# Whitetail (S59656) — Quick Reference

**Site:** Whitetail | **Key:** `S59656` | **Portfolio:** C12941
**Location:** SC | **Capacity:** ~14.2 MW_dc
**Inverters:** 80x Sungrow SG125HV (fc=1) | **Trackers:** GameChange (fc=24)
**Meter:** SEL-735 Production Meter (`H312384`, fc=2)
**Weather:** Hukseflux SR-30 POA (`H312487`), GHI (`H312488`), ALB (`H312489`)
**Relay/Recloser:** SEL-751 Relay (`H312387`, fc=11)
**Datalogger:** PowerManager 2200 (`H521460`, fc=10)

---

## Hardware IDs — Inverters of Interest

| Inverter | Hardware Key | Role |
|----------|-------------|------|
| Inverter 2 | H312389 | SECONDARY |
| Inverter 5 | H312392 | CONTEXT |
| Inverter 7 | H312394 | PRIMARY |
| Inverter 35 | H312422 | PRIMARY |
| Inverter 39 | H312426 | CONTEXT |
| Inverter 40 | H312427 | SECONDARY |
| Inverter 51 | H312439 | PRIMARY |
| Inverter 52 | H312440 | CONTEXT |
| Inverter 71 | H312459 | CONTEXT |
| Inverter 72 | H312460 | CONTEXT |
| Inverter 78 | H312466 | PRIMARY |

**Pattern:** Inverter N = `H31238{7+N}` for 1-47, then offset +1 starting at 48 (H312436).
Full range: Inverter 1 (`H312388`) through Inverter 80 (`H312468`).

---

## Data Registers Available (per scriptsite API)

### Per Inverter (48 registers)
| Field | dataName | Description |
|-------|----------|-------------|
| DC Voltage | Vdc1 | DC bus voltage (single MPPT) |
| DC Current | Idc1 | DC bus current |
| AC Voltage | VacAB, VacBC, VacCA | Line-to-line AC voltages |
| AC Current | IacA, IacB, IacC | Phase currents |
| AC Power | KwAC | AC active power (kW) |
| Energy | KWH | Cumulative energy |
| Reactive | KVAR, KVA | Reactive/apparent power |
| Power Factor | PowerFactor | |
| Status | (various) | Inverter state/fault registers |

### Production Meter (SEL-735, 34 registers)
| Field | dataName | Description |
|-------|----------|-------------|
| Real Power | KW | Instantaneous kW |
| Total Energy | KWHnet | Net cumulative kWh |
| Export Energy | KWHdel | Delivered kWh |
| Import Energy | KWHrec | Received kWh |
| Phase Voltage | VacA, VacB, VacC | Volts A/B/C to neutral |
| Phase Current | IacA, IacB, IacC | Amps per phase |
| Power Factor | PowerFactor | |
| Frequency | (unnamed) | Line frequency |

### POA Pyranometer (Hukseflux SR-30, 21 registers)
| Field | dataName | Description |
|-------|----------|-------------|
| POA Irradiance | Sun | W/m² (temp-compensated) |
| Body Temp | bodyTemp | Sensor temperature |

---

## API Endpoints That Work for This Site

| Endpoint | Method | Notes |
|----------|--------|-------|
| `/api/view/portfolio/C12941` | GET | Site list with live power |
| `/api/view/site/S59656` | GET | Site detail (address, capacity) |
| `/api/scriptsite/S59656?lastChanged=...` | GET | Hardware + live dataRegisters |
| `/api/view/alerthistory` | POST | `{"key":"S59656","from":"...","to":"...","offset":300}` |
| `/api/ruleresults/S59656?lastChanged=...` | GET | Diagnostic checks |
| `/api/view/kpidashboard?lastChanged=...` | POST | `{"keys":["S59656"]}` — daily KPIs |
| `/api/ai-site-summary?siteId=S59656&lang=en-US` | GET (SSE) | AI health summary |

### Chart / Time-Series Data (UNLOCKED)

`POST /api/view/chart?lastChanged=...` — requires a complex nested JSON payload.
See `whitetail_timeseries.py` for the working payload structure.

Key payload fields:

- `chartType: 1`, `binSize: 15` (minutes), `context: "site"`
- `start/end`: date strings
- `hardwareSet`: array of H-keys
- `query.kpiChart.categories.measurements`: bitmask array (value 1=Power, 2=Energy, 4/8=Irradiance, 16=DC Current, 32=DC Voltage, 64=AC Current, 128=AC Voltage, 256=Power Factor, 1024=Fault/Status)
- `source`: array of site keys

`POST /api/view/chart/kpimenu` — returns available measurement categories for a site.
Payload: `{"siteKeys":["S59656"],"hardwareSet":[...]}`

---

## Extraction Script

```bash
python whitetail_extract.py
```

**Outputs:**
- `alarms_whitetail.csv` — All alarms Feb–May 2026, flagged for ISO/leakage/comm/recloser, with target-morning overlap column
- `inverter_settings.csv` — API-exposed settings for Inv 7, 35, 51, 78 (limited to Modbus comm params)
- `morning_timeseries.csv` — (blocked, needs chart endpoint)
- `meter_morning.csv` — (blocked, needs chart endpoint)

---

## Late-Start Investigation Target Dates (2026)

02-22, 02-27, 03-01, 03-04, 03-05, 03-06, 03-27, 03-30, 03-31,
04-01, 04-02, 04-03, 04-04, 04-05, 04-07, 04-10, 04-11, 04-12,
04-13, 04-14, 04-15, 04-17, 04-18, 04-26, 04-29,
05-07, 05-09, 05-10, 05-11, 05-12

Morning window: 05:00–11:00 Eastern (09:00–16:00 UTC broad).
