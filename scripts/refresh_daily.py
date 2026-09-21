"""Refresh a disposable snapshot. Never run against a live/original archive.

Publication is a separate step, only reached after every station and both DBs
validate. A failed run leaves the production release and manifest untouched.
"""
import argparse
from collections import Counter
from contextlib import closing
from datetime import date, datetime, timezone
import json
from pathlib import Path
import sqlite3
import sys
import time

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from anm_climate import database
from anm_climate.config import BASE_URL, prepare
from anm_climate.discovery import entries
from anm_climate.downloader import download, sha256
from anm_climate.http import HttpClient, atomic_json
from anm_climate.parser import parse_archive
from anm_climate.validation import summarize
from anm_climate.phase3_policy import Policy, VARIABLES, eligibility, pressure_quarantine, cleaned_rows
from anm_climate.snapshot_products import save_station, dumps

TABLES = ('qc_exclusions', 'qc_counts', 'pressure_quarantine', 'daily_climatology',
          'window_thresholds', 'daily_records', 'monthly_summary', 'annual_summary',
          'period_climatology', 'climate_indices', 'temperature_events',
          'precipitation_events', 'station_build')


def validate_replacement(previous, parsed, report, today):
    if report['rejected_rows'] or report['duplicate_dates'] or report['unexpected_dates']:
        raise ValueError('Invalid or ambiguous source rows; publication blocked')
    if not parsed['rows']:
        raise ValueError('Empty or unreadable archive; publication blocked')
    rows = {row['date']: row for row in parsed['rows']}
    for row in rows.values():
        if row['date'] > today.isoformat() and any(row[v] is not None for v in VARIABLES):
            raise ValueError('Future dated measurements; publication blocked')
    for old in previous:
        new = rows.get(old['date'], {})
        if any(old[v] is not None and new.get(v) is None for v in VARIABLES):
            raise ValueError('Previously available measurements disappeared; manual review required')


def update_station_summary(db, sid):
    measured = ' OR '.join(v + ' IS NOT NULL' for v in VARIABLES)
    first, last, count = db.execute(
        f'SELECT min(date),max(date),count(*) FROM daily_observations WHERE station_id=? AND ({measured})', (sid,)).fetchone()
    first_source, last_source, total = db.execute(
        'SELECT min(date),max(date),count(*) FROM daily_observations WHERE station_id=?', (sid,)).fetchone()
    possible = (date.fromisoformat(last) - date.fromisoformat(first)).days + 1 if first else 0
    history = db.execute('SELECT year,expected_days FROM archives WHERE station_id=? AND ingested_at IS NOT NULL ORDER BY year', (sid,)).fetchall()
    years = [r[0] for r in history]
    denominator = sum(r[1] for r in history)
    db.execute('''UPDATE stations SET first_observation=?,last_observation=?,observation_days=?,
        possible_calendar_days=?,completeness_percent=?,ingested_year_completeness_percent=?,
        source_daily_rows=?,first_source_date=?,last_source_date=?,first_year=?,last_year=?,
        available_years=?,missing_years=? WHERE station_id=?''',
        (first, last, count, possible, 100*count/possible if possible else None,
         100*total/denominator if denominator else None, total, first_source, last_source,
         min(years), max(years), json.dumps(years),
         json.dumps(sorted(set(range(min(years), max(years)+1))-set(years))), sid))


def refresh_products(source, derived, sid, policy):
    rows = [dict(r) for r in source.execute(
        'SELECT date,' + ','.join(VARIABLES) + ',precip_raw,precip_trace,quality_flags '
        'FROM daily_observations WHERE station_id=? ORDER BY date', (sid,))]
    suspect = pressure_quarantine(rows)
    counts = {v: Counter() for v in VARIABLES}
    exclusions = []
    for row in rows:
        for variable in VARIABLES:
            ok, reason = eligibility(row, variable, suspect)
            counts[variable]['eligible' if ok else 'missing' if reason == 'missing' else 'excluded'] += 1
            if not ok and reason != 'missing':
                exclusions.append((sid, row['date'], variable, reason, row[variable]))
    with derived:
        for table in TABLES:
            derived.execute(f'DELETE FROM {table} WHERE station_id=?', (sid,))
        derived.executemany('INSERT INTO pressure_quarantine VALUES (?,?)', [(sid, y) for y in sorted(suspect)])
        derived.executemany('INSERT INTO qc_exclusions VALUES (?,?,?,?,?)', exclusions)
        derived.executemany('INSERT INTO qc_counts VALUES (?,?,?,?,?)',
                            [(sid, v, c['eligible'], c['missing'], c['excluded']) for v, c in counts.items()])
        started = time.monotonic()
        save_station(derived, sid, cleaned_rows(rows, suspect), policy)
        derived.execute('INSERT INTO station_build VALUES (?,?)', (sid, time.monotonic()-started))
        if derived.execute('SELECT count(*) FROM daily_records WHERE station_id=?', (sid,)).fetchone()[0] != 366:
            raise ValueError('Incomplete rebuilt calendar')
        if derived.execute('SELECT sum(eligible_count+missing_count+excluded_count) FROM qc_counts WHERE station_id=?', (sid,)).fetchone()[0] != len(rows)*len(VARIABLES):
            raise ValueError('Incomplete QC accounting')


def verify_database(db):
    if [r[0] for r in db.execute('PRAGMA integrity_check')] != ['ok']:
        raise ValueError('SQLite integrity check failed')
    if db.execute('PRAGMA foreign_key_check').fetchone():
        raise ValueError('SQLite foreign key check failed')


def run(root, today=None):
    root = Path(root).resolve()
    # Explicit sentinel prevents accidental mutation of a historical/live DB.
    if not (root / '.daily-refresh-workspace').is_file():
        raise ValueError('Use a disposable copy with a .daily-refresh-workspace marker')
    today = today or datetime.now(timezone.utc).date()
    prepare(root)
    client = HttpClient(root, interval=1, timeout=45, retries=3)
    changed, checked = set(), 0
    with closing(database.connect(root)) as source, closing(sqlite3.connect(root / 'climatology.sqlite')) as derived:
        derived.row_factory = sqlite3.Row
        policy = Policy(**json.loads(derived.execute("SELECT value FROM metadata WHERE key='policy'").fetchone()[0])).validate()
        if json.loads(derived.execute("SELECT value FROM metadata WHERE key='state'").fetchone()[0]) != 'complete':
            raise ValueError('Starting snapshot is incomplete')
        station_ids = [r[0] for r in source.execute('SELECT station_id FROM stations ORDER BY station_id')]
        for index, sid in enumerate(station_ids, 1):
            listing = client.get(BASE_URL + sid + '/').decode('utf-8-sig')
            names = {e['href'] for e in entries(listing)}
            if not any(n.startswith(sid + '_') and n.endswith('.zip') for n in names):
                raise ValueError('Source listing format changed: ' + sid)
            # The previous year catches late reports and the January rollover.
            for year in (today.year-1, today.year):
                name = f'{sid}_{year}.zip'
                previous_archive = source.execute('SELECT sha256 FROM archives WHERE station_id=? AND year=? AND ingested_at IS NOT NULL', (sid, year)).fetchone()
                if name not in names:
                    if previous_archive:
                        raise ValueError('Previously available archive disappeared: ' + name)
                    continue
                target = root / 'raw' / sid / name
                # Fetch anew, including retries/reruns in a disposable workspace.
                target.unlink(missing_ok=True)
                path = download(root, client, sid, year)
                checked += 1
                if previous_archive and previous_archive[0] == sha256(path):
                    continue
                parsed = parse_archive(path, sid, year)
                report = summarize(parsed, sid, year)
                previous = [dict(r) for r in source.execute(
                    'SELECT date,' + ','.join(VARIABLES) + ' FROM daily_observations WHERE station_id=? AND date>=? AND date<?',
                    (sid, f'{year}-01-01', f'{year+1}-01-01'))]
                validate_replacement(previous, parsed, report, today)
                result = database.ingest(root, sid, year, path, parsed, report)
                if result['status'] == 'ingested':
                    changed.add(sid)
            print(f'Checked {index}/{len(station_ids)}: {sid}', flush=True)
        for index, sid in enumerate(sorted(changed), 1):
            with source:
                update_station_summary(source, sid)
            refresh_products(source, derived, sid, policy)
            print(f'Rebuilt {index}/{len(changed)}: {sid}', flush=True)
        if changed:
            verify_database(source)
            verify_database(derived)
            source.commit()
            source.execute('PRAGMA wal_checkpoint(TRUNCATE)')
            source_digest = sha256(root / 'climate.sqlite')
            with derived:
                for key, value in {
                    'source_sha256': source_digest, 'completed_at': datetime.now(timezone.utc).isoformat(),
                    'daily_refresh': {'changed_stations': len(changed), 'checked_archives': checked,
                                      'checked_years': [today.year-1, today.year]},
                    'validation': {'passed': True, 'integrity_check': 'ok', 'qc_accounting': True},
                }.items():
                    derived.execute('INSERT OR REPLACE INTO metadata VALUES (?,?)', (key, dumps(value)))
                # Original whole-build timings/signature/reports no longer describe this version.
                derived.execute("DELETE FROM metadata WHERE key IN ('signature','processing_seconds','qc_summary')")
            derived.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        latest = source.execute('SELECT max(last_observation) FROM stations').fetchone()[0]
    status = {'changed': bool(changed), 'checked_at': datetime.now(timezone.utc).isoformat(),
              'latest_observation': latest, 'station_count': len(station_ids),
              'changed_stations': len(changed), 'checked_archives': checked,
              'checked_years': [today.year-1, today.year]}
    atomic_json(root / 'refresh-result.json', status)
    print(json.dumps(status), flush=True)
    return status


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-root', required=True, type=Path)
    args = parser.parse_args()
    run(args.data_root)
