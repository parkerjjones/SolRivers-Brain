# RCA Playbooks for Solar Asset Management AI

## 1. Full Site Outage

Trigger:
- Actual energy is zero or near-zero during daylight while expected energy is materially above zero.

Check sequence:
1. Confirm daylight and irradiance.
2. Check revenue meter energy. If meter is updating and zero, likely real outage.
3. Check DAS heartbeat. If stale, classify as data-quality issue until meter confirms.
4. Check POI breaker/recloser status.
5. Check inverter fleet status.
6. Check utility outage/curtailment notices.
7. Estimate lost energy from expected minus actual.
8. Assign owner:
   - Breaker/recloser/grid issue: O&M + Utility
   - Inverter fleet issue: O&M
   - Stale DAS only: DAS/SCADA Provider

Output:
- Severity: Critical unless data-only.
- Next action: Confirm site status and create or update O&M ticket.

## 2. Low Performance Index With High Availability

Trigger:
- PI below threshold, but availability is near 100%.

Likely causes:
- Soiling
- Vegetation shading
- Tracker angle issue
- Partial inverter derate
- Bad POA sensor
- Stale expected model
- Curtailment not tagged correctly

Check sequence:
1. Compare actual vs expected on clear-sky days.
2. Compare inverter-level outputs against peers.
3. Check POA/GHI sensor quality.
4. Check tracker target vs actual angle.
5. Check weather and curtailment flags.
6. Check whether expected model recently changed.

Output:
- Do not dispatch immediately unless equipment evidence exists.
- Recommend data/model validation if no equipment evidence.

## 3. High Performance Index

Trigger:
- PI materially above normal, especially > 125%.

Likely causes:
- Expected model too low
- Irradiance sensor under-reporting
- Meter backfill or scaling issue
- Wrong capacity
- Bifacial/snow/albedo gain
- Curtailment baseline issue

Check sequence:
1. Check expected energy and weather input freshness.
2. Compare revenue meter to SCADA energy.
3. Compare capacity metadata against asset registry.
4. Look for meter backfill or missing prior intervals.
5. Review weather conditions.

Output:
- Mark as "suspicious high PI" if not validated.
- Do not treat as overperformance until model and meter are confirmed.

## 4. Inverter Offline or Underperforming

Trigger:
- One or more inverters produce materially less than peers during irradiance.

Check sequence:
1. Identify affected inverter(s).
2. Check status/fault code.
3. Compare DC input/string current.
4. Check AC breaker/disconnect status.
5. Check whether peers on same transformer are affected.
6. Estimate lost energy using peer-normalized expected output.
7. Check warranty status for repeated faults.

Output:
- Owner: O&M.
- Escalate to warranty/EPC if recurring, design-related, or inside warranty window.

## 5. DAS / Communications Issue

Trigger:
- Data stale, missing, flatlined, or contradictory.

Check sequence:
1. Check last valid timestamp.
2. Check whether all devices or one device stopped reporting.
3. Compare revenue meter portal or utility data.
4. Check gateway, modem, data logger, and power supply/UPS status.
5. Determine whether operational status can be confirmed from another source.

Output:
- Owner: DAS/SCADA Provider.
- If production cannot be verified, flag "operational state unknown."

## 6. Tracker Issue

Trigger:
- Tracker angle flatlined, actual angle deviates from target, or tracker alarms appear.

Check sequence:
1. Compare actual vs target angle.
2. Check wind speed and stow command.
3. Identify whether issue is site-wide or block-specific.
4. Compare affected block production to normal blocks.
5. Review tracker controller alarms and power/network status.

Output:
- Owner: O&M.
- If in stow due to wind, classify as weather/operational mode, not failure.

## 7. Utility / Grid Event

Trigger:
- POI breaker/recloser open, grid voltage/frequency abnormal, site trips, utility notice, or many inverters trip together.

Check sequence:
1. Check POI breaker/recloser status.
2. Check grid voltage/frequency trends.
3. Check relay event logs if available.
4. Check utility outage/feeder notifications.
5. Confirm whether curtailment or outage is contractually excusable.
6. Track restoration and lost revenue classification.

Output:
- Owner: Utility + O&M.
- Asset Management should track commercial treatment and documentation.

## 8. Soiling / Vegetation

Trigger:
- Gradual underperformance, high availability, clear-day deficit, affected sections/strings.

Check sequence:
1. Compare clear-day normalized performance over time.
2. Compare site to nearby sites with similar weather.
3. Check vegetation/soiling inspection history.
4. Review recent rainfall/wash events.
5. Estimate economic value of cleaning/mowing.

Output:
- Owner: O&M.
- Next action: inspection, vegetation maintenance, or wash ROI review.

## 9. Revenue Meter vs SCADA Mismatch

Trigger:
- Revenue-grade meter and SCADA energy diverge beyond threshold.

Check sequence:
1. Confirm time interval alignment and timezone.
2. Check CT/PT ratio and meter multiplier.
3. Check missing/backfilled intervals.
4. Compare daily totals, not just instantaneous values.
5. Determine which source is authoritative for billing.

Output:
- Owner: DAS/SCADA Provider.
- Asset Management should flag revenue/reporting risk.
