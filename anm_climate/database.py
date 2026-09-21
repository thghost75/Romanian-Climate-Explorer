"""SQLite persistence, transactional station/year replacement and provenance."""
import calendar
import json
import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path
from .config import ATTRIBUTION, MEASURES, archive_url, prepare
from .downloader import sha256
from .http import utc_now

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS stations (
 station_id TEXT PRIMARY KEY, station_name TEXT, latitude REAL, longitude REAL, elevation_m REAL,
 metadata_source TEXT, first_year INTEGER, last_year INTEGER, available_years TEXT NOT NULL DEFAULT '[]',
 missing_years TEXT NOT NULL DEFAULT '[]', observation_count INTEGER NOT NULL DEFAULT 0,
 completeness_percent REAL, ingested_expected_days INTEGER NOT NULL DEFAULT 0,
 ingested_years TEXT NOT NULL DEFAULT '[]', discovery_error TEXT, catalog_updated_at TEXT
);
CREATE TABLE IF NOT EXISTS archives (
 archive_id INTEGER PRIMARY KEY, station_id TEXT NOT NULL REFERENCES stations(station_id),
 year INTEGER NOT NULL, source_url TEXT NOT NULL, listed INTEGER NOT NULL DEFAULT 1,
 estimated_bytes INTEGER, size_is_exact INTEGER, listing_fetched_at TEXT,
 raw_path TEXT, sha256 TEXT, downloaded_at TEXT, ingested_at TEXT, parser_version TEXT,
 observation_count INTEGER, expected_days INTEGER, UNIQUE(station_id,year)
);
CREATE TABLE IF NOT EXISTS source_files (
 archive_id INTEGER NOT NULL REFERENCES archives(archive_id), member_name TEXT NOT NULL,
 encoding TEXT NOT NULL, header_line INTEGER NOT NULL, metadata_preamble TEXT NOT NULL,
 parsed_rows INTEGER NOT NULL, PRIMARY KEY(archive_id,member_name)
);
CREATE TABLE IF NOT EXISTS daily_observations (
 station_id TEXT NOT NULL REFERENCES stations(station_id), date TEXT NOT NULL,
 tmean_c REAL, tmin_c REAL, tmax_c REAL, precip_mm REAL,
 precip_trace INTEGER CHECK(precip_trace IN (0,1) OR precip_trace IS NULL),
 precip_raw REAL, wind_mean_ms REAL, pressure_msl_hpa REAL,
 source_archive_id INTEGER NOT NULL REFERENCES archives(archive_id), source_member TEXT NOT NULL,
 source_line INTEGER NOT NULL, raw_values_json TEXT NOT NULL, quality_flags TEXT NOT NULL DEFAULT '[]',
 PRIMARY KEY(station_id,date), CHECK(length(date)=10 AND date GLOB '????-??-??')
);
CREATE INDEX IF NOT EXISTS observations_date_idx ON daily_observations(date);
CREATE INDEX IF NOT EXISTS observations_calendar_idx ON daily_observations(station_id,substr(date,6,5));
CREATE INDEX IF NOT EXISTS observations_archive_idx ON daily_observations(source_archive_id);
CREATE TABLE IF NOT EXISTS duplicate_source_rows (
 archive_id INTEGER NOT NULL REFERENCES archives(archive_id), source_member TEXT NOT NULL,
 source_line INTEGER NOT NULL, station_id TEXT NOT NULL, date TEXT NOT NULL,
 duplicate_of_member TEXT NOT NULL, duplicate_of_line INTEGER NOT NULL, raw_values_json TEXT NOT NULL,
 PRIMARY KEY(archive_id,source_member,source_line)
);
CREATE TABLE IF NOT EXISTS dataset_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""

def connect(root):
    root = prepare(root)
    db = sqlite3.connect(root / "climate.sqlite", timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")
    db.executescript(SCHEMA)
    db.execute("INSERT OR IGNORE INTO dataset_metadata VALUES ('schema_version','1')")
    db.execute("INSERT OR IGNORE INTO dataset_metadata VALUES ('attribution',?)", (ATTRIBUTION,))
    db.commit()
    return db

def sync_catalog(root, manifest):
    with closing(connect(root)) as db, db:
        for station in manifest["stations"]:
            db.execute("""
                INSERT INTO stations(station_id,first_year,last_year,available_years,missing_years,discovery_error,catalog_updated_at)
                VALUES (?,?,?,?,?,?,?) ON CONFLICT(station_id) DO UPDATE SET
                first_year=CASE WHEN excluded.discovery_error IS NULL THEN excluded.first_year ELSE stations.first_year END,
                last_year=CASE WHEN excluded.discovery_error IS NULL THEN excluded.last_year ELSE stations.last_year END,
                available_years=CASE WHEN excluded.discovery_error IS NULL THEN excluded.available_years ELSE stations.available_years END,
                missing_years=CASE WHEN excluded.discovery_error IS NULL THEN excluded.missing_years ELSE stations.missing_years END,
                discovery_error=excluded.discovery_error,
                catalog_updated_at=COALESCE(excluded.catalog_updated_at,stations.catalog_updated_at)
            """, (station["station_id"], station["first_year"], station["last_year"],
                  json.dumps(station["available_years"]), json.dumps(station["missing_years"]),
                  station["discovery_error"], station["listing_fetched_at"]))
            if not station["discovery_error"]:
                db.execute("UPDATE archives SET listed=0 WHERE station_id=?", (station["station_id"],))
        for archive in manifest["archives"]:
            db.execute("""
                INSERT INTO archives(station_id,year,source_url,estimated_bytes,size_is_exact,listing_fetched_at)
                VALUES (?,?,?,?,?,?) ON CONFLICT(station_id,year) DO UPDATE SET listed=1,
                source_url=excluded.source_url,estimated_bytes=excluded.estimated_bytes,
                size_is_exact=excluded.size_is_exact,listing_fetched_at=excluded.listing_fetched_at
            """, (archive["station_id"], archive["year"], archive["url"], archive["estimated_bytes"],
                  archive["size_is_exact"], archive["listing_fetched_at"]))

def register_download(root, station, year, path):
    path = Path(path)
    receipt = json.loads(path.with_suffix(".zip.json").read_text(encoding="utf-8"))
    if receipt["url"] != archive_url(station, year) or receipt["sha256"] != sha256(path):
        raise ValueError("Downloaded file does not match its provenance receipt")
    with closing(connect(root)) as db, db:
        db.execute("INSERT OR IGNORE INTO stations(station_id) VALUES (?)", (station,))
        db.execute("""
            INSERT INTO archives(station_id,year,source_url,raw_path,downloaded_at)
            VALUES (?,?,?,?,?) ON CONFLICT(station_id,year) DO UPDATE SET
            raw_path=excluded.raw_path,downloaded_at=excluded.downloaded_at
        """, (station, year, archive_url(station, year), str(path.relative_to(Path(root))),
              receipt.get("downloaded_at")))
    # archives.sha256 identifies the ingested data; the receipt identifies the downloaded data.

def ingest(root, station, year, path, parsed, report):
    if report["duplicate_dates"] or report["rejected_rows"] or report["unexpected_dates"]:
        raise ValueError("Archive has duplicate/invalid keys; see validation report. No observations inserted.")
    if not parsed["rows"]:
        raise ValueError("No daily observations to ingest")
    for row in parsed["rows"]:
        day = date.fromisoformat(row["date"])
        if row["station_id"] != station or day.year != year:
            raise ValueError("Ingestion identity mismatch")
    digest = sha256(path)
    register_download(root, station, year, path)
    with closing(connect(root)) as db, db:
        source = db.execute("SELECT * FROM archives WHERE station_id=? AND year=?", (station, year)).fetchone()
        if source["sha256"] == digest and source["ingested_at"] and source["parser_version"] == parsed["parser_version"]:
            return {"status": "already_ingested", "observations": source["observation_count"]}
        archive_id = source["archive_id"]
        db.execute("DELETE FROM daily_observations WHERE station_id=? AND date>=? AND date<?",
                   (station, f"{year}-01-01", f"{year+1}-01-01"))
        db.execute("DELETE FROM source_files WHERE archive_id=?", (archive_id,))
        db.execute("DELETE FROM duplicate_source_rows WHERE archive_id=?", (archive_id,))
        for duplicate in parsed.get("exact_duplicate_rows", []):
            db.execute("INSERT INTO duplicate_source_rows VALUES (?,?,?,?,?,?,?,?)",
                       (archive_id, duplicate["source_member"], duplicate["source_line"], station, duplicate["date"],
                        duplicate["duplicate_of_member"], duplicate["duplicate_of_line"], json.dumps(duplicate["raw"])))
        for member in parsed["files"]:
            db.execute("INSERT INTO source_files VALUES (?,?,?,?,?,?)",
                       (archive_id, member["file"], member["encoding"], member["header_line"],
                        member["metadata_preamble"], member["parsed_rows"]))
        columns = ("station_id", "date", *MEASURES.values(), "precip_trace", "precip_raw",
                   "source_archive_id", "source_member", "source_line", "raw_values_json", "quality_flags")
        values = []
        for row in parsed["rows"]:
            item = {**row, "source_archive_id": archive_id, "raw_values_json": json.dumps(row["raw"]),
                    "quality_flags": json.dumps(row["quality_flags"])}
            values.append(tuple(item[name] for name in columns))
        db.executemany(f"INSERT INTO daily_observations ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})", values)
        expected = 366 if calendar.isleap(year) else 365
        db.execute("""
            UPDATE archives SET sha256=?,ingested_at=?,parser_version=?,observation_count=?,expected_days=?
            WHERE archive_id=?
        """, (digest, utc_now(), parsed["parser_version"], len(values), expected, archive_id))
        history = db.execute("SELECT year,expected_days FROM archives WHERE station_id=? AND ingested_at IS NOT NULL ORDER BY year",
                             (station,)).fetchall()
        denominator = sum(r["expected_days"] for r in history)
        count = db.execute("SELECT COUNT(*) FROM daily_observations WHERE station_id=?", (station,)).fetchone()[0]
        db.execute("""
            UPDATE stations SET observation_count=?,completeness_percent=?,ingested_expected_days=?,ingested_years=?
            WHERE station_id=?
        """, (count, 100 * count / denominator if denominator else None, denominator,
              json.dumps([r["year"] for r in history]), station))
    return {"status": "ingested", "observations": len(values)}

def status(root):
    with closing(connect(root)) as db:
        return {
            "stations": db.execute("SELECT COUNT(*) FROM stations").fetchone()[0],
            "catalogued_archives": db.execute("SELECT COUNT(*) FROM archives WHERE listed=1").fetchone()[0],
            "downloaded_archives": db.execute("SELECT COUNT(*) FROM archives WHERE raw_path IS NOT NULL").fetchone()[0],
            "ingested_archives": db.execute("SELECT COUNT(*) FROM archives WHERE ingested_at IS NOT NULL").fetchone()[0],
            "daily_observations": db.execute("SELECT COUNT(*) FROM daily_observations").fetchone()[0],
            "flagged_observations": db.execute("SELECT COUNT(*) FROM daily_observations WHERE quality_flags!='[]'").fetchone()[0],
            "database_bytes": (Path(root) / "climate.sqlite").stat().st_size,
        }

