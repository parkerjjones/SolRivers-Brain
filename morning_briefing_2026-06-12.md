# SolRiver Morning Health Briefing — Fri, Jun 12, 2026

> ⚠️ **Data is stale.** Underlying summaries were generated **Jun 10, 00:11 UTC (~2.5 days ago)**. No fresh pull has run since. Treat outage durations/impacts below as "as of Jun 9" — some may have resolved. Run `python run_all.py` on your machine to refresh.

## Portfolio summary
~34 active sites. **~9 flagged for attention**, the rest operating normally (mostly weather-limited under a rainy, hot mid-week). Two sites are in real trouble (Graham, Elk); the rest are single-inverter outages or chronic underperformance.

## Sites needing attention (action first)

- **C & B Graham Energy (S65918) — most critical.** ~8 inverters offline (INV-4, 7, 9, 13, 17, 22, 23, 35), ~1.4 MW down. Day-of loss ~6–8 MWh vs. ~61 MWh estimate; 30-day production only **42% of estimate**. METER 1 dead since Apr 27. This site has a running history of inverter thermal events (Solectria RCA/replacements). Needs sustained O&M push, not a one-off.
- **Elk Solar (S66930).** ~9 inverters offline/derated (01.02 & 01.15 fully offline since May 27; 01.08–01.14 at ~30% availability). ~1.1 MW affected, ~5.6 MWh/day, **~78 MWh over 14 days**. Production meter reading **zero** + voltage calc 173% of meter power → CT/metering issue masking true output.
- **WCPS – William Perry Elementary (S51957).** Severe underperformance: 30-day EPI **~0.41**, 85% of estimate. Sampled inverter shows 83–88% DC/AC age loss + 58% residual across all three units. Performance Index alert open since May 24. Needs field review — pattern looks like a real plant fault, not weather.
- **Gallia Academy (S40835).** Solectria Inverter-1 offline since Apr 6 (~64 days), ~12 MWh lost. Inv 12 chronically ~29% low. Active current-mismatch alert on the Main Elkor meter (CT/wiring check).
- **Monroe Landfill (S44882).** Inverter 20 offline since May 30 (Insulation Resistance Low / IsolationErr), ~73 kW, ~2.3 MWh over 11 days.
- **Williams Solar (S70645).** INVERTER A20 forced outage since Jun 5 (grid overvoltage → comm fault), ~125 kW, ~5 MWh. *(Tracker log shows a tech brought A20 back on 5/28 from a prior trip; this is a recurrence — worth a root-cause look.)*
- **Eagle (S54681).** Inv-8 running ~25% low with active External Fan Err (Jun 9), ~150 kWh/day. Partial capability, ~125 kW.
- **WCPS – Kate Collins Middle (S51960).** Inverters 2 & 3 chronically 30–35% below Inv 1 (low energy ratios 0.67/0.62) — persistent string/combiner issue, field investigation.
- **Longleaf Pine (S70532).** Full-site outage Jun 3–4 (~83 MWh lost), **recovered Jun 5** — flagging only because it dragged availability to 93% and a similar event hit May 17–19. Two transformer vacuum-fault alerts remain unacknowledged.

## Performance outliers (likely sensor/POA calibration, not plant faults)
Persistently high EPI (>1.05) points to pyranometer/PV-model drift worth a calibration check, not lost energy: **Monroe Landfill (1.18)**, **Washington Solar (1.16)**, **RIT (~1.10)**, **Auburn (1.09)**, **Wallace (1.07)**, **RRH 1&2 (1.05)**. Several (Washington, RIT, Wallace, Upson) have rule-tool flags confirming POA insolation mismatch.

Low availability is fully explained by the outages above (Longleaf 93%, Elk 95%, Gallia 95%, Monroe 96%) — no separate availability problem.

## New issues logged today
**None.** The combined tracker ends Jun 5; the Jun 9 alert export (tracker_new_rows_609) is the freshest batch. Most of those are end-of-day comm blips and meter current-mismatch flags that auto-resolved same day. The genuinely production-impacting Jun 9 items already roll up into the flagged sites above (Graham comm/inverter faults, Eagle Inv-8 fan error, Monroe INV-20).

## Weather
Portfolio-wide light rain/rain Jun 10–12 limiting output across the board. Southeastern sites (Shorthorn, McLean, Sunflower, Whitetail, Bulloch, Richmond, Gray Fox, Williams) face highs near **97–100°F** mid-week — watch for thermal derating. Western sites (Auburn, Sheridan, Wallace, Marble, Green Solar) clear and favorable Jun 11–12.

---
*Excluded: Manuel Lawrence Dairy (S55935) is not in the active portfolio; its summary shows a full data-retrieval failure (0% availability reported but unverifiable).*

**To refresh this briefing, run `python run_all.py` on your machine.**
