---
name: feedback-missing-data
description: Missing production data in dashboards is intentional signal — it indicates a site or AlsoEnergy problem, not a code bug to fix
metadata:
  type: feedback
---

Don't treat missing production data, empty chart API responses, or gaps in site data as problems to fix or work around in the dashboard code. Those gaps are the point — Parker is using the dashboard to identify which sites have data issues.

**Why:** Parker's analysis workflow uses this dashboard to spot sites with AlsoEnergy or equipment problems. Filling in gaps or adding fallback logic hides the very signal he's looking for.

**How to apply:** When building or updating dashboards, render missing data visually (e.g., gray/hatched cells) but don't add fallback data sources, interpolation, or error-handling that masks the gap. Report what the API returns, even if it's empty.
