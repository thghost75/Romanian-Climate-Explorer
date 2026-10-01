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
        highlight_cases=[('month',2,2024),('month-year',2,2024),('year',2,2024),('all',1,2024),('year',1,2022)]
        expected_highlights=[self.api.national_highlights(*args) for args in highlight_cases]
        build_index(self.api.source,self.api.products.db)
        self.assertEqual(expected,[self.api.national_records(*args) for args in cases])
        self.assertEqual(expected_highlights,[self.api.national_highlights(*args) for args in highlight_cases])
        self.assertEqual(expected[-1]['station_count'],0)
        self.assertIsNone(expected[-1]['records']['highest_tmax']['value'])
        # A station beginning later must not prevent national searches in earlier years.
        early=self.api.national_records('year',1,1,2020)
        self.assertEqual(early['station_count'],1)
        self.assertEqual(early['records']['lowest_tmax']['value'],-8)
        with self.assertRaises(ValueError):self.api.national_records('year',1,1,1900)

    def test_highlights_periods_and_all_tied_dates(self):
        month=self.api.dispatch('national-highlights',{'scope':'month','month':'2'})
        by_kind=lambda result,kind:[r for r in result['records'] if r['record_type']==kind]
        low=by_kind(month,'lowest_tmax')
        self.assertEqual([r['station_id'] for r in low],['second','test'])
        self.assertEqual(low[1]['dates'],['2020-02-29','2024-02-01'])
        self.assertEqual(low[1]['sample_count'],4)
        feb=self.api.national_highlights('month-year',2,2024)
        self.assertEqual(by_kind(feb,'lowest_tmax')[1]['dates'],['2024-02-01'])
        self.assertEqual(by_kind(feb,'highest_tmax')[0]['value'],9)  # 99 is excluded for Tmax only.
        self.assertEqual(by_kind(feb,'highest_tmin')[1]['dates'],['2024-02-02','2024-02-03'])
        self.assertTrue(by_kind(feb,'highest_tmin')[1]['needs_verification'])
        annual=self.api.national_highlights('year',1,2024)
        self.assertEqual(by_kind(annual,'lowest_tmin')[0]['value'],-25)
        self.assertEqual(by_kind(annual,'lowest_tmin')[0]['dates'],['2024-03-01'])
        self.assertEqual(by_kind(self.api.national_highlights('all'),'lowest_tmin')[0]['value'],-25)
        self.assertEqual(self.api.national_highlights('year',1,2022)['records'],[])
        self.assertEqual(self.api.national_highlights('year',1,2020)['station_count'],1)
        with self.assertRaises(ValueError):self.api.national_highlights('year',1,1900)
        with self.assertRaises(ValueError):self.api.national_highlights('month',13)
        with self.assertRaises(ValueError):self.api.national_highlights('day',1)

    def test_day_highlights_supply_categories_missing_from_legacy_products(self):
        self.api.products.db.execute('CREATE TABLE precipitation_events (station_id,precip_mm,date,data_json)')
        result=self.api.on_this_day(2,2)
        records={r['record_type']:r for r in result['records'] if r['station_id']=='test'}
        self.assertEqual(records['lowest_tmax']['value'],9)
        self.assertEqual(records['highest_tmin']['value'],7)
        self.assertEqual(records['highest_tmin']['observations'][0]['source_member'],'test.txt')

    def test_highlights_ten_stations_per_category_including_wind_pressure_and_rain(self):
        for index in range(12):
            sid=f'station-{index:02d}'
            self.api.source.execute('INSERT INTO stations VALUES (?)',(sid,))
            self.api.stations[sid]={**self.api.stations['test'],'station_id':sid,'station_name':sid}
            for day in ('2024-01-01','2024-01-02'):
                # Constant wind produces more than ten tied stations at the cutoff.
                self.api.source.execute('INSERT INTO daily_observations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (sid,day,index,-index,index+10,index,0,index,5,1000+index,'[]','source.csv',index+1))
        # Exclude pressure at one station without excluding its rain or wind.
        self.api.products.db.executemany('INSERT INTO qc_exclusions VALUES (?,?,?,?)',
            [('station-11',day,'pressure_msl_hpa','suspect_pressure') for day in ('2024-01-01','2024-01-02')])
        result=self.api.national_highlights('month-year',1,2024)
        self.assertEqual(result['station_count'],12)
        for kind in result['records']:
            self.assertEqual(len(kind['dates']),2)
        for kind in ('highest_tmax','lowest_tmin','highest_precip','highest_mean_wind','highest_pressure','lowest_pressure'):
            records=[r for r in result['records'] if r['record_type']==kind]
            self.assertEqual(len(records),10)
            self.assertEqual([r['rank'] for r in records],list(range(1,11)))
            self.assertEqual(len({r['station_id'] for r in records}),10)
        pressure=[r for r in result['records'] if r['record_type']=='highest_pressure']
        self.assertEqual(pressure[0]['value'],1010)
        wind=[r for r in result['records'] if r['record_type']=='highest_mean_wind']
        self.assertEqual([r['station_id'] for r in wind],[f'station-{i:02d}' for i in range(10)])
        build_index(self.api.source,self.api.products.db)
        self.assertEqual(result,self.api.national_highlights('month-year',1,2024))


if __name__ == '__main__': unittest.main()
