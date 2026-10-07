"""Thermal ranges never cross station/year boundaries or bypass temperature QC."""
import unittest
from test_record_periods import RecordPeriodTests
from anm_climate.national_records import build_index
from anm_climate.thermal_records import amplitude


class ThermalRecordTests(unittest.TestCase):
    def setUp(self):
        RecordPeriodTests.setUp(self)
        self.api.source.execute("CREATE TABLE stations (station_id TEXT PRIMARY KEY)")
        self.api.source.executemany("INSERT INTO stations VALUES (?)", [("test",),("second",)])
        self.api.stations["second"]={**self.api.stations["test"], "station_id":"second", "station_name":"Second"}
        self.api.source.execute('DELETE FROM daily_observations')
        self.api.products.db.execute('DELETE FROM qc_exclusions')
        samples = [
            ('test','2020-01-01',-20,-10),
            ('test','2020-01-02',-8,0),
            ('test','2024-01-01',20,30),
            ('test','2024-01-02',0,25),
            ('test','2024-01-03',-2.9,26.5),
            ('test','2024-01-04',-30,60),  # Tmax rejected, Tmin remains eligible for excursion.
            ('test','2024-01-05',None,20),
            ('test','2024-01-06',30,10),  # Inverted pair cannot yield daily amplitude.
            ('test','2024-02-01',-40,-20),
            ('test','2024-02-02',None,None),
            ('second','2024-01-01',-50,-40),
            ('second','2024-01-02',-49,-40),
        ]
        for sid,day,low,high in samples:
            self.api.source.execute('INSERT INTO daily_observations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (sid,day,None,low,high,None,0,None,None,None,'[]','thermal.csv',1))
        self.api.products.db.execute("INSERT INTO qc_exclusions VALUES ('test','2024-01-04','tmax_c','suspect')")

    # Do not inherit unrelated fixture-dependent test cases.
    def test_daily_amplitude_uses_both_temperatures(self):
        self.assertEqual(amplitude(-2.9,26.5),29.4)
        ranked=self.api.station_rankings('test','highest_amplitude','month',1)
        self.assertEqual(ranked['ranking'][0]['value'],29.4)
        self.assertEqual(ranked['ranking'][0]['observations'][0]['tmin_c'],-2.9)
        self.assertNotIn('2024-01-04',[d for r in ranked['ranking'] for d in r['dates']])
        self.assertNotIn('2024-01-06',[d for r in ranked['ranking'] for d in r['dates']])
        self.api.products.db.execute("INSERT INTO qc_exclusions VALUES ('test','2024-01-03','tmin_c','suspect')")
        self.assertEqual(self.api.station_rankings('test','highest_amplitude','month',1)['ranking'][0]['value'],25)

    def test_excursion_stays_within_station_and_calendar_period(self):
        result=self.api.national_highlights('month',1,2024,'value')
        ranges=[r for r in result['records'] if r['record_type']=='highest_excursion']
        self.assertEqual([(r['station_id'],r['value'],r['periods'][0]['period']) for r in ranges],
                         [('test',60,'2024-01'),('test',20,'2020-01'),('second',10,'2024-01')])
        self.assertEqual(ranges[0]['periods'][0]['tmin_dates'],['2024-01-04'])
        self.assertEqual(ranges[0]['periods'][0]['tmax_dates'],['2024-01-01'])
        self.assertTrue(ranges[0]['incomplete'])
        self.assertEqual(ranges[0]['periods'][0]['tmax_days'],5)
        station=self.api.excursion_rankings('test','highest_monthly_excursion',1)
        self.assertEqual([r['value'] for r in station['ranking']],[60,20])
        annual=self.api.excursion_rankings('test','highest_yearly_excursion',1)
        self.assertEqual([r['value'] for r in annual['ranking']],[70,20])
        selected=self.api.station_rankings('test','highest_yearly_excursion','year',1,1,2020)
        self.assertEqual([r['value'] for r in selected['ranking']],[20])
        selected=self.api.station_rankings('test','highest_monthly_excursion','month-year',1,1,2024)
        self.assertEqual([r['value'] for r in selected['ranking']],[60])
        # Daily national list must not contain period excursions.
        self.assertFalse(any(r['record_type']=='highest_excursion' for r in self.api.national_highlights('day',1,2024)['records']))

    def test_all_new_rankings_match_serving_index(self):
        cases=[(scope,1,2024,mode,group,1) for scope in ('day','month','month-year','year','all')
               for mode in ('station','value') for group in ('all','flat')]
        expected=[self.api.national_highlights(*args) for args in cases]
        monthly=self.api.excursion_rankings('test','highest_monthly_excursion',1)
        annual=self.api.excursion_rankings('test','highest_yearly_excursion',1)
        build_index(self.api.source,self.api.products.db)
        self.assertEqual(expected,[self.api.national_highlights(*args) for args in cases])
        self.assertEqual(monthly,self.api.excursion_rankings('test','highest_monthly_excursion',1))
        self.assertEqual(annual,self.api.excursion_rankings('test','highest_yearly_excursion',1))
        self.assertEqual(self.api.excursion_rankings('test','highest_yearly_excursion',1,2020)['ranking'][0]['value'],20)

    def test_complete_month_and_tied_periods(self):
        self.api.source.execute('DELETE FROM daily_observations')
        for year in (2020,2024):
            for day in range(1,32):
                self.api.source.execute('INSERT INTO daily_observations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    ('test',f'{year}-01-{day:02d}',None,-2.9,26.5,None,0,None,None,None,'[]','thermal.csv',day))
        self.api.products.db.execute('DELETE FROM qc_exclusions')
        result=self.api.excursion_rankings('test','highest_monthly_excursion',1)
        self.assertEqual(len(result['ranking']),1)
        row=result['ranking'][0]
        self.assertEqual(row['value'],29.4)
        self.assertEqual(len(row['periods']),2)
        self.assertFalse(row['incomplete'])
        self.assertEqual(len(row['periods'][0]['tmin_dates']),31)
        national=self.api.national_highlights('month',1,2024,'station')
        row=next(r for r in national['records'] if r['record_type']=='highest_excursion')
        self.assertEqual(len(row['periods']),2)
        self.assertFalse(row['incomplete'])
