"""Resumable, validated downloads; raw ZIPs remain unmodified."""
import hashlib
import http.client
import json
import logging
import os
import re
import stat
import urllib.error
import uuid
import zlib
from pathlib import Path, PurePosixPath
from zipfile import ZipFile, BadZipFile
from .config import archive_url, prepare
from .http import atomic_json, utc_now

LOG = logging.getLogger(__name__)

def sha256(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()

def validate_zip(path):
    try:
        return _validate_zip(path)
    except (zlib.error, EOFError) as error:
        raise BadZipFile(f"ZIP decompression failed: {error}") from error

def _validate_zip(path):
    with ZipFile(path) as archive:
        members = archive.infolist()
        if not members or len(members) > 500:
            raise ValueError("ZIP has zero or too many members")
        total = 0
        names = set()
        for member in members:
            name = member.filename
            if name.casefold() in names:
                raise ValueError(f"Duplicate ZIP member: {name}")
            names.add(name.casefold())
            parts = PurePosixPath(name).parts
            if "\\" in name or ":" in name or name.startswith("/") or ".." in parts:
                raise ValueError(f"Unsafe ZIP member: {name}")
            if stat.S_ISLNK(member.external_attr >> 16):
                raise ValueError(f"ZIP symlink rejected: {name}")
            if member.flag_bits & 1:
                raise ValueError("Encrypted ZIP not supported")
            total += member.file_size
            if total > 100 * 1024 * 1024:
                raise ValueError("ZIP expanded size exceeds 100 MiB safety bound")
        bad = archive.testzip()
        if bad:
            raise BadZipFile(f"CRC failed: {bad}")
        return {"member_count": len(members), "uncompressed_bytes": total}

def download(root, client, station, year):
    root = prepare(root)
    url = archive_url(station, year)
    directory = root / "raw" / station
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{station}_{year}.zip"
    receipt = target.with_suffix(".zip.json")
    part = target.with_suffix(".zip.part")
    part_meta = target.with_suffix(".zip.part.json")
    if target.exists():
        try:
            validate_zip(target)
            digest = sha256(target)
            prior = json.loads(receipt.read_text(encoding="utf-8")) if receipt.exists() else {}
            if prior.get("url", url) != url or prior.get("sha256", digest) != digest:
                raise ValueError("Cached archive provenance/checksum mismatch")
            if not prior:
                atomic_json(receipt, {"url": url, "sha256": digest, "bytes": target.stat().st_size,
                                      "validated_at": utc_now(), "downloaded_at": None})
            LOG.info("Using already downloaded and verified archive: %s", target)
            return target
        except (ValueError, OSError, BadZipFile) as error:
            client.error("cached-zip-invalid", url, error)
            target.rename(target.with_suffix(f".zip.corrupt-{uuid.uuid4().hex[:8]}"))
    for attempt in range(client.retries + 1):
        try:
            meta = json.loads(part_meta.read_text(encoding="utf-8")) if part_meta.exists() else {}
            offset = part.stat().st_size if part.exists() else 0
            validator = meta.get("etag") or meta.get("last_modified")
            headers = {}
            if offset and validator and meta.get("url") == url:
                headers = {"Range": f"bytes={offset}-", "If-Range": validator}
            else:
                offset = 0
            with client.open(url, headers) as response:
                status = response.status
                if status == 206:
                    match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", response.headers.get("Content-Range", ""))
                    if not headers or not match or int(match[1]) != offset or int(match[2]) < offset:
                        raise ValueError("Invalid HTTP Content-Range")
                    total = int(match[3])
                    new_validator = response.headers.get("ETag") or response.headers.get("Last-Modified")
                    if new_validator and new_validator != validator:
                        part.write_bytes(b"")
                        raise ValueError("Remote file changed during resume")
                    mode = "ab"
                elif status == 200:
                    offset = 0
                    total = int(response.headers["Content-Length"]) if response.headers.get("Content-Length") else None
                    mode = "wb"
                else:
                    raise ValueError(f"Unexpected download status {status}")
                etag = response.headers.get("ETag")
                if etag and etag.startswith("W/"):
                    etag = None
                meta = {"url": url, "etag": etag, "last_modified": response.headers.get("Last-Modified"),
                        "expected_bytes": total}
                atomic_json(part_meta, meta)
                with part.open(mode) as out:
                    while chunk := response.read(65536):
                        out.write(chunk)
                        if out.tell() > 64 * 1024 * 1024:
                            raise ValueError("Yearly ZIP exceeds 64 MiB safety bound")
                if total is not None and part.stat().st_size != total:
                    raise OSError(f"Incomplete download: {part.stat().st_size}/{total} bytes")
            info = validate_zip(part)
            digest = sha256(part)
            os.replace(part, target)
            atomic_json(receipt, {**meta, **info, "sha256": digest, "bytes": target.stat().st_size,
                                  "downloaded_at": utc_now(), "validated_at": utc_now()})
            part_meta.unlink(missing_ok=True)
            LOG.info("Downloaded and verified %s (%s bytes)", target.name, target.stat().st_size)
            return target
        except (OSError, ValueError, BadZipFile, http.client.HTTPException) as error:
            # A corrupt full response or unsatisfiable range must restart cleanly.
            if isinstance(error, (BadZipFile, ValueError)) or isinstance(error, urllib.error.HTTPError) and error.code == 416:
                if part.exists():
                    part.rename(part.with_suffix(f".corrupt-{uuid.uuid4().hex[:8]}"))
                part_meta.unlink(missing_ok=True)
            if attempt == client.retries or (isinstance(error, urllib.error.HTTPError) and error.code not in (408, 416, 429, 500, 502, 503, 504)):
                client.error("download", url, error)
                raise
            client.backoff(attempt, error)
    raise RuntimeError("Download attempts exhausted")

