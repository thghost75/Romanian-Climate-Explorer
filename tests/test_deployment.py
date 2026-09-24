import gzip
import hashlib
from http.server import ThreadingHTTPServer
import io
import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from api.index import handler
from anm_climate.explorer_api import readonly
from anm_climate.phase3_api import ClimatologyStore
from scripts.fetch_snapshot import HTTPSRedirectHandler, github_asset_urls, install_stream, snapshot_request, fetch
from scripts.publish_daily import validate_remote_asset, publish

TEST_TMP = Path(__file__).resolve().parent / '_tmp'
TEST_TMP.mkdir(exist_ok=True)


class PrivateReleaseTests(unittest.TestCase):
    def test_credentials_are_removed_from_storage_redirect(self):
        request = snapshot_request('https://api.github.com/repos/o/r/releases/assets/1', 'test-token', True)
        self.assertEqual(request.get_header('Authorization'), 'Bearer test-token')
        redirected = HTTPSRedirectHandler().redirect_request(
            request, None, 302, 'Found', {}, 'https://release-assets.githubusercontent.com/asset')
        self.assertIsNone(redirected.get_header('Authorization'))
        with self.assertRaises(ValueError):
            HTTPSRedirectHandler().redirect_request(request, None, 302, 'Found', {}, 'http://example.com/asset')

    def test_credentials_cannot_be_sent_to_another_host(self):
        for url in ['https://example.com/a', 'https://api.github.com.evil.test/a', 'http://api.github.com/a']:
            with self.assertRaises(ValueError):
                snapshot_request(url, 'test-token')

    def test_private_assets_use_authenticated_api_not_download_links(self):
        opener = Mock()
        opener.open.return_value = io.BytesIO(json.dumps({'assets': [
            {'id': 42, 'name': 'climate.sqlite.gz', 'state': 'uploaded', 'url': 'https://untrusted.test/a'}
        ]}).encode())
        assets = github_asset_urls('https://github.com/owner/repo/releases/download/tag', 'test-token', opener)
        self.assertEqual(assets, {'climate.sqlite.gz': 'https://api.github.com/repos/owner/repo/releases/assets/42'})
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, 'https://api.github.com/repos/owner/repo/releases/tags/tag')
        self.assertEqual(request.get_header('Authorization'), 'Bearer test-token')
        with self.assertRaises(ValueError):
            github_asset_urls('https://example.com/owner/repo/releases/download/tag', 'test-token', opener)


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=TEST_TMP)
        self.addCleanup(self.directory.cleanup)
        self.target = Path(self.directory.name) / 'climate.sqlite'
        self.payload = b'SQLite test payload' * 100
        self.entry = {'name': self.target.name, 'bytes': len(self.payload),
                      'sha256': hashlib.sha256(self.payload).hexdigest()}

    def test_valid_snapshot_is_installed_exactly(self):
        install_stream(io.BytesIO(gzip.compress(self.payload)), self.target, self.entry)
        self.assertEqual(self.target.read_bytes(), self.payload)

    def test_committed_release_overrides_stale_environment_url(self):
        project = Path(self.directory.name)
        (project / 'snapshots').mkdir()
        manifest = {'version': 1, 'base_url': 'https://github.com/o/r/releases/download/new', 'files': [
            {'name': name, 'asset': name + '.gz', 'bytes': 10}
            for name in ('climate.sqlite', 'climatology.sqlite')]}
        (project / 'snapshots/manifest.json').write_text(json.dumps(manifest))
        with patch('scripts.fetch_snapshot.PROJECT', project), patch.dict(os.environ, {
            'CLIMATE_GITHUB_TOKEN': 'test-token',
            'CLIMATE_SNAPSHOT_BASE_URL': 'https://github.com/o/r/releases/download/old'}), patch(
                'scripts.fetch_snapshot.github_asset_urls', side_effect=RuntimeError('stop before download')) as resolve:
            with self.assertRaisesRegex(RuntimeError, 'stop before download'):
                fetch()
        self.assertEqual(resolve.call_args.args[0], manifest['base_url'])

    def test_public_snapshot_download_ignores_expired_personal_token(self):
        project = Path(self.directory.name)
        (project / 'snapshots').mkdir()
        notes = b'[]'
        manifest = {'version': 1, 'public': True,
            'base_url': 'https://github.com/o/r/releases/download/public',
            'review_notes_sha256': hashlib.sha256(notes).hexdigest(),
            'files': [{'name': name, 'asset': name + '.gz', 'bytes': len(self.payload),
                       'sha256': hashlib.sha256(self.payload).hexdigest()}
                      for name in ('climate.sqlite', 'climatology.sqlite')]}
        (project / 'snapshots/manifest.json').write_text(json.dumps(manifest))
        (project / 'snapshots/candidate_review_notes.json').write_bytes(notes)
        requests = []
        def open_public(request, **kwargs):
            requests.append(request)
            response = io.BytesIO(gzip.compress(self.payload))
            response.geturl = lambda: 'https://release-assets.githubusercontent.com/public-asset'
            return response
        opener = Mock()
        opener.open.side_effect = open_public
        with patch('scripts.fetch_snapshot.PROJECT', project), patch.dict(os.environ, {
            'CLIMATE_GITHUB_TOKEN': 'obsolete-expired-token'}), patch(
                'scripts.fetch_snapshot.build_opener', return_value=opener), patch(
                'scripts.fetch_snapshot.github_asset_urls') as private_api:
            fetch()
        private_api.assert_not_called()
        self.assertEqual(len(requests), 2)
        self.assertTrue(all(r.get_header('Authorization') is None for r in requests))
        self.assertEqual((project / 'data/anm/climate.sqlite').read_bytes(), self.payload)

    def test_remote_asset_digest_must_match_before_publication(self):
        self.target.write_bytes(self.payload)
        remote = {'state': 'uploaded', 'size': len(self.payload),
                  'digest': 'sha256:' + hashlib.sha256(self.payload).hexdigest()}
        validate_remote_asset(remote, self.target)
        with self.assertRaisesRegex(ValueError, 'verification'):
            validate_remote_asset({**remote, 'digest': 'sha256:bad'}, self.target)

    def test_unchanged_source_still_requires_production_verification(self):
        project = Path(self.directory.name)
        (project / 'data/anm').mkdir(parents=True)
        (project / 'web').mkdir()
        (project / 'data/anm/refresh-result.json').write_text('{"changed": false}')
        (project / 'web/data-status.json').write_text('{"release": "current-release"}')
        with patch('scripts.publish_daily.PROJECT', project), patch('scripts.publish_daily.api') as remote:
            self.assertEqual(publish(), 'current-release')
        remote.assert_not_called()

    def test_corrupt_snapshot_preserves_existing_file_and_removes_partial(self):
        self.target.write_bytes(b'existing')
        with self.assertRaises(ValueError):
            install_stream(io.BytesIO(gzip.compress(b'x' * len(self.payload))), self.target, self.entry)
        self.assertEqual(self.target.read_bytes(), b'existing')
        self.assertFalse(self.target.with_suffix('.sqlite.part').exists())

    def test_decompression_cannot_exceed_manifest_size(self):
        with self.assertRaises(ValueError):
            install_stream(io.BytesIO(gzip.compress(self.payload * 2)), self.target, self.entry)
        self.assertFalse(self.target.exists())

    def test_deployed_wal_snapshot_never_creates_sidecar_files(self):
        with closing(sqlite3.connect(self.target)) as writer:
            writer.execute('PRAGMA journal_mode=WAL')
            writer.execute('CREATE TABLE metadata (key TEXT, value TEXT)')
            writer.executemany('INSERT INTO metadata VALUES (?, ?)', [('policy', '{}'), ('state', '"complete"')])
            writer.commit()
            writer.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        self.assertEqual(self.target.read_bytes()[18:20], b'\x02\x02')
        before = set(self.target.parent.iterdir())
        with patch.dict(os.environ, {'VERCEL': '1'}):
            with closing(readonly(self.target)) as source, ClimatologyStore(self.target) as products:
                self.assertEqual(source.execute('SELECT COUNT(*) FROM metadata').fetchone()[0], 2)
                self.assertEqual(products.policy, {})
                self.assertEqual(set(self.target.parent.iterdir()), before)
                with self.assertRaises(sqlite3.OperationalError):
                    products.db.execute('DELETE FROM metadata')


class QuietHandler(handler):
    def log_message(self, *args):
        pass


class RoutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), QuietHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = 'http://127.0.0.1:' + str(cls.server.server_port)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def request(self, path):
        try:
            response = urlopen(self.url + path, timeout=5)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response)

    def test_rewritten_and_direct_routes_keep_station_parameters(self):
        def fake(h, path, query, root):
            h.json_response(200, {'path': path, 'query': query})
        with patch('api.index.handle_climate', fake):
            for path in ['/api?__climate_endpoint=overview&station=ABC&year=2025',
                         '/api/climate/overview?station=ABC&year=2025',
                         '/api/climate/overview?__climate_endpoint=overview&station=ABC&year=2025',
                         '/api/climate/overview?__climate_endpoint=overview&endpoint=overview&station=ABC&year=2025']:
                status, body = self.request(path)
                self.assertEqual(status, 200)
                self.assertEqual(body, {'path': '/api/climate/overview', 'query': 'station=ABC&year=2025'})

    def test_vercel_reads_compact_runtime_snapshot(self):
        def fake(h, path, query, root):
            h.json_response(200, {'folder': root.name})
        with patch.dict(os.environ, {'VERCEL': '1'}), patch('api.index.handle_climate', fake):
            with patch.dict(os.environ):
                os.environ.pop('CLIMATE_DATA_ROOT', None)
                self.assertEqual(self.request('/api/climate/stations'), (200, {'folder': 'runtime'}))

    def test_ambiguous_or_invalid_routes_are_rejected(self):
        for path in ['/api?__climate_endpoint=a&__climate_endpoint=b',
                     '/api/climate/stations?__climate_endpoint=overview',
                     '/api/climate/stations?endpoint=overview',
                     '/api/climate/stations?endpoint=stations&endpoint=stations',
                     '/api?__climate_endpoint=../data']:
            self.assertEqual(self.request(path)[0], 400)

    def test_private_files_are_not_routes(self):
        for path in ['/data/anm/climate.sqlite', '/anm_climate/config.py', '/api']:
            self.assertEqual(self.request(path)[0], 404)

    def test_visit_routes_keep_cache_and_cookie_headers(self):
        with patch('api.index.visit_response', return_value=(200, {'visits': 17}, {
                'Cache-Control': 'no-store', 'Set-Cookie': 'test=1; HttpOnly'})) as visits:
            for path in ['/api/visits', '/api?__climate_endpoint=visits']:
                with urlopen(Request(self.url + path, data=b'', method='POST'), timeout=5) as response:
                    self.assertEqual(json.load(response), {'visits': 17})
                    self.assertEqual(response.headers['Cache-Control'], 'no-store')
                    self.assertEqual(response.headers['Set-Cookie'], 'test=1; HttpOnly')
                self.assertEqual(visits.call_args.args[0], 'POST')
            self.assertEqual(self.request('/api/visits'), (200, {'visits': 17}))
            self.assertEqual(visits.call_args.args[0], 'GET')

    def test_climate_post_remains_read_only(self):
        with patch('api.index.handle_climate') as climate:
            with self.assertRaises(HTTPError) as error:
                urlopen(Request(self.url + '/api/climate/stations', data=b'', method='POST'), timeout=5)
            self.assertEqual(error.exception.code, 405)
            error.exception.close()
            climate.assert_not_called()

    def test_health_reports_missing_data_without_local_paths(self):
        with tempfile.TemporaryDirectory(dir=TEST_TMP) as folder, patch.dict(os.environ, {'CLIMATE_DATA_ROOT': folder}):
            for path in ['/api/health', '/api?__climate_endpoint=health']:
                status, data = self.request(path)
                self.assertEqual(status, 503)
                self.assertEqual(data, {'service': 'romanian-climate-explorer', 'data_ready': False})

    def test_health_rejects_present_but_unreadable_databases(self):
        with tempfile.TemporaryDirectory(dir=TEST_TMP) as folder, patch.dict(os.environ, {'CLIMATE_DATA_ROOT': folder}):
            root = Path(folder)
            (root / 'climate.sqlite').write_bytes(b'not a database')
            (root / 'climatology.sqlite').write_bytes(b'not a database')
            notes = root / 'processed/phase3/candidate_review_notes.json'
            notes.parent.mkdir(parents=True)
            notes.write_text('[]')
            self.assertEqual(self.request('/api/health'), (503, {'service': 'romanian-climate-explorer', 'data_ready': False}))

    @unittest.skipUnless((Path(__file__).resolve().parents[1] / 'data/anm/climatology.sqlite').exists(), 'Snapshot required')
    def test_real_snapshot_through_vercel_entrypoint(self):
        self.assertEqual(self.request('/api/health'), (200, {'service': 'romanian-climate-explorer', 'data_ready': True}))
        status, stations = self.request('/api?__climate_endpoint=stations')
        self.assertEqual(status, 200)
        self.assertEqual(len(stations), 160)
        status, daily = self.request('/api?__climate_endpoint=daily-year&station=0-20000-0-15420&year=2025')
        self.assertEqual(status, 200)
        self.assertEqual(len(daily['days']), 365)
        self.assertEqual(self.request('/api?__climate_endpoint=overview&station=x&station=y')[0], 400)


if __name__ == '__main__':
    unittest.main()
