import json
import sqlite3
import unittest
from anm_climate.reviewed_observations import apply_reviews
from anm_climate.snapshot_products import SCHEMA
from anm_climate.national_records import aggregate


class ObservationReviewTests(unittest.TestCase):
    def setUp(self):
        self.source = sqlite3.connect(':memory:')
        self.source.row_factory = sqlite3.Row
        self.products = sqlite3.connect(':memory:')
        self.addCleanup(self.source.close)
        self.addCleanup(self.products.close)
        self.source.execute('CREATE TABLE stations (station_id TEXT)')
        self.source.execute("INSERT INTO stations VALUES ('test')")
        self.source.execute('CREATE TABLE daily_observations (station_id,date,tmean_c,tmin_c,tmax_c,precip_mm,precip_raw,precip_trace,wind_mean_ms,pressure_msl_hpa,quality_flags)')
        self.source.executemany('INSERT INTO daily_observations VALUES (?,?,?,?,?,?,?,?,?,?,?)',[
            ('test','1996-12-30',-18.4,-24.7,12.0,1.1,1.1,0,0,1017.8,'[]'),
            ('test','1996-12-31',-11.4,-12.8,30.0,0.1,0.1,0,0,1020,'[]')])
        self.products.executescript(SCHEMA)

    def review(self, day, value, action, **extra):
        return dict(station_id='test',start_date=day,end_date=day,variable='tmax_c',
                    original_value=value,action=action,**extra)

    def test_corrected_range_and_exclusions_rebuild_all_products(self):
        reviews=[self.review('1996-12-30',12,'correct',corrected_value=-12),
                 self.review('1996-12-31',30,'exclude')]
        self.assertEqual(apply_reviews(self.source,self.products,reviews),reviews)
        result=aggregate(self.source,self.products,'year','1996')[('year','1996')]['records']
        self.assertEqual(result['highest_amplitude']['value'],12.7)
        self.assertEqual(result['highest_tmax']['value'],-12)
        self.assertEqual(result['highest_precip']['sample_count'],2)
        raw=self.source.execute("SELECT tmax_c FROM daily_observations WHERE date='1996-12-31'").fetchone()[0]
        self.assertEqual(raw,30)  # Quarantine does not erase the source value.
        day=json.loads(self.products.execute("SELECT data_json FROM daily_records WHERE calendar_day='12-30'").fetchone()[0])
        self.assertEqual(day['highest_tmax']['value'], -12)
        self.assertEqual(day['highest_tmax']['dates'], ['1996-12-30'])
        excluded_day=json.loads(self.products.execute("SELECT data_json FROM daily_records WHERE calendar_day='12-31'").fetchone()[0])
        self.assertIsNone(excluded_day['highest_tmax']['value'])
        self.assertEqual(excluded_day['highest_precip']['value'], 0.1)
        excluded=self.products.execute("SELECT excluded_count FROM qc_counts WHERE variable='tmax_c'").fetchone()[0]
        self.assertEqual(excluded,1)

    def test_upstream_change_requires_new_review(self):
        with self.assertRaisesRegex(ValueError,'source value changed'):
            apply_reviews(self.source,self.products,[self.review('1996-12-30',11,'exclude')])

    def test_source_already_corrected_is_not_overwritten(self):
        self.source.execute("UPDATE daily_observations SET tmax_c=-12 WHERE date='1996-12-30'")
        self.assertEqual(apply_reviews(self.source,self.products,[self.review('1996-12-30',12,'correct',corrected_value=-12)]),[])
