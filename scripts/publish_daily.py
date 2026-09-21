"""Publish a validated snapshot, then atomically advance the pinned manifest."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from urllib.request import Request, urlopen

PROJECT = Path(__file__).resolve().parents[1]


def git(*args):
    return subprocess.check_output(['git', *args], cwd=PROJECT, text=True).strip()


def api(url, method='GET', data=None, size=None):
    if not url.startswith(('https://api.github.com/', 'https://uploads.github.com/')):
        raise ValueError('Unexpected GitHub API destination')
    headers = {'Authorization': 'Bearer ' + os.environ['GH_TOKEN'],
               'Accept': 'application/vnd.github+json', 'User-Agent': 'WxProbs-Daily-Refresh'}
    if isinstance(data, dict):
        data = json.dumps(data).encode()
        headers['Content-Type'] = 'application/json'
    elif data is not None:
        headers['Content-Type'] = 'application/gzip'
        headers['Content-Length'] = str(size)
    with urlopen(Request(url, data=data, headers=headers, method=method), timeout=300) as response:
        return json.load(response)


def validate_remote_asset(remote, path):
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    if (remote.get('state') != 'uploaded' or remote.get('size') != path.stat().st_size
            or remote.get('digest') != 'sha256:' + digest):
        raise ValueError('Uploaded release asset failed verification: ' + path.name)


def publish():
    result = json.loads((PROJECT / 'data/anm/refresh-result.json').read_text())
    if not result['changed']:
        print('No source changes; keeping the current release and deployment.')
        return None
    repo = os.environ['GITHUB_REPOSITORY']
    if repo != 'thghost75/Romanian-Climate-Explorer':
        raise ValueError('Unexpected publishing repository')
    base = 'https://api.github.com/repos/' + repo
    if not api(base)['private']:
        raise ValueError('This workflow requires the repository to remain private')
    expected = os.environ['GITHUB_SHA']
    git('fetch', 'origin', 'main')
    if git('rev-parse', 'origin/main') != expected or git('rev-parse', 'HEAD') != expected:
        raise ValueError('Main changed while updating; rerun against the new version')
    run_id = os.environ['GITHUB_RUN_ID']
    attempt = os.environ['GITHUB_RUN_ATTEMPT']
    if not run_id.isdigit() or not attempt.isdigit():
        raise ValueError('Invalid workflow run identity')
    tag = f'climate-auto-{run_id}-{attempt}'
    release = api(base + '/releases', 'POST', {
        'tag_name': tag, 'target_commitish': expected, 'draft': True,
        'name': 'Daily climate snapshot through ' + result['latest_observation'],
        'body': 'Validated daily refresh for WxProbs Romanian Climate Explorer.\n\n'
                'Source: ANM / MeteoRomania Open Data Portal.\n'
                'https://odp.meteoromania.ro/station_data_series/climate/daily/\n\n'
                'Only the current and previous calendar years are refreshed automatically. '
                'Historical observations and review notes are retained.\n\n' +
                '```json\n' + json.dumps(result, indent=2) + '\n```',
    })
    upload = release['upload_url'].split('{')[0]
    if not upload.startswith('https://uploads.github.com/repos/' + repo + '/releases/'):
        raise ValueError('Unexpected release upload destination')
    for name in ('climate.sqlite.gz', 'climatology.sqlite.gz'):
        path = PROJECT / 'release-assets' / name
        print('Uploading and verifying ' + name, flush=True)
        with path.open('rb') as stream:
            remote = api(upload + '?name=' + name, 'POST', stream, path.stat().st_size)
        validate_remote_asset(remote, path)
    api(base + '/releases/' + str(release['id']), 'PATCH', {'draft': False, 'make_latest': 'false'})
    manifest_path = PROJECT / 'snapshots/manifest.json'
    manifest = json.loads(manifest_path.read_text())
    manifest['base_url'] = 'https://github.com/' + repo + '/releases/download/' + tag
    manifest['refresh'] = result
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    public_status = {'release': tag, 'updated_at': result['checked_at'],
                     'latest_observation': result['latest_observation'],
                     'station_count': result['station_count'], 'schedule': 'Daily at 05:23 UTC'}
    (PROJECT / 'web/data-status.json').write_text(json.dumps(public_status, indent=2) + '\n', encoding='utf-8')
    # Attribute this user's scheduled automation to the repository owner so the
    # existing Vercel Hobby Git integration can recognize its authorized author.
    owner = api('https://api.github.com/users/thghost75')
    git('add', '--', 'snapshots/manifest.json', 'snapshots/candidate_review_notes.json', 'web/data-status.json')
    git('diff', '--cached', '--check')
    git('-c', 'user.name=thghost75', '-c', f"user.email={owner['id']}+thghost75@users.noreply.github.com",
        'commit', '-m', 'Refresh ANM observations through ' + result['latest_observation'])
    # No force push: concurrent user changes must win over this refresh.
    git('push', 'origin', 'HEAD:main')
    print('Published ' + tag + '; awaiting the connected Vercel deployment.', flush=True)
    return tag


def wait_for_production(tag, timeout=900):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            base = 'https://romanian-climate-explorer.vercel.app'
            with urlopen(base + '/data-status.json?release=' + tag, timeout=30) as response:
                status = json.load(response)
            if status.get('release') == tag:
                with urlopen(base + '/api/health', timeout=45) as response:
                    health = json.load(response)
                with urlopen(base + '/api/climate/stations', timeout=45) as response:
                    stations = json.load(response)
                # The catalogue response is an object with a stations list.
                catalogue = stations.get('stations', []) if isinstance(stations, dict) else stations
                if not health.get('data_ready') or len(catalogue) != status['station_count']:
                    raise ValueError('Production snapshot health/catalogue validation failed')
                print('Verified refreshed data on the public production site.', flush=True)
                return
        except (OSError, ValueError):
            pass
        time.sleep(20)
    raise RuntimeError('Snapshot published, but production did not pass verification within 15 minutes. Check the Vercel deployment; do not treat this run as successful.')


if __name__ == '__main__':
    tag = publish()
    if tag:
        wait_for_production(tag)
