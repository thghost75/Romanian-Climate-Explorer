"""Standalone local website serving public assets and read-only climate queries."""
import argparse
import json
import socket
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen
import webbrowser

from .config import DEFAULT_ROOT
from .explorer_http import handle_climate

WEB = Path(__file__).resolve().parents[1] / "web"


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, data_root=DEFAULT_ROOT, **kwargs):
        self.data_root = Path(data_root)
        super().__init__(*args, directory=str(WEB), **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            body = json.dumps({"service": "romanian-climate-explorer", "data_root": str(self.data_root.resolve())}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if handle_climate(self, parsed.path, parsed.query, root=self.data_root):
            return
        super().do_GET()

    def list_directory(self, path):
        self.send_error(404)
        return None

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()


class StandaloneServer(ThreadingHTTPServer):
    # Windows SO_REUSEADDR can let a second server steal the same listener.
    allow_reuse_address = False
    allow_reuse_port = False

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def main():
    parser = argparse.ArgumentParser(description="Run the standalone Romanian Climate Explorer.")
    parser.add_argument("--port", type=int, default=4887)
    parser.add_argument("--data-root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--open-browser", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("Port must be between 1 and 65535")
    for relative in ("climate.sqlite", "climatology.sqlite", "processed/phase3/candidate_review_notes.json"):
        if not (args.data_root / relative).is_file():
            parser.error(f"Required climate data is missing: {args.data_root / relative}")
    url = f"http://127.0.0.1:{args.port}/"
    try:
        server = StandaloneServer(("127.0.0.1", args.port), partial(Handler, data_root=args.data_root))
    except OSError:
        try:
            with urlopen(url + "api/health", timeout=2) as response:
                health = json.load(response)
            same = health.get("service") == "romanian-climate-explorer" and health.get("data_root") == str(args.data_root.resolve())
        except Exception:
            same = False
        if not same:
            parser.error(f"Port {args.port} is unavailable; choose another --port.")
        print(f"Romanian Climate Explorer is already running: {url}", flush=True)
        if args.open_browser:
            webbrowser.open(url)
        return
    print(f"Romanian Climate Explorer: {url}", flush=True)
    print("Press Ctrl+C to stop. Climate databases are read-only.", flush=True)
    if args.open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
