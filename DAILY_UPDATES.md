# Daily observations update

The private repository runs **Refresh daily ANM observations** in GitHub Actions
at **05:23 UTC every day** (08:23 in Romanian summer time, 07:23 in winter).
GitHub may delay scheduled jobs; this is a daily check, not an exact publication
time or a guarantee that ANM has published yesterday's observations.

The workflow can also be started with **Actions → Refresh daily ANM observations
→ Run workflow → main**. No local computer or Codex session is required.

Each run:

1. Tests the updater and downloads the last checksum-verified snapshot.
2. Fetches ANM's current and previous calendar-year archives for the existing
   160 stations, sequentially with at least one second between requests.
3. Rejects invalid keys, future measurements and losses of existing measurements.
   Suspect finite measurements retain the existing variable-level QC policy.
4. Rebuilds all products for changed stations from their full history: records,
   QC exclusions, normals, monthly/annual summaries, indices and events.
5. Checks both SQLite databases, runs the website/API tests, checkpoints and
   compresses the result, then verifies the uploaded release attachments.
6. Commits the new release URL and matching checksums together. Vercel deploys
   through the existing Git integration. The run verifies the public production
   release, API health and station catalogue before reporting success.

If nothing changed, no new release or deployment is made, but the existing
production release is still checked so an earlier deployment failure cannot
silently appear as a successful update. A download, data-quality
or validation failure prevents publication and leaves the previous live snapshot
in place. If a later Vercel build fails, its previous successful deployment stays
live and the update workflow reports failure. The updater never force-pushes over
user changes. A concurrent main-branch update makes it stop and require a rerun.

The immutable dated original release and historical review notes are retained.
New generated releases are kept as rollback snapshots. The daily process does
not discover new stations or recheck corrections older than the previous year;
those need a separate historical refresh and review.

## Credentials and limits

GitHub uses its short-lived workflow `GITHUB_TOKEN` with repository Contents write
permission to publish private release assets and the pinned manifest. It does
not store a new long-lived write token. Vercel still needs the existing read-only
`CLIMATE_GITHUB_TOKEN` to download private assets at build time. Replace that token
before it expires; a failed token blocks new builds, not the existing deployment.

The Vercel environment's original `CLIMATE_SNAPSHOT_BASE_URL` is now only a
fallback. A release URL in `snapshots/manifest.json` takes precedence, so each
successful update no longer needs an environment-variable edit.

Runs use GitHub Actions minutes and Vercel build resources within the account's
quotas. Each run has a 45-minute maximum; unchanged runs skip packaging and
deployment. No paid plan or spending limit is enabled by this workflow. Databases
must remain below 4.8 GB combined to leave room in the 5 GB function. If they
outgrow that allowance, the updater stops rather than publishing unusable data.

Check the Actions run summary for observation dates and changed station counts.
Failed-run notifications follow your GitHub notification settings. The site
footer and `/data-status.json` identify the latest published observation date.

## Recovery

For a transient ANM or network failure, rerun the workflow. For source losses or
format changes, inspect the failed step before changing validation rules. To roll
back the public site, promote the previous successful deployment in Vercel; to
roll back future builds, restore the matching earlier manifest and public status
file in Git. Never overwrite an existing release's database attachments.
