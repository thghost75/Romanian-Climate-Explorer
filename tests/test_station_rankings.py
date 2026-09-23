"""Station top-ten rankings are daily observations, with grouped ties and QC."""
import unittest
import test_record_periods


class StationRankingTests(unittest.TestCase):
    setUp = test_record_periods.RecordPeriodTests.setUp

    def test_month_year_leap_day_and_missing_values(self):
        month=self.api.station_rankings('test','lowest_tmin','month',2,1,2024)
        self.assertEqual([r['value'] for r in month['ranking']],[-12,-11,-10,7])
        self.assertEqual([r['rank'] for r in month['ranking']],[1,2,3,4])
        self.assertTrue(month['ranking'][0]['needs_verification'])
        self.assertEqual(month['ranking'][-1]['dates'],['2024-02-02','2024-02-03'])
        yearly=self.api.station_rankings('test','lowest_tmin','year',2,1,2024)
        self.assertEqual(yearly['ranking'][0]['date'],'2024-03-01')
        specific=self.api.station_rankings('test','highest_tmax','month-year',2,1,2024)
        self.assertEqual([r['value'] for r in specific['ranking']],[9,-8])
        leap=self.api.station_rankings('test','lowest_tmin','day',2,29,2024)
        self.assertEqual([r['date'] for r in leap['ranking']],['2020-02-29'])
        self.assertEqual(self.api.station_rankings('test','highest_tmean','all')['ranking'],[])

    def test_tenth_place_ties_and_station_isolation(self):
        self.api.source.execute('DELETE FROM daily_observations')
        for day,value in enumerate([1,2,3,4,5,6,7,8,9,10,10,11,None,-99],1):
            self.api.source.execute('INSERT INTO daily_observations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                ('test',f'2024-01-{day:02d}',None,value,None,None,0,None,None,None,'[]','test.txt',day))
        self.api.products.db.execute("INSERT INTO qc_exclusions VALUES ('test','2024-01-14','tmin_c','excluded')")
        self.api.source.execute("INSERT INTO daily_observations (station_id,date,tmin_c) VALUES ('other','2024-01-01',-100)")
        result=self.api.dispatch('station-rankings',{'station':'test','scope':'month','month':'1','kind':'lowest_tmin'})
        self.assertEqual(result['sample_count'],12)
        self.assertEqual(len(result['ranking']),10)
        self.assertEqual([r['rank'] for r in result['ranking']],list(range(1,11)))
        self.assertEqual([r['value'] for r in result['ranking']],list(range(1,11)))
        self.assertEqual(result['ranking'][-1]['dates'],['2024-01-10','2024-01-11'])
        self.assertEqual(len(result['ranking'][-1]['observations']),2)

    def test_invalid_category_scope_and_year(self):
        with self.assertRaises(ValueError):self.api.station_rankings('test','unknown')
        with self.assertRaises(ValueError):self.api.station_rankings('test',scope='bad')
        with self.assertRaises(ValueError):self.api.station_rankings('test',scope='year',year=1900)
        with self.assertRaises(LookupError):self.api.station_rankings('unknown')
