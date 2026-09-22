"""Serving copies must retain data and leave the complete archive untouched."""
from contextlib import closing
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from scripts.prepare_runtime import NOTES, OBSERVATION_COLUMNS, PRODUCT_TABLES, prepare
from anm_climate.explorer_api import Explorer

PROJECT = Path(__file__).resolve().parents[1]


class RuntimeSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.source = self.root / 'source'
        self.source.mkdir()
        self.destination = self.root / 'runtime'
        with closing(sqlite3.connect(self.source / 'climate.sqlite')) as db:
            db.execute('CREATE TABLE stations (station_id TEXT PRIMARY KEY, station_name TEXT)')
            db.execute("INSERT INTO stations VALUES ('test','Test')")
            db.execute('CREATE TABLE daily_observations (' + ','.join(OBSERVATION_COLUMNS) + ',raw_values_json,PRIMARY KEY(station_id,date))')
            self.row = ('test','1871-01-01',None,None,None,0.0,1,-1.0,None,None,'["review"]','source.txt',7)
            db.execute('INSERT INTO daily_observations VALUES (' + ','.join('?' for _ in range(14)) + ')', (*self.row,'original raw values'))
            db.execute('CREATE TABLE source_files (metadata TEXT)')
            db.execute("INSERT INTO source_files VALUES ('keep this in the archive')")
            db.commit()
        with closing(sqlite3.connect(self.source / 'climatology.sqlite')) as db:
            for table in PRODUCT_TABLES:
                db.execute(f'CREATE TABLE {table} (id TEXT PRIMARY KEY, value TEXT)')
                db.execute(f'INSERT INTO {table} VALUES (?,?)', ('test','unchanged data'))
            db.execute('CREATE INDEX event_value ON precipitation_events(value)')
            db.execute('CREATE TABLE window_thresholds (value TEXT)')
            db.commit()
        (self.source / NOTES).parent.mkdir(parents=True)
        (self.source / NOTES).write_text('[{"note":"retain QC review"}]')

    def test_measurements_qc_provenance_and_products_survive_without_ingestion_copies(self):
        before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.source.glob('*.sqlite')}
        prepare(self.source, self.destination)
        self.assertEqual(before,{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in self.source.glob('*.sqlite')})
        with closing(sqlite3.connect(self.destination / 'climate.sqlite')) as db:
            self.assertEqual(db.execute('SELECT * FROM daily_observations').fetchone(),self.row)
            self.assertEqual({r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")},{'stations','daily_observations'})
        with closing(sqlite3.connect(self.destination / 'climatology.sqlite')) as db:
            for table in PRODUCT_TABLES:
                self.assertEqual(db.execute(f'SELECT * FROM {table}').fetchone(),('test','unchanged data'))
            self.assertIsNotNone(db.execute("SELECT name FROM sqlite_master WHERE name='event_value'").fetchone())
            self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='window_thresholds'").fetchone())
        self.assertEqual((self.source / NOTES).read_bytes(),(self.destination / NOTES).read_bytes())
        self.assertEqual(list(self.root.glob('runtime-build-*')),[])

    def test_size_failure_does_not_replace_previous_serving_copy(self):
        self.destination.mkdir()
        old = self.destination / 'climate.sqlite'
        old.write_bytes(b'previous serving copy')
        with patch('scripts.prepare_runtime.MAX_RUNTIME_BYTES',1), self.assertRaisesRegex(ValueError,'budget'):
            prepare(self.source,self.destination)
        self.assertEqual(old.read_bytes(),b'previous serving copy')
        self.assertEqual(list(self.root.glob('runtime-build-*')),[])

    def test_source_destination_overlap_is_rejected(self):
        for target in (self.source,self.source/'runtime',self.root):
            with self.assertRaisesRegex(ValueError,'separate'):
                prepare(self.source,target)


@unittest.skipUnless((PROJECT/'data/runtime/climatology.sqlite').exists(), 'Prepared serving snapshot required')
class RuntimeParityTests(unittest.TestCase):
    def test_public_responses_match_complete_archive(self):
        cases = [('stations', {}), ('on-this-day', {'month':'9','day':'21'})]
        for station, year in [('0-20000-0-15200','1871'), ('0-20000-0-15324','1931'), ('0-20000-0-15420','2025')]:
            params = {'station':station,'year':year,'month':'12','day':'1'}
            cases.extend((endpoint,params) for endpoint in ('overview','daily-year','history','quality','temperature','rainfall','events'))
        with Explorer(PROJECT/'data/anm') as source, Explorer(PROJECT/'data/runtime') as serving:
            for endpoint, params in cases:
                with self.subTest(endpoint=endpoint,params=params):
                    self.assertEqual(source.dispatch(endpoint,params),serving.dispatch(endpoint,params))
