"""Vercel entrypoint: same read-only climate service, no local server startup."""
import json
import os
import re
import sqlite3
from contextlib import closing
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse

from anm_climate.config import DEFAULT_ROOT
from anm_climate.explorer_http import handle_climate
from anm_climate.explorer_api import readonly
from anm_climate.visit_counter import visit_response

REQUIRED_FILES = ('climate.sqlite', 'climatology.sqlite', 'processed/phase3/candidate_review_notes.json')


class handler(BaseHTTPRequestHandler):
    def json_response(self, status, payload, headers=None):
        body = json.dumps(payload).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        for name, value in (headers or {'Cache-Control': 'no-store'}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self.dispatch('GET')

    def dispatch(self, method):
        parsed = urlparse(self.path)
        try:
            if len(parsed.query) > 2300:
                raise ValueError('Query is too long')
            pairs = parse_qsl(parsed.query, keep_blank_values=True, max_num_fields=18)
            routed = [v for k, v in pairs if k == '__climate_endpoint']
            captured = [v for k, v in pairs if k == 'endpoint']
            if len(routed) > 1 or len(captured) > 1:
                raise ValueError('Ambiguous endpoint')
            # Support both Vercel's rewritten URL and direct local HTTP requests.
            if parsed.path.startswith('/api/climate/'):
                endpoint = parsed.path[len('/api/climate/'):]
            elif parsed.path == '/api/health':
                endpoint = 'health'
            elif parsed.path == '/api/visits':
                endpoint = 'visits'
            elif parsed.path in ('/api', '/api/', '/api/index', '/api/index.py') and routed:
                endpoint = routed[0]
            else:
                self.json_response(404, {'error': 'Unknown route'})
                return
            if (not re.fullmatch(r'[a-z-]+', endpoint)
                    or (routed and routed[0] != endpoint)
                    or (captured and captured[0] != endpoint)):
                raise ValueError('Invalid endpoint')
            if endpoint == 'visits':
                self.json_response(*visit_response(method, self.headers))
                return
            if method != 'GET':
                self.json_response(405, {'error': 'Climate data is read-only. Use GET.'})
                return
            serving_root = DEFAULT_ROOT.parent / 'runtime' if os.environ.get('VERCEL') == '1' else DEFAULT_ROOT
            root = Path(os.environ.get('CLIMATE_DATA_ROOT', str(serving_root)))
            if endpoint == 'health':
                ready = all((root / name).is_file() for name in REQUIRED_FILES)
                if ready:
                    try:
                        for name in REQUIRED_FILES[:2]:
                            with closing(readonly(root / name)) as database:
                                database.execute('SELECT name FROM sqlite_master LIMIT 1').fetchone()
                    except (sqlite3.Error, OSError):
                        ready = False
                self.json_response(200 if ready else 503, {
                    'service': 'romanian-climate-explorer', 'data_ready': ready,
                })
                return
            # Vercel also forwards the named :endpoint path capture as a query.
            query = urlencode([(k, v) for k, v in pairs if k not in ('__climate_endpoint', 'endpoint')])
            handle_climate(self, '/api/climate/' + endpoint, query, root=root)
        except ValueError as error:
            self.json_response(400, {'error': str(error)})

    def do_POST(self):
        self.dispatch('POST')
