"""Rank complete period totals; gaps cannot masquerade as dry months or years."""
import calendar
import json
import unittest
import test_record_periods


class RainfallRankingTests(unittest.TestCase):
    def setUp(self):
        test_record_periods.RecordPeriodTests.setUp(self)
        self.api.products.db.execute('CREATE TABLE monthly_summary (station_id,year,month,data_json)')
        self.api.products.db.execute('CREATE TABLE annual_summary (station_id,year,data_json)')

    def add(self,year,month,total,**overrides):
        days=calendar.monthrange(year,month)[1] if month else 365+int(calendar.isleap(year))
        rain={'eligible':True,'sample_count':days,'eligible_months':12,'total':total}
        rain.update(overrides)
        data=json.dumps({'variables':{'precip_mm':rain}})
        if month:self.api.products.db.execute('INSERT INTO monthly_summary VALUES (?,?,?,?)',('test',year,month,data))
        else:self.api.products.db.execute('INSERT INTO annual_summary VALUES (?,?,?)',('test',year,data))

    def test_month_selection_zero_totals_ties_and_missing_days(self):
        self.add(2020,2,40)
        self.add(2021,2,0)
        self.add(2022,2,None,eligible=False,sample_count=7,observed_total=0)
        self.add(2023,2,0,sample_count=27)
        self.add(2024,2,40)
        self.add(2024,3,999)
        wet=self.api.station_rankings('test','wettest_month','year',2,1,2024)
        dry=self.api.station_rankings('test','driest_month','day',2,1,2024)
        self.assertEqual([r['value'] for r in wet['ranking']],[40,0])
        self.assertEqual([r['value'] for r in dry['ranking']],[0,40])
        self.assertEqual([p['year'] for p in wet['ranking'][0]['periods']],[2020,2024])
        self.assertEqual(wet['ranking'][0]['periods'][1]['expected_days'],29)
        self.assertTrue(wet['ranking'][0]['needs_verification'])
        self.assertEqual(wet['sample_count'],3)
        self.assertEqual(wet['excluded_period_count'],2)
        self.assertIsNone(wet['year'])

    def test_annual_full_archive_excludes_partial_and_ineligible_years(self):
        self.add(2020,None,700)
        self.add(2021,None,200)
        self.add(2022,None,0,eligible_months=11)
        self.add(2023,None,0,sample_count=364)
        self.add(2024,None,999,eligible=False)
        wet=self.api.dispatch('station-rankings',{'station':'test','kind':'wettest_year','year':'2024','month':'9'})
        dry=self.api.station_rankings('test','driest_year',month=1,year=2020)
        self.assertEqual([r['value'] for r in wet['ranking']],[700,200])
        self.assertEqual([r['value'] for r in dry['ranking']],[200,700])
        self.assertEqual(wet['ranking'][0]['periods'][0]['expected_days'],366)
        self.assertEqual(wet['excluded_period_count'],3)
        self.assertEqual(wet['period_unit'],'year')

    def test_ten_distinct_totals_group_float_equivalent_ties(self):
        for year in range(2000,2012):self.add(year,1,(year-1999)*10)
        self.add(2012,1,0.1+0.2)
        self.add(2013,1,0.3)
        result=self.api.station_rankings('test','driest_month',month=1)
        self.assertEqual(len(result['ranking']),10)
        self.assertEqual([r['rank'] for r in result['ranking']],list(range(1,11)))
        self.assertEqual(len(result['ranking'][0]['periods']),2)
        self.assertEqual(result['ranking'][0]['value'],0.3)
        self.assertEqual(self.api.station_rankings('test','wettest_month',month=12)['ranking'],[])
        with self.assertRaises(ValueError):self.api.station_rankings('test','wettest_month',month=13)
