# Design history and rollback

## Classic design — saved 21 September 2026

- Git tag: `design-classic-2026-09-21`
- Commit: `d0f60be5f1cf09f57b0a266eb91c4e37ae8ed3c9`
- Repository version: https://github.com/thghost75/Romanian-Climate-Explorer/tree/design-classic-2026-09-21
- Local backup: `../romanian-climate-classic-design-2026-09-21.zip`
- Appearance: light climate explorer with map and station picker, followed by
  Overview, Records, Temperature, Rainfall, Extremes and History tabs; separate
  nationwide On This Day view.
- Capabilities: all 160 named and mapped stations, historical quality notes,
  full daily histories, chart exports with © WxProbs, public data releases and
  automated daily ANM updates.

## Modern workspace — September 2026

The React design is in `frontend/`. It adds light/dark mode, a station sidebar,
annual anomaly heatmaps and station comparisons while retaining records, events,
normals, daily history, source/QC inspection and © WxProbs exports. The build
generates dashboard data from the same verified snapshot used by the API.

The preserved classic frontend remains in `web/`. Vercel serves the generated
modern `dist/` directory; daily automation still updates `web/data-status.json`,
which the build copies into `dist/`.

## Switch back without losing newer observations

Restore only the classic build configuration and frontend, then commit and push:

```sh
git restore --source=design-classic-2026-09-21 -- vercel.json web/index.html web/climate.js web/daily-charts.js web/climate.css web/site.css web/data-status.js web/favicon.svg web/romania.geojson
git add vercel.json web/index.html web/climate.js web/daily-charts.js web/climate.css web/site.css web/data-status.js web/favicon.svg web/romania.geojson
git commit -m "Restore the classic climate explorer design"
git push origin main
```

Keep the current `snapshots/manifest.json`, `snapshots/candidate_review_notes.json`,
`web/data-status.json`, `.github/workflows/` and backend files so data freshness,
station fixes and daily updates are retained. Do not reset the whole repository
or force-push the saved tag over main. Vercel will deploy the rollback commit.
