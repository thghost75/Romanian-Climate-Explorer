"""Fetch and verify pinned data at build time, never on a visitor request."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

PROJECT = Path(__file__).resolve().parents[1]
NAMES = {'climate.sqlite', 'climatology.sqlite'}
CHUNK = 4 * 1024 * 1024


class HTTPSRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urlparse(newurl).scheme != 'https':
            raise ValueError('Snapshot redirect must remain HTTPS')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def snapshot_request(url, token=None, binary=False):
    request = Request(url, headers={
        'User-Agent': 'WxProbs-Climate-Build/1.0',
        'Accept': 'application/octet-stream' if binary else 'application/vnd.github+json',
    })
    if token:
        parsed = urlparse(url)
        if parsed.scheme != 'https' or parsed.netloc != 'api.github.com':
            raise ValueError('GitHub credentials may only be sent to api.github.com')
        # Signed storage redirects must never receive the GitHub credential.
        request.add_unredirected_header('Authorization', 'Bearer ' + token)
    return request


def github_asset_urls(base_url, token, opener):
    parsed = urlparse(base_url)
    parts = parsed.path.strip('/').split('/')
    if parsed.scheme != 'https' or parsed.netloc != 'github.com' or len(parts) != 5 or parts[2:4] != ['releases', 'download']:
        raise ValueError('Private snapshots require a github.com release-download URL')
    repo = '/'.join(quote(unquote(part), safe='') for part in parts[:2])
    tag = quote(unquote(parts[4]), safe='')
    url = 'https://api.github.com/repos/' + repo + '/releases/tags/' + tag
    try:
        with opener.open(snapshot_request(url, token), timeout=120) as source:
            release = json.load(source)
    except (HTTPError, URLError, TimeoutError, ConnectionError):
        raise RuntimeError('Cannot read private snapshot release. Check CLIMATE_GITHUB_TOKEN has Contents: read access to this repository.') from None
    assets = {}
    for asset in release.get('assets', []):
        asset_id = asset.get('id')
        if isinstance(asset_id, int) and asset.get('state') == 'uploaded':
            assets[asset['name']] = 'https://api.github.com/repos/' + repo + '/releases/assets/' + str(asset_id)
    return assets


def file_digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as source:
        while chunk := source.read(CHUNK):
            result.update(chunk)
    return result.hexdigest()


def install_stream(compressed, target, entry):
    """Atomic bounded extraction of one gzip stream; no archive paths accepted."""
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + '.part')
    count = 0
    digest = hashlib.sha256()
    try:
        with gzip.GzipFile(fileobj=compressed, mode='rb') as source, partial.open('wb') as output:
            while chunk := source.read(CHUNK):
                count += len(chunk)
                if count > entry['bytes']:
                    raise ValueError('Snapshot exceeds its pinned size: ' + entry['name'])
                digest.update(chunk)
                output.write(chunk)
        if count != entry['bytes'] or digest.hexdigest() != entry['sha256']:
            raise ValueError('Snapshot checksum or size mismatch: ' + entry['name'])
        partial.replace(target)
    finally:
        partial.unlink(missing_ok=True)


def fetch(base_url=None, asset_dir=None, destination=None):
    manifest = json.loads((PROJECT / 'snapshots/manifest.json').read_text(encoding='utf-8'))
    entries = manifest['files']
    if manifest.get('version') != 1 or len(entries) != 2 or {e['name'] for e in entries} != NAMES:
        raise ValueError('Unexpected snapshot manifest')
    for entry in entries:
        if entry['asset'] != entry['name'] + '.gz' or not isinstance(entry['bytes'], int) or not 0 < entry['bytes'] < 5_000_000_000:
            raise ValueError('Invalid snapshot asset')
    if sum(e['bytes'] for e in entries) >= 4_800_000_000:
        raise ValueError('Snapshot leaves insufficient room in a 5 GB function')
    destination = Path(destination or PROJECT / 'data/anm')
    opener = build_opener(HTTPSRedirectHandler())
    # Public releases need no credentials. Ignore obsolete/expired Vercel tokens
    # for a public snapshot, rather than allowing them to break anonymous access.
    token = os.environ.get('CLIMATE_GITHUB_TOKEN', '').strip() if asset_dir is None and not manifest.get('public', False) else ''
    private_assets = None
    if asset_dir is None:
        # A committed release URL travels atomically with its matching checksums.
        # The environment variable remains a fallback for the original snapshot.
        base_url = (base_url or manifest.get('base_url') or os.environ.get('CLIMATE_SNAPSHOT_BASE_URL', '')).rstrip('/')
        parsed = urlparse(base_url)
        if parsed.scheme != 'https' or not parsed.netloc or parsed.query or parsed.fragment or parsed.username or parsed.password:
            raise ValueError('Set CLIMATE_SNAPSHOT_BASE_URL to an HTTPS release-download directory. See DEPLOY.md.')
        if token:
            private_assets = github_asset_urls(base_url, token, opener)
    for entry in entries:
        target = destination / entry['name']
        if target.is_file() and target.stat().st_size == entry['bytes'] and file_digest(target) == entry['sha256']:
            print('Verified existing ' + entry['name'], flush=True)
            continue
        print('Preparing ' + entry['name'], flush=True)
        if asset_dir is not None:
            with (Path(asset_dir) / entry['asset']).open('rb') as source:
                install_stream(source, target, entry)
        else:
            asset_url = base_url + '/' + entry['asset']
            if private_assets is not None:
                asset_url = private_assets.get(entry['asset'])
                if not asset_url:
                    raise RuntimeError('Private release is missing ' + entry['asset'])
            for attempt in range(3):
                try:
                    request = snapshot_request(asset_url, token, binary=True)
                    with opener.open(request, timeout=120) as source:
                        if urlparse(source.geturl()).scheme != 'https':
                            raise ValueError('Snapshot redirect must remain HTTPS')
                        install_stream(source, target, entry)
                    break
                except (HTTPError, URLError, TimeoutError, ConnectionError) as error:
                    retryable = not isinstance(error, HTTPError) or error.code in (429, 500, 502, 503, 504)
                    if attempt == 2 or not retryable:
                        raise RuntimeError('Snapshot download failed for ' + entry['asset'] + '; check the release URL, assets and private-repository token.') from None
                    time.sleep(2 ** attempt)
        print('SHA-256 verified: ' + entry['name'], flush=True)
    notes = PROJECT / 'snapshots/candidate_review_notes.json'
    if file_digest(notes) != manifest['review_notes_sha256']:
        raise ValueError('Review notes checksum mismatch')
    notes_target = destination / 'processed/phase3/candidate_review_notes.json'
    notes_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(notes, notes_target)
    print('Read-only climate snapshot ready.', flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--asset-dir', type=Path, help='Use local release assets instead of HTTPS, for verification.')
    parser.add_argument('--destination', type=Path)
    args = parser.parse_args()
    try:
        fetch(asset_dir=args.asset_dir, destination=args.destination)
    except (ValueError, RuntimeError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
