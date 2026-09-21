"""Sequential, rate-limited HTTP with bounded retries."""
import json
import http.client
import logging
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
import os

LOG = logging.getLogger(__name__)

def utc_now():
    return datetime.now(timezone.utc).isoformat()

def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_suffix(path.suffix + ".tmp")
    part.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    os.replace(part, path)

class HttpClient:
    def __init__(self, root, interval=1.0, timeout=30, retries=4):
        self.root = Path(root)
        self.interval = max(0.1, interval)
        self.timeout = timeout
        self.retries = retries
        self.last_request = 0.0
        self.not_before = 0.0

    def error(self, operation, url, error):
        path = self.root / "logs" / "errors.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"time": utc_now(), "operation": operation, "url": url,
                                "error": str(error)}, ensure_ascii=False) + "\n")
        LOG.error("%s %s: %s", operation, url, error)

    def open(self, url, headers=None):
        time.sleep(max(0, self.interval - (time.monotonic() - self.last_request), self.not_before - time.monotonic()))
        self.last_request = time.monotonic()
        request = urllib.request.Request(url, headers={
            "User-Agent": "WeatherViewer-ANMClimate/0.1 (sequential archive research)",
            "Accept-Encoding": "identity", **(headers or {}),
        })
        return urllib.request.urlopen(request, timeout=self.timeout)

    def retryable(self, error):
        return not isinstance(error, urllib.error.HTTPError) or error.code in (408, 429, 500, 502, 503, 504)

    def backoff(self, attempt, error):
        delay = min(30, 2 ** attempt)
        if isinstance(error, urllib.error.HTTPError):
            value = error.headers.get("Retry-After")
            if value:
                try:
                    delay = max(delay, float(value))
                except ValueError:
                    try:
                        delay = max(delay, parsedate_to_datetime(value).timestamp() - time.time())
                    except (ValueError, TypeError):
                        pass
        if delay > 60:
            self.not_before = time.monotonic() + delay
            raise RuntimeError(f"Server requested a {delay:.0f}s pause; rerun later") from error
        LOG.warning("Retry in %.1fs: %s", delay, error)
        time.sleep(max(0, delay))

    def get(self, url):
        for attempt in range(self.retries + 1):
            try:
                with self.open(url) as response:
                    data = response.read()
                    length = response.headers.get("Content-Length")
                    if length and len(data) != int(length):
                        raise OSError("Incomplete HTTP body")
                    return data
            except (OSError, ValueError, http.client.HTTPException) as error:
                if attempt == self.retries or not self.retryable(error):
                    self.error("fetch", url, error)
                    raise
                self.backoff(attempt, error)

    def listing(self, url, path, refresh=False):
        path = Path(path)
        if path.exists() and not refresh:
            cached = json.loads(path.read_text(encoding="utf-8"))
            if cached["url"] != url:
                raise ValueError("Listing cache URL mismatch")
            return cached
        entry = {"url": url, "fetched_at": utc_now(), "html": self.get(url).decode("utf-8-sig")}
        atomic_json(path, entry)
        return entry

