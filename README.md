# Romanian Climate Explorer · WxProbs

A standalone site for exploring Romanian station observations, climate normals,
historical records, daily weather charts and extreme-event candidates.

The site includes the refreshed design and **© WxProbs** on every exported PNG
and SVG chart. ANM attribution is retained separately.

## Deploy from GitHub to Vercel

Start with **[DEPLOY.md](DEPLOY.md)**. This repository contains the application
code and a pinned data manifest. The two large databases are **GitHub Release
attachments**, not Git files. Vercel downloads and verifies them during its build.
The repository and releases are public. Vercel downloads the pinned snapshot
anonymously; no personal GitHub token or token renewal is needed.

The live site is https://romanian-climate-explorer.vercel.app/. It uses Vercel's
**Large Functions beta** because the uncompressed snapshot is about 3.99 GB.
The current deployment uses the Hobby plan within its resource quotas.

## Run locally

Python 3.12 is the deployment target. No third-party Python packages or frontend
build tools are needed.

If the release assets are in a sibling `release-assets` folder:

```powershell
python scripts/fetch_snapshot.py --asset-dir ../release-assets
python -m anm_climate.explorer_server --port 4887 --open-browser
```

Alternatively run against an existing snapshot without copying it:

```powershell
python -m anm_climate.explorer_server --data-root "E:\Codex\Weather Viewer\data\anm" --port 4888 --open-browser
```

## Repository layout

- `web/`: public site, styles, charts and Romania boundary.
- `api/index.py`: one Vercel function for the read-only API and health check.
- `anm_climate/`: existing climate query engine and local server.
- `snapshots/`: pinned SHA-256 checksums and historical review notes.
- `scripts/`: snapshot packaging and verified build-time download.
- `tests/`: deployment tests and existing climate API tests.

The repository includes the selected original parser, downloader and statistics
algorithms needed for daily updates. The original project, raw archive collection
and protected backups remain separate. Data stays outside `web/`; the web API
opens SQLite in read-only mode, and updates run in a separate Actions workspace.

## Checks

```powershell
python -m unittest discover -s tests -v
node --check web/climate.js
node --check web/daily-charts.js
```

The climate integration tests run when `data/anm` contains the verified
snapshot. GitHub Actions runs the deployment tests and skips data-dependent
checks when databases are absent.

## Updating the data

Records can be viewed for one station or across Romania, by calendar day,
calendar month, specific month/year, year, or all available years. National
records retain every tied station/date, variable-specific quality exclusions,
source details and CSV exports. They describe extremes in the available archive;
station coverage varies over time.

The station Records view defaults to **Top 10 observations** for the selected
calendar month across all years. Choose a record category to rank individual
daily measurements, or select a specific year/month. Equal values share a rank
and all observations tied at tenth place are retained. Dates open their source
and quality details; CSV exports include the rankings. **Record summary** keeps
the single-record-per-category view available. Rankings use existing observations
and add no stored copy of station data.

Each deployment rebuilds a compact `national_records` table in the serving
database from the verified observations and QC exclusions. This adds about 2.4 MB
of summaries and avoids scanning the archive on visitor requests. The full source
archive remains unchanged; national summaries refresh with automatic deployments.

Daily cloud updates are configured in `.github/workflows/daily-refresh.yml`.
Read **[DAILY_UPDATES.md](DAILY_UPDATES.md)** for the schedule, validation,
credentials, limits and recovery instructions. New snapshot URLs are committed
with their checksums, so routine updates do not require editing Vercel settings.

For a separately reviewed manual historical refresh:

Against a closed, checkpointed pair of databases, run:

```powershell
python scripts/package_snapshot.py --data-root "PATH_TO_DATA_ANM" --output ../release-assets
```

Commit the updated manifest and review notes, publish the new gzip files under a
**new release tag**, set the matching `base_url` in the manifest, then commit and deploy.
The downloader intentionally rejects data that does not match the committed
checksums. Do not overwrite the contents of an existing tagged snapshot.

## Attribution

Chart presentation: © WxProbs.

Weather observations: Administrația Națională de Meteorologie (ANM),
[MeteoRomania Open Data Portal](https://odp.meteoromania.ro/station_data_series/climate/daily/).
WxProbs chart branding does not replace the underlying dataset attribution.

The names and coordinates of 20 stations absent from the ANM locations catalogue are supplemented by
exact WIGOS matches from [WMO OSCAR/Surface](https://oscar.wmo.int/surface/rest/api/search/station?territoryName=ROU),
verified on 21 September 2026. These verified metadata fallbacks are stored in
`anm_climate/station_metadata.py` and applied to the shared API catalogue, including
search, map markers, calendar records and exports. Existing ANM names and
coordinate pairs take precedence. The fallbacks persist across daily data
refreshes. WMO coordinates describe registry locations, not historical station
relocations; observation data is unchanged. Map counts and availability messages
are calculated from the catalogue rather than fixed in the interface.
