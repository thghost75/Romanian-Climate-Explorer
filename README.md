# Romanian Climate Explorer · WxProbs

A standalone site for exploring Romanian station observations, climate normals,
historical records, daily weather charts and extreme-event candidates.

The site includes the refreshed design and **© WxProbs** on every exported PNG
and SVG chart. ANM attribution is retained separately.

## Deploy from GitHub to Vercel

Start with **[DEPLOY.md](DEPLOY.md)**. This repository contains the application
code and a pinned data manifest. The two large databases are **GitHub Release
attachments**, not Git files. Vercel downloads and verifies them during its build.
The repository remains private. Add a repository-scoped, read-only
`CLIMATE_GITHUB_TOKEN` in Vercel as described in the deployment guide.

This is prepared for deployment, not a claim that a live Vercel deployment has
passed. It requires Vercel's **Large Functions beta** because the uncompressed
snapshot is about 3.99 GB. Hobby is for personal, non-commercial use within its
resource quotas. Account eligibility and actual deployed performance remain to
be checked during your first deployment.

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

The original ingestion project, raw archives and protected backups are not part
of this deployment repository. Only the files needed to run the explorer are
included. Data stays outside `web/` and SQLite connections use read-only mode.

## Checks

```powershell
python -m unittest discover -s tests -v
node --check web/climate.js
node --check web/daily-charts.js
```

The 14 climate integration tests run when `data/anm` contains the verified
snapshot. GitHub Actions runs the deployment tests and skips data-dependent
checks when databases are absent.

## Updating the data

Against a closed, checkpointed pair of databases, run:

```powershell
python scripts/package_snapshot.py --data-root "PATH_TO_DATA_ANM" --output ../release-assets
```

Commit the updated manifest and review notes, publish the new gzip files under a
**new release tag**, update `CLIMATE_SNAPSHOT_BASE_URL` in Vercel, then redeploy.
The downloader intentionally rejects data that does not match the committed
checksums. Do not overwrite the contents of an existing tagged snapshot.

## Attribution

Chart presentation: © WxProbs.

Weather observations: Administrația Națională de Meteorologie (ANM),
[MeteoRomania Open Data Portal](https://odp.meteoromania.ro/station_data_series/climate/daily/).
WxProbs chart branding does not replace the underlying dataset attribution.
