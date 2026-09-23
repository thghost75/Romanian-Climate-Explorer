"""Build a compact serving snapshot; never modify the complete source archive."""
import json
from contextlib import closing
from pathlib import Path
import shutil
import sqlite3
import tempfile
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from anm_climate.national_records import build_index

PROJECT = Path(__file__).resolve().parents[1]
MAX_RUNTIME_BYTES = 4_500_000_000  # Leave room for the Python runtime below 5 GB.
PRODUCT_TABLES = (
    'metadata', 'qc_exclusions', 'qc_counts', 'daily_climatology', 'daily_records',
    'monthly_summary', 'annual_summary', 'period_climatology', 'climate_indices',
    'temperature_events', 'precipitation_events',
)
OBSERVATION_COLUMNS = (
    'station_id', 'date', 'tmean_c', 'tmin_c', 'tmax_c', 'precip_mm', 'precip_trace',
    'precip_raw', 'wind_mean_ms', 'pressure_msl_hpa', 'quality_flags',
    'source_member', 'source_line',
)
NOTES = Path('processed/phase3/candidate_review_notes.json')


def copy_database(source, target, tables, project_observations=False):
    with closing(sqlite3.connect(target, uri=True)) as db:
        db.execute('ATTACH DATABASE ? AS archive', (source.resolve().as_uri() + '?mode=ro',))
        for table in tables:
            if table == 'daily_observations' and project_observations:
                # Keep every measurement, QC flag and displayed source reference.
                db.execute('''CREATE TABLE daily_observations (
                    station_id TEXT NOT NULL, date TEXT NOT NULL,
                    tmean_c REAL, tmin_c REAL, tmax_c REAL, precip_mm REAL,
                    precip_trace INTEGER, precip_raw REAL, wind_mean_ms REAL,
                    pressure_msl_hpa REAL, quality_flags TEXT NOT NULL,
                    source_member TEXT NOT NULL, source_line INTEGER NOT NULL,
                    PRIMARY KEY(station_id,date)) WITHOUT ROWID''')
                columns = ','.join(OBSERVATION_COLUMNS)
            else:
                schema = db.execute('SELECT sql FROM archive.sqlite_master WHERE type=? AND name=?',
                                    ('table', table)).fetchone()
                if not schema:
                    raise ValueError('Required serving table is missing: ' + table)
                db.execute(schema[0])
                columns = '*'
            db.execute(f'INSERT INTO main.{table} SELECT {columns} FROM archive.{table}')
            expected = db.execute(f'SELECT COUNT(*) FROM archive.{table}').fetchone()[0]
            actual = db.execute(f'SELECT COUNT(*) FROM main.{table}').fetchone()[0]
            if actual != expected:
                raise ValueError('Serving snapshot row count mismatch: ' + table)
            if table != 'daily_observations':
                for (sql,) in db.execute('SELECT sql FROM archive.sqlite_master WHERE type=? AND tbl_name=? AND sql IS NOT NULL',
                                        ('index', table)).fetchall():
                    db.execute(sql)
        db.commit()
        db.execute('ANALYZE main')
        db.commit()
        if db.execute('PRAGMA main.quick_check').fetchone()[0] != 'ok':
            raise ValueError('Serving snapshot integrity check failed: ' + target.name)


def prepare(source=None, destination=None):
    source = Path(source or PROJECT / 'data/anm').resolve()
    destination = Path(destination or PROJECT / 'data/runtime').resolve()
    if source == destination or source in destination.parents or destination in source.parents:
        raise ValueError('Serving snapshot must be separate from the source archive')
    destination.parent.mkdir(parents=True, exist_ok=True)
    names = ('climate.sqlite', 'climatology.sqlite')
    # A fresh bounded staging directory prevents cached builds accumulating old data.
    with tempfile.TemporaryDirectory(prefix='runtime-build-', dir=destination.parent) as temporary:
        staging = Path(temporary).resolve()
        if staging.parent != destination.parent:
            raise ValueError('Unexpected serving snapshot staging directory')
        print('Preparing compact serving databases; full archive retained.', flush=True)
        copy_database(source / names[0], staging / names[0], ('stations', 'daily_observations'), True)
        copy_database(source / names[1], staging / names[1], PRODUCT_TABLES)
        with closing(sqlite3.connect(staging / names[0])) as observations, closing(sqlite3.connect(staging / names[1])) as products:
            print('Preparing compact national record summaries.', flush=True)
            build_index(observations, products)
        notes = (source / NOTES).read_bytes()
        runtime_bytes = sum((staging / name).stat().st_size for name in names) + len(notes)
        if runtime_bytes >= MAX_RUNTIME_BYTES:
            raise ValueError('Serving snapshot exceeds the safe 4.5 GB deployment budget')
        destination.mkdir(parents=True, exist_ok=True)
        for name in names:
            (staging / name).replace(destination / name)
        (destination / NOTES).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / NOTES, destination / NOTES)
    source_bytes = sum((source / name).stat().st_size for name in names) + len(notes)
    report = {'source_bytes': source_bytes, 'runtime_bytes': runtime_bytes,
              'saved_bytes': source_bytes - runtime_bytes, 'limit_bytes': MAX_RUNTIME_BYTES}
    print('Serving snapshot size: ' + json.dumps(report), flush=True)
    return report


if __name__ == '__main__':
    prepare()
