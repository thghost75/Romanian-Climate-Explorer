"""National periods preserve cross-station ties, coverage and variable QC."""
import json
import unittest
from test_record_periods import RecordPeriodTests
from anm_climate.national_records import build_index


class NationalRecordTests(RecordPeriodTests):
    def setUp(self):
        super().setUp()
        self.api.source.execute('CREATE TABLE stations (station_id TEXT PRIMARY KEY)')
        self.api.source.executemany('INSERT INTO stations VALUES (?)', [('test',),('second',)])
        self.api.stations['second']={**self.api.stations['test'], 'station_id':'second', 'station_name':'Second',
                                    'first_year':2024, 'first_observation':'2024-02-02'}
        self.api.source.execute('INSERT INTO daily_observations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
            ('second','2024-02-02',None,7,-8,10,0,10,None,None,'[]','second.txt',2))

    def test_national_ties_samples_and_provenance(self):
        result=self.api.dispatch('national-records',{'scope':'month-year','month':'2','day':'29','year':'2024'})
        records=result['records']
        self.assertEqual(result['station_count'],2)
        self.assertEqual(records['lowest_tmax']['value'],-8)
        self.assertEqual(records['lowest_tmax']['sample_count'],3)
        self.assertEqual({(o['station_id'],o['date']) for o in records['lowest_tmax']['observations']},
                         {('test','2024-02-01'),('second','2024-02-02')})
        self.assertEqual(len(records['highest_tmin']['observations']),3)
        self.assertTrue(records['highest_tmin']['needs_verification'])
        self.assertEqual(records['highest_tmax']['value'],9)  # QC excludes 99 only for Tmax.
        self.assertEqual(records['highest_precip']['observations'][0]['source_member'],'second.txt')

    def test_index_matches_direct_calculation_for_every_period(self):
        cases=[('day',2,29,2024),('month',2,1,2024),('month-year',2,1,2024),
               ('year',2,1,2024),('all',1,1,2024),('year',1,1,2022)]
        expected=[self.api.national_records(*args) for args in cases]
        build_index(self.api.source,self.api.products.db)
        self.assertEqual(expected,[self.api.national_records(*args) for args in cases])
        self.assertEqual(expected[-1]['station_count'],0)
        self.assertIsNone(expected[-1]['records']['highest_tmax']['value'])
        # A station beginning later must not prevent national searches in earlier years.
        early=self.api.national_records('year',1,1,2020)
        self.assertEqual(early['station_count'],1)
        self.assertEqual(early['records']['lowest_tmax']['value'],-8)
        with self.assertRaises(ValueError):self.api.national_records('year',1,1,1900)


if __name__ == '__main__': unittest.main()
