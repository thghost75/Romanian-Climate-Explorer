"""Records use the requested dates, variable-specific QC and every tied date."""
import sqlite3
from types import SimpleNamespace
import unittest

from anm_climate.explorer_api import Explorer, RECORD_VARIABLES
from anm_climate.phase3_api import ClimatologyStore


class RecordPeriodTests(unittest.TestCase):
    def setUp(self):
        self.api=Explorer.__new__(Explorer)
        self.api.notes=[]
        self.api.stations={'test':{'station_id':'test','station_name':'Test','missing_years':'[]',
            'latitude':44,'longitude':26,'completeness_percent':80,'first_year':2020,'last_year':2024,
            'first_observation':'2020-02-29','last_observation':'2024-03-01'}}
        self.api.source=sqlite3.connect(':memory:')
        self.api.source.row_factory=sqlite3.Row
        self.addCleanup(self.api.source.close)
        self.api.source.execute('''CREATE TABLE daily_observations (
            station_id,date,tmean_c,tmin_c,tmax_c,precip_mm,precip_trace,precip_raw,
            wind_mean_ms,pressure_msl_hpa,quality_flags,source_member,source_line)''')
        self.rows=[('2020-02-29',-12,-8),('2021-02-28',-10,-5),('2024-02-01',-11,-8),
                   ('2024-02-02',7,9),('2024-02-03',7,99),('2024-02-04',None,None),('2024-03-01',-25,-20)]
        for day,tn,tx in self.rows:
            self.api.source.execute('INSERT INTO daily_observations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                ('test',day,None,tn,tx,0,0,0,None,None,'["source-note"]','test.txt',1))
        products=sqlite3.connect(':memory:')
        products.row_factory=sqlite3.Row
        self.addCleanup(products.close)
        products.execute('CREATE TABLE qc_exclusions (station_id,date,variable,reason)')
        products.execute("INSERT INTO qc_exclusions VALUES ('test','2024-02-03','tmax_c','outside_physical_screen')")
        # Legacy snapshots have only the original categories, forcing the compatibility path.
        self.api.products=SimpleNamespace(db=products,day=ClimatologyStore.day,get_daily_records=lambda *a:{'records':{}})

    def test_month_preserves_ties_and_variable_specific_qc(self):
        records=self.api.records('test','month',2,1)['records']
        self.assertEqual(records['lowest_tmax']['value'],-8)
        self.assertEqual(records['lowest_tmax']['dates'],['2020-02-29','2024-02-01'])
        self.assertEqual(records['lowest_tmax']['sample_count'],4)
        self.assertEqual(records['highest_tmin']['value'],7)
        self.assertEqual(records['highest_tmin']['dates'],['2024-02-02','2024-02-03'])
        self.assertEqual(records['highest_tmin']['sample_count'],5)
        self.assertTrue(records['highest_tmin']['needs_verification'])
        self.assertEqual(records['highest_tmean']['value'],None)
        self.assertEqual(records['highest_tmean']['sample_count'],0)

    def test_year_and_specific_month_do_not_include_other_years(self):
        annual=self.api.records('test','year',2,1,2024)
        month=self.api.records('test','month-year',2,1,2024)
        self.assertEqual(annual['records']['lowest_tmax']['value'],-20)
        self.assertEqual(annual['records']['lowest_tmax']['dates'],['2024-03-01'])
        self.assertEqual(month['records']['lowest_tmax']['dates'],['2024-02-01'])
        self.assertEqual(month['records']['lowest_tmax']['sample_count'],2)
        self.assertEqual(month['period_label'],'February 2024')
        self.assertEqual(annual['period_label'],'Year 2024')
        self.assertEqual(set(annual['records']),set(RECORD_VARIABLES))

    def test_leap_day_empty_period_and_invalid_year(self):
        self.assertEqual(self.api.records('test','day',2,29)['records']['lowest_tmax']['dates'],['2020-02-29'])
        empty=self.api.records('test','month-year',2,1,2022)['records']['highest_tmin']
        self.assertIsNone(empty['value'])
        self.assertEqual(empty['dates'],[])
        self.assertEqual(empty['sample_count'],0)
        with self.assertRaises(ValueError): self.api.records('test','year',1,1,2019)
        with self.assertRaises(ValueError): self.api.records('test','unsupported')
