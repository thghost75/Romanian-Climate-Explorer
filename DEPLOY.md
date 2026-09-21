# Public GitHub deployment on Vercel

The live site is https://romanian-climate-explorer.vercel.app/.
The source repository and its climate-data release attachments are public.
Daily updates are documented in [DAILY_UPDATES.md](DAILY_UPDATES.md).

## Build configuration

Import `thghost75/Romanian-Climate-Explorer` into Vercel using the repository
root and framework preset **Other**. The committed `vercel.json` specifies:

| Setting | Value |
| --- | --- |
| Install command | `python3 --version` |
| Build command | `python3 scripts/fetch_snapshot.py` |
| Output directory | `web` |
| Python version | `3.12` |
| Fluid compute | Enabled |

The verified databases are approximately 4 GB combined and require Vercel Large
Functions. Set `VERCEL_SUPPORT_LARGE_FUNCTIONS=1` in Production and Preview.
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

The databases are opened using immutable SQLite connections on Vercel. They stay
outside `web/` and are never exposed through the web API as database files. Their
release attachments are intentionally downloadable from the public GitHub repo.

## Troubleshooting

- **Download failure / 404:** confirm the manifest's release is published and its
  two attachments are available publicly; draft releases are not public.
- **Checksum mismatch:** the release and manifest must come from the same packaging
  run. Do not overwrite old tagged assets.
- **Function too large:** check Large Functions is enabled. The packaging guard
  stops snapshots at 4.8 GB to leave space in the 5 GB function.
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
