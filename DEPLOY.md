# Publish the repository, then deploy on Vercel

## 1. Put the source code on GitHub

Use **only this `github-ready` folder** as the repository root. Do not publish
the parent working folder or the original E: drive archive project.

With GitHub Desktop, choose **File → Add local repository**, select this folder,
enter an initial commit summary such as `Prepare Climate Explorer for Vercel`,
choose **Commit to main**, then **Publish repository**. Alternatively, create an empty repository on GitHub
and follow its instructions to push this local repository. The suggested name
is `romanian-climate-explorer`; any name works.

If using GitHub's file uploader, extract the supplied source ZIP and upload its
contents, not the ZIP itself. `vercel.json`, `api/`, `web/`, `anm_climate/`,
`scripts/` and `snapshots/` must be at the repository root. Include hidden files
such as `.python-version`, `.gitignore`, and `.github/` (GitHub Desktop handles
these more reliably).

Keep all `.sqlite`, `.gz`, raw archives, backups and secrets out of Git.

## 2. Attach the prepared data to a GitHub Release

The repository and its release assets stay **private**. The build uses GitHub's
release API with a read-only token; credentials are never sent to redirected
download hosts or included in frontend files.

In the chosen data repository, open **Releases → Draft a new release**:

- Tag: `climate-2026-09-17`
- Title: `ANM climate snapshot through 17 September 2026`
- Attach both files from the supplied `release-assets` folder:
  - `climate.sqlite.gz` (about 414 MB)
  - `climatology.sqlite.gz` (about 235 MB)
- Include the ANM source attribution from the README in the release description.
- Publish the release; do not leave it as a draft.

These are release attachments, **not files added to the repository**. Each is
below GitHub's 2 GiB per-asset limit. The build decompresses them to approximately
3.99 GB and checks every byte against the committed SHA-256 manifest.

## 3. Import the code repository into Vercel

Choose **Add New → Project**, import your GitHub code repository, and keep the
Root Directory at the repository root. Select framework preset **Other**.

The committed `vercel.json` provides:

| Setting | Value |
| --- | --- |
| Install command | `python3 --version` |
| Build command | `python3 scripts/fetch_snapshot.py` |
| Output directory | `web` |
| Python version | `3.12` (from `.python-version`) |
| Fluid compute | Enabled |

Before clicking **Deploy**, add these environment variables for Production and
Preview:

| Name | Value |
| --- | --- |
| `CLIMATE_SNAPSHOT_BASE_URL` | `https://github.com/thghost75/Romanian-Climate-Explorer/releases/download/climate-2026-09-17` |
| `CLIMATE_GITHUB_TOKEN` | A fine-grained GitHub token with **Contents: Read-only** for **Romanian-Climate-Explorer** only |
| `VERCEL_SUPPORT_LARGE_FUNCTIONS` | `1` |

Create the token in GitHub **Settings → Developer settings → Personal access
tokens → Fine-grained tokens**. Select only this repository and give it only
**Contents: Read-only** permission (Metadata read access is automatic). Set an
appropriate expiry and replace the token in Vercel before future builds if it
expires. Paste it directly into Vercel's sensitive environment-variable field;
never commit it or put it in a `NEXT_PUBLIC_`/`VITE_` variable. Importing a private
repository into Vercel does not automatically authenticate this custom downloader.

Do not append a filename to the release URL. Do not set
`CLIMATE_DATA_ROOT` on Vercel; that option is only useful for local tests.

Now deploy. The build downloads about 650 MB; its logs should show both
`SHA-256 verified` messages and `Read-only climate snapshot ready.`

## 4. Check the deployed site

Open `/api/health` on your Vercel URL. A ready deployment returns:

```json
{"service":"romanian-climate-explorer","data_ready":true}
```

Then check `/api/climate/stations`, which should return 160 stations. Open the
home page, select a station and test History, On This Day and image downloads.
Exported PNG and SVG charts should show **© WxProbs** as well as ANM attribution.

## If the first deployment fails

- **Missing snapshot URL:** add `CLIMATE_SNAPSHOT_BASE_URL` to the deployment's
  environment and redeploy.
- **Cannot read private snapshot / 404:** check the repository, release tag,
  attachment filenames and `CLIMATE_GITHUB_TOKEN`. The token must be unexpired
  and have Contents read access to this repository. Publish the data release.
- **Checksum mismatch:** the release files and committed manifest must come from
  the same packaging run. Restore the matching assets or package a new version.
- **500 MB bundle limit:** verify Fluid compute and Large Functions are enabled.
  This app needs the 5 GB beta path. If your account cannot use it, the current
  full-data deployment cannot proceed there; a separate data host or smaller
  serving snapshot would be needed.
- **API 503:** the data files were not included or could not be read. Check the
  build logs and function bundle configuration; never move the databases into
  `web/` to make them accessible.

The local packaging and API checks do not prove Vercel performance or Hobby
eligibility. The first hosted deployment still needs the checks above. The free
plan is for personal, non-commercial use and has CPU, transfer and request
limits. Your computer can be switched off once the cloud deployment succeeds.

## Reference documentation

- [Vercel Python API functions](https://vercel.com/docs/functions/runtimes/python/api-directory)
- [Vercel Large Functions and limits](https://vercel.com/docs/functions/limitations)
- [Vercel configuration](https://vercel.com/docs/project-configuration/vercel-json)
- [Vercel Hobby plan](https://vercel.com/docs/plans/hobby)
- [GitHub release asset limits](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases)
- [GitHub private release downloads and permissions](https://docs.github.com/en/rest/releases/assets#get-a-release-asset)
