# SolRiver Portfolio — Morning Health Briefing
**Run:** 2026-06-11 (scheduled) · **Data source:** ae_ai_deep.txt + tracker (Jun 9 pull)

> ⚠️ **Data is stale.** Underlying pull is dated **2026-06-10 00:11 UTC** (~36h old) and the tracker batch is from **Jun 9**. `run_all.py` likely hasn't run on Parker's machine since then — figures below reflect Jun 9 conditions, not today's.

## Summary
34 active sites. The portfolio is broadly healthy and weather-limited (light rain across most sites Jun 9–12), but **8 sites need attention** — led by two genuine multi-inverter outages (Graham, Elk) and two chronic underperformers (William Perry, Kate Collins). The rest is monitoring-grade.

## Sites needing attention (action priority)

- **C & B Graham Energy (S65918)** — Worst site. **8 inverters offline** (INV-4, 7, 9, 13, 17, 22, 23, 35), ~1.4 MW down, ~6–8 MWh lost yesterday vs. ~61 MWh estimate. 30-day production only **42% of estimate**. METER 1 dark since Apr 27; weather station offline (EPI uncomputable). Tracker logs a recurring pattern of **IGBT thermal failures** (INV-2, 8, 9, 13, 17, 23, 35). Needs sustained RCA push with Solectria — this is a fleet-level reliability problem, not a one-off.
- **Elk Solar (S66930)** — **~9 inverters in outage** (01.02 down since May 27; 01.15 concurrent; 01.08–01.14 at ~30% availability). ~1.1 MW affected, **~78 MWh lost over 14 days**. Production meter reading zero → CT/metering issue (voltage calc 173% of meter power). Inv 01.01/01.05 also flagged low energy ratios.
- **WCPS – William Perry Elementary (S51957)** — Severe chronic underperformance: **30-day EPI ~0.41**, with 83–88% age losses and 58% residual loss on Inverter-1 (all 3 inverters similar). Performance Index alert open since May 24. Inverters report "available" but barely producing — needs field investigation.
- **WCPS – Kate Collins Middle (S51960)** — Inverters 2 & 3 producing **30–35% less than Inverter 1** every daylight hour (energy ratios 0.67 / 0.62), EPI 0.78. Classic string/combiner/fuse issue — field check warranted.
- **Williams Solar (S70645)** — **INVERTER A20 forced outage since Jun 5** (grid overvoltage), ~5 MWh lost, 125 kW. A20 is a repeat offender (also tripped May 26 and Jun 4 per tracker) — worth a durable fix rather than another reset.
- **Gallia Academy (S40835)** — **Inverter 1 offline since Apr 6 (~64 days, ~12 MWh lost).** Active Elkor main-meter current-mismatch (A/B/C) alert; Inv 12 showing ~29% residual underperformance.
- **Monroe Landfill (S44882)** — Inverter 20 offline since May 30 (Insulation Resistance Low / IsolationErr), ~2.3 MWh lost over 11 days, ~3.7% of capacity.
- **Eagle (S54681)** — Inv-8 External Fan Err (Jun 9), ~25% deficit, ~150 kWh/day. Minor but active.

**Recovered / watch:** Longleaf Pine (S70532) had a full-site outage Jun 3–4 (~83 MWh lost), recovered Jun 5 — but two transformer vacuum-fault alerts remain unacknowledged. Shorthorn (S64603) tracker ST1 e-stop + comm loss since Jun 9.

## Performance outliers (EPI — likely sensor, not real)
High EPI (>1.05, points to POA/pyranometer tilt/calibration drift, biasing EPI up — review, not a plant problem): **Monroe 1.18, Washington Solar 1.16, RIT 1.10, Auburn 1.09, Wallace 1.07, RRH 1.05.** Wallace and Upson explicitly flag POA reading +55%/+61% vs. other sensors.
Low EPI (real): **William Perry 0.41** and **Kate Collins 0.78** (both covered above).

## New tracker issues (Jun 9 batch — latest available)
Most were transient end-of-day comm failures that **auto-resolved same day** (Bulloch 1B 26 inv, Sunflower 102 inv, Washington 48 inv, Longleaf 10 inv). Open/persistent items worth follow-up: Graham inverter faults, Eagle Inv-8 fan err, Monroe INV-20 IsolationErr, Harding UPS battery over-temp, Longleaf transformer vacuum fault, Shorthorn tracker ST1. *No rows logged for Jun 10–11 — consistent with the stale pull.*

## Weather
Portfolio-wide light rain/overcast Jun 9–12 suppressing output across the board (normal, weather-driven). Heat climbing to **97–100°F midweek** at Southeast sites (Shorthorn, McLean, Sunflower, Gray Fox, Richmond, Bulloch, Whitetail) — monitor for thermal derating.

## Data gap
**Manuel Lawrence Dairy (S55935)** — full data-retrieval failure (0% availability reported, unvalidated). Note: this site is flagged as excluded from the active 34-site portfolio in project config.

---
*To refresh: run `python run_all.py` on your machine — this environment can't reach AlsoEnergy.*
