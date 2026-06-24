# SolRiver Portfolio — Morning Health Briefing
**Run:** 2026-06-16 | **Data source:** ae_ai_deep.txt + tracker_new_rows_609.csv

> ⚠️ **STALE DATA.** Underlying summaries were generated **Jun 10, 00:11 UTC (~6 days old)** and the alert export is from the Jun 9 pull. Nothing has refreshed since. Parker likely hasn't run `run_all.py` recently — the pull only happens on his machine. Treat everything below as a Jun 9 snapshot, not live status.

## Portfolio summary
35 sites monitored. ~25 healthy or weather-limited only; **~10 need attention** — most carrying genuine equipment issues. (Note: every site shows Risk Score 50, a uniform default — not useful for triage; the detail below is what matters.) The region was under persistent light rain Jun 9–12 with a heat ramp to 95–100°F midweek, so portfolio-wide EPIs are weather-suppressed.

## Sites needing attention (lead with these)

- **C & B Graham (S65918) — worst in fleet.** ~8 inverters offline (INV-4, 7, 9, 13, 17, 22, 23, 35; some since April), ~1.4 MW down. METER 1 not reporting since Apr 27. 30-day production only **42% of estimate** (740 of ~1,782 MWh). Gateway/UPS offline, EPI uncomputable. Fresh alerts confirm a 9-inverter comm-failure outage + 41-inverter shutdown-command fault. Needs site visit.
- **Elk Solar (S66930).** ~9 inverters in outage/reduced state (~1.1 MW, ~5.6 MWh/day, ~78 MWh over 14 days). INV 01.02 offline since May 27; 01.15 concurrent. **Production meter reads zero** — CT/metering fault (voltage calc 173% of meter power). Multiple Rule Fail performance errors.
- **Manuel Lawrence Dairy (S55935).** Full data blackout — hardware list, EPI, availability all unavailable; rule tool reports 0% availability across all 15 inverters and invalid IMT reference-cell readings. Can't confirm production. **Restore data acquisition** to re-enable monitoring.
- **Monroe Landfill (S44882).** Inverter 20 offline since May 30 — Insulation Resistance Low (IsolationErr) forced outage, ~73 kW, ~2.3 MWh lost over 11 days. Active meter current-mismatch alert too.
- **Gallia Academy (S40835).** Solectria Inverter-1 offline since Apr 6 (~64 days), ~12 MWh lost. Active current-mismatch (A/B/C) on the Main Elkor meter — CT/wiring review. Inverter 12 also ~29% under peers.
- **Williams Solar (S70645).** INVERTER A20 offline since Jun 5 (grid overvoltage → comm fault), ~125 kW, ~5 MWh lost, ongoing.
- **Longleaf Pine (S70532).** Recovered from a full-site outage Jun 3–4 (~83 MWh lost, cause undetermined); a similar one hit May 17–19. Tracker Controller 1 offline since Jun 3; two transformer vacuum-fault alerts still unacknowledged.
- **Eagle (S54681).** Inv-8 active External Fan Err (Jun 9), capped ~25% below peers, ~150 kWh/day ongoing.
- **WCPS – William Perry Elementary (S51957).** Severe persistent underperformance: EPI ~0.41, 85% of estimate, ~58% residual loss across all 3 inverters. Performance Index alert open since May 24. Not weather — needs field review.
- **WCPS – Kate Collins Middle (S51960).** Inverters 2 & 3 running 30–35% below Inverter 1 every daylight hour (energy ratios 0.67 / 0.62). String/combiner/fuse check.

## Performance outliers — high EPI (likely POA/pyranometer calibration, not gains)
Monroe Landfill (1.18), Washington Solar (~1.16), RIT (~1.10), Auburn (1.09), Wallace (1.07), RRH 1 & 2 (1.05). Several explicitly flag POA insolation mismatches (Upson +61%, Wallace +55%, Whitetail tilt/azimuth). Worth a sensor calibration sweep — these inflate reported EPI.

**Low end:** WCPS William Perry (0.41) and Kate Collins (0.78) are the true underperformers (above). Longleaf availability 93% (outage-dragged); RIT 94% (already recovered).

## New issues logged today
**None.** The latest tracker export is from the Jun 9 pull (tracker_new_rows_609.csv) — no rows dated Jun 16. Refresh needed to see anything since.

## Weather
Persistent light rain Jun 9–12 suppressed midday output portfolio-wide; heat climbing to 95–100°F midweek at several southern sites (Shorthorn, McLean, Gray Fox, Sunflower, Longleaf) — watch for thermal derating. No stow/wind risk noted.

---
*To refresh, run `python run_all.py` on your machine.*
