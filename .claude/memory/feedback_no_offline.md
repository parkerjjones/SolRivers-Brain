---
name: feedback-no-offline
description: Never use --offline flag when regenerating the alert dashboard — it blanks all inverter heatmaps
metadata:
  type: feedback
---

Do not use `--offline` when running `ae_alert_dashboard.py`. Offline mode skips the chart API fetch, which means zero production data and empty heatmaps for every site. This has caused the heatmaps to appear broken multiple times.

**Why:** Parker kept seeing blank heatmaps because I used `--offline` for faster iteration. The heatmap data comes entirely from the live chart API — there is no cached fallback.

**How to apply:** Always run `python ae_alert_dashboard.py --days N` without `--offline`. Accept the ~2-minute wait for API calls. [[feedback-missing-data]]
