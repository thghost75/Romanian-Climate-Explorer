# Public GitHub deployment on Vercel

The live site is https://romanian-climate-explorer.vercel.app/.
The source repository and its climate-data release attachments are public.
Daily updates are documented in [DAILY_UPDATES.md](DAILY_UPDATES.md).

## Build configuration

Import `thghost75/Romanian-Climate-Explorer` into Vercel using the repository
root and framework preset **Other**. The committed `vercel.json` specifies:

| Setting | Value |
| --- | --- |
| Install command | `npm ci --prefix frontend` |
| Build command | `python3 scripts/build_site.py` |
| Output directory | `dist` |
| Python version | `3.12` |
| Fluid compute | Enabled |

The build verifies the pinned data release, regenerates the annual dashboard from
that same snapshot, and compiles the React workspace. Each scheduled data-release
commit therefore refreshes both the API and the dashboard. `web/data-status.json`
is copied to `dist/data-status.json`, preserving the daily updater's verification.
See [DESIGN_HISTORY.md](DESIGN_HISTORY.md) for the preserved classic design and
instructions for reverting the frontend without reverting newer observations.

The complete verified archive is approximately 4 GB. Each build creates a compact
serving copy (approximately 2.2 GB at the September 2026 snapshot) and bundles only
that copy. It still requires Vercel Large Functions.
Set `VERCEL_SUPPORT_LARGE_FUNCTIONS=1` in Production and Preview.
If the importer disables that field, add it in the project's Environment Variables
settings after import, then redeploy.

The snapshot URL and SHA-256 checksums are pinned together in
`snapshots/manifest.json`. Public snapshots are fetched without authentication,
including when an obsolete `CLIMATE_GITHUB_TOKEN` remains in the environment.
Remove that old variable from Production and Preview. No replacement personal
token is required, and no credential is shipped to visitors.

`CLIMATE_SNAPSHOT_BASE_URL` is an optional fallback for older manifests. The
committed `base_url` takes precedence, so daily refreshes need no Vercel settings
changes. Do not set `CLIMATE_DATA_ROOT` on Vercel; it is a local testing option.

## Verify a deployment

The build logs must show both `SHA-256 verified` messages and
`Read-only climate snapshot ready.` Then check:

- `/api/health` returns `data_ready: true`.
- `/api/climate/stations` returns all 160 stations.
- `/data-status.json` identifies the published release and latest observation.
- Daily charts and PNG/SVG downloads work and retain **© WxProbs** and ANM attribution.

The serving databases are opened using immutable SQLite connections on Vercel. They stay
outside `web/` and are never exposed through the web API as database files. Their
complete archive release attachments are intentionally downloadable from the public GitHub repo.

## Automatic deployment cleanup

`scripts/prepare_runtime.py` creates fresh databases in `data/runtime` from the
verified `data/anm` archive on every build. It retains all dates and measurements,
the QC flags, review notes, displayed source references, and every statistical
table read by the public API. Ingestion logs, source-file preambles, duplicate raw
text, build-only threshold tables, and ingestion-only indexes stay in the full
archive and are omitted from the serving copy. No historical years are pruned.

The build verifies copied row counts and SQLite integrity, reports bytes saved,
and fails before deployment if serving data reaches 4.5 GB. Vercel's function
configuration includes only the two serving databases and review notes, excluding
the full source archive, staging directories, SQLite sidecars and temporary files.
Frontend builds also remove obsolete hashed JavaScript/CSS files from `dist`.
Run `python scripts/prepare_runtime.py` followed by the test suite to compare
public API responses with the complete local archive.

Keep the pinned GitHub data release and the classic-design rollback tag. Old
release attachments are not bundled into the Vercel function. This cleanup reduces
deployment size; traffic, compute and build-usage quotas are separate limits.

## Troubleshooting

- **Download failure / 404:** confirm the manifest's release is published and its
  two attachments are available publicly; draft releases are not public.
- **Checksum mismatch:** the release and manifest must come from the same packaging
  run. Do not overwrite old tagged assets.
- **Function too large:** check Large Functions is enabled and `data/anm` is
  excluded. The serving-copy guard stops at 4.5 GB to leave room in the 5 GB
  function. The complete release archive has a separate 4.8 GB packaging guard.
- **API 503:** inspect build logs and function data inclusion. Never move SQLite
  files into `web/` as a workaround.
- **Daily update failure:** inspect its Actions run; data checks must pass before
  publication. The GitHub workflow writes using its automatically issued token.

The site currently uses Vercel Hobby, subject to its usage limits and plan terms.
The computer running this local project is not needed for hosting or updates.

## Reference documentation

- [Public release downloads](https://docs.github.com/en/rest/releases/assets)
- [Vercel Large Functions](https://vercel.com/docs/functions/limitations)
- [Vercel environment variables](https://vercel.com/docs/environment-variables/managing-environment-variables)
- [GitHub scheduled workflows](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)

## Automatic refresh schedule

ANM is checked at **03:17, 09:17, 15:17 and 21:17 UTC** each day (06:17,
12:17, 18:17 and 00:17 in Romania during summer time). GitHub may delay or miss
an individual scheduled event; the later checks provide another attempt.
Each run downloads the current pinned release, checks the source, and publishes
only after validation. Production is verified before the run can succeed.
The workflow uses GitHub's short-lived built-in token, with no personal token to
renew. Its run summary and retained refresh diagnostics show the check time and
latest observation separately. Empty source days are not fabricated or marked
as imported. Inspect **Actions > Refresh daily ANM observations** for history.
Manual dispatch remains available for maintenance, but is not the normal updater.
