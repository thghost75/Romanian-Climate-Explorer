import gzip
import hashlib
from http.server import ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import urlopen

from api.index import handler
from scripts.fetch_snapshot import HTTPSRedirectHandler, github_asset_urls, install_stream, snapshot_request

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
                         '/api/climate/overview?__climate_endpoint=overview&station=ABC&year=2025']:
                status, body = self.request(path)
                self.assertEqual(status, 200)
                self.assertEqual(body, {'path': '/api/climate/overview', 'query': 'station=ABC&year=2025'})

    def test_ambiguous_or_invalid_routes_are_rejected(self):
        for path in ['/api?__climate_endpoint=a&__climate_endpoint=b',
                     '/api/climate/stations?__climate_endpoint=overview',
                     '/api?__climate_endpoint=../data']:
            self.assertEqual(self.request(path)[0], 400)

    def test_private_files_are_not_routes(self):
        for path in ['/data/anm/climate.sqlite', '/anm_climate/config.py', '/api']:
            self.assertEqual(self.request(path)[0], 404)

    def test_health_reports_missing_data_without_local_paths(self):
        with tempfile.TemporaryDirectory(dir=TEST_TMP) as folder, patch.dict(os.environ, {'CLIMATE_DATA_ROOT': folder}):
            for path in ['/api/health', '/api?__climate_endpoint=health']:
                status, data = self.request(path)
                self.assertEqual(status, 503)
                self.assertEqual(data, {'service': 'romanian-climate-explorer', 'data_ready': False})

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
