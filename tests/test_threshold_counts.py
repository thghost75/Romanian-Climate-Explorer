import calendar
import sqlite3
import unittest
from datetime import date,timedelta
from types import SimpleNamespace
from anm_climate import threshold_counts as tc

class CountsTests(unittest.TestCase):
 def setUp(self):
  self.source=sqlite3.connect(':memory:'); self.products=sqlite3.connect(':memory:')
  self.addCleanup(self.source.close); self.addCleanup(self.products.close)
  self.source.execute('CREATE TABLE stations(station_id)')
  self.source.execute("INSERT INTO stations VALUES ('s')")
  self.source.execute('CREATE TABLE daily_observations(station_id,date,tmin_c,tmax_c,precip_mm,precip_trace,quality_flags)')
  self.products.execute('CREATE TABLE qc_exclusions(station_id,date,variable)')
  self.info={'station_name':'Station','first_year':2020,'last_year':2024}
  self.api=SimpleNamespace(source=self.source,products=SimpleNamespace(db=self.products),
    stations={'s':self.info},reviews=lambda *a:[],station=lambda sid:self.info,year=int)
  when=date(2024,1,1)
  while when.year==2024:
   self.source.execute('INSERT INTO daily_observations VALUES (?,?,?,?,?,?,?)',('s',str(when),20,25,0.1,0,'[]'))
   when+=timedelta(days=1)
 def update(self,day,tn,tx,rain,trace=0,flags='[]'):
  self.source.execute('UPDATE daily_observations SET tmin_c=?,tmax_c=?,precip_mm=?,precip_trace=?,quality_flags=? WHERE date=?',(tn,tx,rain,trace,flags,day))
 def test_strict_boundaries_and_trace(self):
  self.update('2024-01-01',20.1,25.1,0.2)
  self.update('2024-01-02',0,30,1)
  self.update('2024-01-03',-10,35,10)
  self.update('2024-01-04',-20,0,10.1)
  self.update('2024-01-05',-20.1,-10,None,1)
  self.update('2024-01-06',-0.1,-10.1,0)
  self.update('2024-01-07',-10.1,35.1,0)
  p=next(p for y,m,p in tc.station_periods(self.source,self.products,'s') if m==1)
  self.assertEqual(p['counts'],dict(tropical_nights=1,summer_days=4,tropical_days=2,scorching_days=1,
   frosty_days=2,freezing_days=1,frosty_nights=5,freezing_nights=3,polar_nights=1,
   rain_01_days=4,rain_1_days=2,rain_10_days=1,least_rain_01_days=4,least_rain_1_days=2,least_rain_10_days=1))
  self.assertEqual(p['coverage']['precip_mm'],31)
 def test_qc_is_variable_specific_and_incomplete_excluded(self):
  self.products.execute("INSERT INTO qc_exclusions VALUES ('s','2024-02-01','tmin_c')")
  rows=tc.national(self.api,'month-year',2,2024,'value',self.api.stations)
  self.assertFalse(any(r['record_type']=='count_tropical_nights_month' for r in rows))
  hot=next(r for r in rows if r['record_type']=='count_summer_days_month')
  self.assertEqual(hot['periods'][0]['expected_days'],29)
  self.source.execute("UPDATE daily_observations SET precip_mm=NULL WHERE date='2024-03-01'")
  self.assertEqual(tc.station_rankings(self.api,'s','count_rain_01_days_year','all',1,None)['ranking'],[])
 def test_serving_index_parity_ties_and_year_filter(self):
  before=tc.national(self.api,'all',1,None,'station',self.api.stations)
  station=tc.station_rankings(self.api,'s','count_summer_days_month','all',11,None)
  self.assertEqual(len(station['ranking']),1)
  self.assertEqual(len(station['ranking'][0]['periods']),12)
  tc.build_count_index(self.source,self.products)
  self.assertEqual(before,tc.national(self.api,'all',1,None,'station',self.api.stations))
  self.assertEqual(station,tc.station_rankings(self.api,'s','count_summer_days_month','all',11,None))
  self.assertEqual(tc.national(self.api,'year',1,2020,'value',self.api.stations),[])
  self.assertEqual(tc.national(self.api,'all',1,None,'value',{}),[])
 def test_ranking_modes_and_limit(self):
  stations={str(i):{'station_name':str(i)} for i in range(12)}
  template=next(p for y,m,p in tc.station_periods(self.source,self.products,'s') if m==1)
  entries=[]
  for sid in stations:
   for year in (2020,2021):
    p={**template,'period':f'{year}-01','counts':{**template['counts'],'summer_days':31-int(sid)}}
    entries.append((sid,p))
  by_station=tc.rank(self.api,entries,stations,'count_summer_days_month','station')[0]
  by_value=tc.rank(self.api,entries,stations,'count_summer_days_month','value')[0]
  self.assertEqual(len(by_station),10)
  self.assertTrue(all(len(r['periods'])==2 for r in by_station))
  self.assertEqual(len({r['station_id'] for r in by_station}),10)
  self.assertEqual(len(by_value),10)
  self.assertEqual(len({r['station_id'] for r in by_value}),5)

 def test_fewest_preserves_zero_and_excludes_missing_periods(self):
  self.update('2024-01-01',20,25,15)
  self.source.execute("UPDATE daily_observations SET precip_mm=NULL WHERE date='2024-03-01'")
  for indexed in (False,True):
   if indexed: tc.build_count_index(self.source,self.products)
   r=tc.station_rankings(self.api,'s','count_least_rain_10_days_month','all',1,None)
   self.assertEqual([row['value'] for row in r['ranking']],[0,1])
   zero=r['ranking'][0]
   self.assertEqual(len(zero['periods']),10)
   self.assertNotIn('2024-03',[p['period'] for p in zero['periods']])
   self.assertEqual(r['excluded_period_count'],1)
   rows=tc.national(self.api,'month-year',2,2024,'value',self.api.stations)
   result=next(r for r in rows if r['record_type']=='count_least_rain_01_days_month')
   self.assertEqual(result['value'],0)
