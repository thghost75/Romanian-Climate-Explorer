from contextlib import closing
from datetime import date
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from anm_climate import database
from anm_climate.config import archive_url, prepare
from anm_climate.downloader import sha256
from anm_climate.http import atomic_json
from anm_climate.parser import parse_archive
from anm_climate.phase3_policy import Policy, VARIABLES
from anm_climate.snapshot_products import SCHEMA, dumps
from anm_climate.validation import summarize
from scripts.refresh_daily import refresh_products, update_station_summary, validate_replacement, run

SID = '0-20000-0-15085'
TODAY = date(2026, 9, 21)


class DailyRefreshTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent / '_tmp')
        self.root = prepare(Path(self.temp.name))
        self.path = self.root / 'raw' / SID / f'{SID}_2026.zip'
        self.path.parent.mkdir(parents=True)
        with closing(database.connect(self.root)) as db:
            for name, kind in [('first_observation','TEXT'), ('last_observation','TEXT'),
                ('observation_days','INTEGER'), ('possible_calendar_days','INTEGER'),
                ('ingested_year_completeness_percent','REAL'), ('source_daily_rows','INTEGER'),
                ('first_source_date','TEXT'), ('last_source_date','TEXT')]:
                db.execute(f'ALTER TABLE stations ADD COLUMN {name} {kind}')
            db.commit()
        self.make_archive([('2026-09-18', 10, 20, 1)])
        self.ingest()
        with closing(sqlite3.connect(self.root / 'climatology.sqlite')) as db:
            db.executescript(SCHEMA)
            db.executemany('INSERT INTO metadata VALUES (?,?)',
                           [('policy', dumps(vars(Policy()))), ('state', dumps('complete'))])
            db.commit()

    def tearDown(self):
        self.temp.cleanup()

    def make_archive(self, rows):
        text = 'wsi,an,luna,zi,ff,p,r,ta,tn,tx\n'
        for day, mean, high, rain in rows:
            day = date.fromisoformat(day)
            text += f'{SID},{day.year},{day.month},{day.day},2,1010,{rain},{mean},5,{high}\n'
        with ZipFile(self.path, 'w') as zipped:
            zipped.writestr(f'{SID}_2026_09.csv', text)
        atomic_json(self.path.with_suffix('.zip.json'),
                    {'url': archive_url(SID, 2026), 'sha256': sha256(self.path)})

    def ingest(self):
        parsed = parse_archive(self.path, SID, 2026)
        database.ingest(self.root, SID, 2026, self.path, parsed, summarize(parsed, SID, 2026))

    def previous(self):
        with closing(database.connect(self.root)) as db:
            return [dict(r) for r in db.execute('SELECT * FROM daily_observations')]

    def validate(self):
        parsed = parse_archive(self.path, SID, 2026)
        validate_replacement(self.previous(), parsed, summarize(parsed, SID, 2026), TODAY)

    def test_truncated_source_cannot_replace_existing_observations(self):
        self.make_archive([('2026-09-19', 15, 25, 0)])
        with self.assertRaisesRegex(ValueError, 'disappeared'):
            self.validate()
        self.assertEqual(self.previous()[0]['date'], '2026-09-18')

    def test_future_measurements_are_rejected(self):
        self.make_archive([('2026-09-18', 10, 20, 1), ('2026-09-22', 15, 25, 0)])
        with self.assertRaisesRegex(ValueError, 'Future'):
            self.validate()

    def test_real_correction_and_new_day_update_records_summaries_and_qc(self):
        self.make_archive([('2026-09-18', 11, 22, 2), ('2026-09-19', 15, 30, 5)])
        self.validate()
        self.ingest()
        with closing(database.connect(self.root)) as source, closing(sqlite3.connect(self.root / 'climatology.sqlite')) as derived:
            with source:
                update_station_summary(source, SID)
            refresh_products(source, derived, SID, Policy())
            record = json.loads(derived.execute('SELECT data_json FROM daily_records WHERE calendar_day=?', ('09-19',)).fetchone()[0])
            self.assertEqual(record['highest_tmax']['value'], 30)
            self.assertEqual(record['highest_tmax']['dates'], ['2026-09-19'])
            self.assertEqual(derived.execute('SELECT eligible_count FROM qc_counts WHERE variable=?', ('precip_mm',)).fetchone()[0], 2)
            self.assertEqual(source.execute('SELECT last_observation,observation_days FROM stations').fetchone()[:], ('2026-09-19', 2))
            # A second build replaces station products, without accumulating rows.
            refresh_products(source, derived, SID, Policy())
            self.assertEqual(derived.execute('SELECT count(*) FROM daily_records').fetchone()[0], 366)

    def test_failed_product_build_rolls_back_station_replacement(self):
        with closing(database.connect(self.root)) as source, closing(sqlite3.connect(self.root / 'climatology.sqlite')) as derived:
            refresh_products(source, derived, SID, Policy())
            before = derived.execute('SELECT count(*) FROM daily_records').fetchone()[0]
            with patch('scripts.refresh_daily.save_station', side_effect=RuntimeError('interrupted')):
                with self.assertRaises(RuntimeError):
                    refresh_products(source, derived, SID, Policy())
            self.assertEqual(derived.execute('SELECT count(*) FROM daily_records').fetchone()[0], before)

    def test_original_database_cannot_be_targeted(self):
        with self.assertRaisesRegex(ValueError, 'disposable'):
            run(self.root, TODAY)

    def test_same_source_is_noop_and_does_not_rebuild(self):
        (self.root / '.daily-refresh-workspace').touch()
        content = self.path.read_bytes()
        def download_again(*args):
            self.path.write_bytes(content)
            return self.path
        with patch('scripts.refresh_daily.HttpClient') as http, patch('scripts.refresh_daily.download', side_effect=download_again), patch('scripts.refresh_daily.refresh_products') as rebuild:
            http.return_value.get.return_value = f'<a href="{SID}_2026.zip">2026</a>'.encode()
            result = run(self.root, TODAY)
        self.assertFalse(result['changed'])
        rebuild.assert_not_called()

    def test_listing_failure_cannot_publish_success(self):
        (self.root / '.daily-refresh-workspace').touch()
        with patch('scripts.refresh_daily.HttpClient') as http:
            http.return_value.get.return_value = b'<html>Temporarily unavailable</html>'
            with self.assertRaisesRegex(ValueError, 'listing format'):
                run(self.root, TODAY)
        self.assertFalse((self.root / 'refresh-result.json').exists())
