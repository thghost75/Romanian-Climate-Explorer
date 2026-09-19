"""Small HTTP adapter for an existing SimpleHTTPRequestHandler backend."""
import gzip
import hashlib
import json
import logging
import threading
from collections import OrderedDict
from pathlib import Path
from urllib.parse import parse_qs
from .config import DEFAULT_ROOT
from .explorer_api import Explorer

_CACHE = OrderedDict()
_LOCK = threading.Lock()
_CACHE_LIMIT = 64

def handle_climate(handler, path, query, root=DEFAULT_ROOT):
    """Return True if handled; never serve raw databases or filesystem paths."""
    if not path.startswith("/api/climate/"): return False
    status=200; body=None; etag=None
    try:
        if len(query)>2048: raise ValueError("Query is too long")
        values=parse_qs(query,keep_blank_values=True,max_num_fields=16)
        if any(len(v)!=1 or len(v[0])>200 for v in values.values()):
            raise ValueError("Expected one short value per query parameter")
        params={k:v[0] for k,v in values.items()}
        root=Path(root)
        revision=tuple((p.stat().st_mtime_ns,p.stat().st_size) for p in (
            root/"climate.sqlite",root/"climatology.sqlite",root/"processed/phase3/candidate_review_notes.json"))
        key=(str(root.resolve()),revision,path,tuple(sorted(params.items())))
        with _LOCK:
            body=_CACHE.get(key)
            if body is not None: _CACHE.move_to_end(key)
        if body is None:
            with Explorer(root) as explorer: payload=explorer.dispatch(path.removeprefix("/api/climate/"),params)
            body=json.dumps(payload,ensure_ascii=False,allow_nan=False,separators=(",",":")).encode("utf-8")
            with _LOCK:
                _CACHE[key]=body
                while len(_CACHE)>_CACHE_LIMIT: _CACHE.popitem(last=False)
        etag='"'+hashlib.sha256(body).hexdigest()+'"'
    except LookupError as exc:
        status=404; body=json.dumps({"error":str(exc)}).encode()
    except (ValueError,TypeError,OverflowError) as exc:
        status=400; body=json.dumps({"error":str(exc)}).encode()
    except Exception:
        logging.exception("Climate explorer request failed")
        status=503; body=b'{"error":"Climate data is unavailable. Check server climate-path configuration."}'
    # Host's end_headers may deliberately enforce no-store; server cache still works.
    if etag and handler.headers.get("If-None-Match")==etag:
        handler.send_response(304); handler.send_header("ETag",etag); handler.end_headers(); return True
    zipped="gzip" in handler.headers.get("Accept-Encoding","") and len(body)>1024
    if zipped: body=gzip.compress(body)
    handler.send_response(status)
    handler.send_header("Content-Type","application/json; charset=utf-8")
    handler.send_header("Content-Length",str(len(body)))
    handler.send_header("X-Content-Type-Options","nosniff")
    handler.send_header("Vary","Accept-Encoding")
    if etag: handler.send_header("ETag",etag)
    if zipped: handler.send_header("Content-Encoding","gzip")
    handler.end_headers(); handler.wfile.write(body)
    return True
