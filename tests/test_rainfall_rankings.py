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
        for kind,ordered in [('wettest_month',[999,40,0]),('driest_month',[0,40,999])]:
            result=self.api.station_rankings('test',kind,'all',11,1,2021)
            self.assertEqual([r['value'] for r in result['ranking']],ordered)
            self.assertEqual(result['sample_count'],4)
            self.assertEqual(result['excluded_period_count'],2)
            march=next(r for r in result['ranking'] if r['value']==999)
            self.assertEqual(march['periods'][0]['end_date'],'2024-03-31')

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

    def test_national_rain_totals_and_serving_index(self):
        from anm_climate.national_rainfall import build_rain_index, highlights
        for year,total in [(2020,90),(2021,0),(2024,90)]:
            self.add(year,2,total)
        self.add(2022,2,990,sample_count=2)
        self.add(2022,3,500)
        self.add(2020,None,550)
        self.add(2021,None,0,eligible_months=6)
        def check():
            def get(scope,ranking):
                return highlights(self.api,scope,2,2021,ranking,self.api.stations)
            wet,dry=get('month','station')
            self.assertEqual([p['period'] for p in wet['periods']],['2020-02','2024-02'])
            self.assertEqual((wet['value'],dry['value']),(90,0))
            self.assertEqual([r['value'] for r in get('month','value')[:3]],[90,90,0])
            self.assertEqual(get('month-year','station')[0]['value'],0)
            self.assertEqual(get('year','value'),[])
            self.assertEqual(get('all','station')[1]['record_type'],'driest_year')
            self.assertEqual(get('all','station')[1]['value'],550)
            self.assertEqual(highlights(self.api,'month',2,2021,'station',{}),[])
            all_months=highlights(self.api,'all',11,2021,'station',self.api.stations,all_months=True)
            self.assertEqual([(r['record_type'],r['value']) for r in all_months],[('wettest_month',500)])
            self.assertEqual(all_months[0]['periods'][0]['period'],'2022-03')
            selected=highlights(self.api,'year',11,2020,'value',self.api.stations,all_months=True)
            self.assertEqual(selected[0]['value'],90)
            self.assertEqual(selected[0]['periods'][0]['period'],'2020-02')
            self.assertEqual(highlights(self.api,'all',11,2020,'value',{},all_months=True),[])
        check()
        build_rain_index(self.api.products.db)
        check()

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
