import calendar
import json
import math
import sqlite3
import tempfile
import unittest
from datetime import date,timedelta
from pathlib import Path
from anm_climate.phase3_policy import *
from anm_climate.phase3_products import *
from anm_climate.snapshot_products import SCHEMA,save_station,dumps
from anm_climate.phase3_api import ClimatologyStore

def row(day,ta=10,tn=5,tx=15,rain=0,trace=False,wind=2,pressure=1013):
    return {"date":day,"tmean_c":ta,"tmin_c":tn,"tmax_c":tx,"precip_mm":rain,
            "precip_raw":-1 if trace else rain,"precip_trace":trace,"wind_mean_ms":wind,
            "pressure_msl_hpa":pressure,"quality_flags":"[]"}

class PolicyTests(unittest.TestCase):
    def test_per_variable_pressure_and_sentinels(self):
        r=row("1950-01-01",rain=-999,wind=-999,pressure=1250)
        self.assertFalse(eligibility(r,"precip_mm")[0]); self.assertFalse(eligibility(r,"wind_mean_ms")[0])
        self.assertFalse(eligibility(r,"pressure_msl_hpa")[0]); self.assertTrue(eligibility(r,"tmax_c")[0])
        trace=row("2000-01-01",rain=0,trace=True)
        self.assertTrue(eligibility(trace,"precip_mm")[0])
    def test_conflicts_do_not_drop_unrelated_values(self):
        r=row("2000-01-01",ta=10,tn=20,tx=15,rain=5)
        self.assertFalse(eligibility(r,"tmin_c")[0]); self.assertFalse(eligibility(r,"tmax_c")[0])
        self.assertFalse(eligibility(r,"tmean_c")[0]); self.assertTrue(eligibility(r,"precip_mm")[0])
    def test_pressure_regime_tail(self):
        rows=[row(f"1950-01-{i:02d}",pressure=1200 if i<=20 else 1090) for i in range(1,32)]
        self.assertEqual(pressure_quarantine(rows),{1950})
        self.assertEqual(eligibility(rows[-1],"pressure_msl_hpa",{1950}),(False,"suspect_pressure_station_year"))
    def test_leap_expected_and_no_mixing(self):
        self.assertEqual(calendar_expected("1991-2020")["02-29"],8)
        rows=[row(f"{y}-02-29",tx=40) for y in range(1991,2021) if calendar.isleap(y)]
        rows += [row(f"{y}-02-28",tx=10) for y in range(1991,2021)]
        d,_,_=daily_products(rows,Policy())
        self.assertEqual(d[("1991-2020","02-29","tmax_c")]["mean"],40)
        self.assertEqual(d[("1991-2020","02-28","tmax_c")]["mean"],10)
        self.assertIsNone(d[("1991-2020","03-01","tmax_c")]["mean"])
    def test_incomplete_normal_and_trace_denominator(self):
        rows=[row(f"{y}-01-01",rain=0,trace=y%2==0) for y in range(1991,2014)]
        d,_,_=daily_products(rows,Policy())
        self.assertFalse(d[("1991-2020","01-01","precip_mm")]["eligible"])
        rows.append(row("2014-01-01",rain=1))
        d,_,_=daily_products(rows,Policy())
        rain=d[("1991-2020","01-01","precip_mm")]
        self.assertTrue(rain["eligible"]); self.assertEqual(rain["sample_count"],24)
        self.assertEqual(rain["trace_days"]+rain["dry_days"]+rain["measurable_rain_days"],24)
        self.assertEqual(rain["probability_ge"]["1"],1/24)
    def test_quantile_and_midrank(self):
        self.assertAlmostEqual(quantile([0,10,20,30],90),27)
        self.assertEqual(percentile_rank([0,0,10,20],0),25)
        self.assertEqual(percentile_rank([0,10],20),100)
    def test_record_ties_all_dates(self):
        d,w,records=daily_products([row("2000-07-01",tx=35),row("2001-07-01",tx=35)],Policy())
        self.assertEqual(records["07-01"]["highest_tmax"]["dates"],["2000-07-01","2001-07-01"])
        self.assertEqual(records["07-01"]["lowest_tmax"]["value"],35)
        self.assertEqual(records["07-01"]["lowest_tmax"]["dates"],["2000-07-01","2001-07-01"])
        self.assertEqual(records["07-01"]["highest_tmin"]["dates"],["2000-07-01","2001-07-01"])
    def test_month_missing_and_zero_are_distinct(self):
        rows=[row(f"2024-07-{d:02d}",rain=1) for d in range(1,31)]
        obj=month_summary(2024,7,rows,Policy())
        self.assertIsNone(obj["variables"]["precip_mm"]["total"])
        self.assertEqual(obj["variables"]["precip_mm"]["observed_total"],30)
        self.assertTrue(obj["variables"]["tmean_c"]["eligible"])
        obj=month_summary(2024,7,[],Policy())
        self.assertIsNone(obj["variables"]["precip_mm"]["observed_total"])
    def test_long_monthly_gap(self):
        rows=[row(f"2024-07-{d:02d}") for d in range(1,32) if d not in (10,11,12,13)]
        obj=month_summary(2024,7,rows,Policy(monthly_fraction=0.8))
        self.assertFalse(obj["variables"]["tmean_c"]["eligible"])
    def test_annual_incomplete_and_day_weighting(self):
        months=[month_summary(2024,m,[row(f"2024-{m:02d}-{d:02d}",ta=m,rain=1) for d in range(1,calendar.monthrange(2024,m)[1]+1)],Policy()) for m in range(1,13)]
        a=annual_summary(2024,months,Policy())
        expected=sum(m*calendar.monthrange(2024,m)[1] for m in range(1,13))/366
        self.assertAlmostEqual(a["variables"]["tmean_c"]["mean"],expected)
        self.assertEqual(a["variables"]["precip_mm"]["total"],366)
        months[-1]=month_summary(2024,12,[],Policy())
        self.assertIsNone(annual_summary(2024,months,Policy())["variables"]["tmean_c"]["mean"])
    def test_indices_inclusive_thresholds_and_gaps(self):
        rows=[row("2020-01-01",tn=0,tx=25,rain=10),row("2020-01-02",tn=20,tx=30,rain=20),
              row("2020-01-04",tn=-1,tx=35,rain=0),row("2020-01-05",rain=None)]
        out=indices(rows,Policy())[2020]
        self.assertEqual(out["summer_days"]["count"],3)
        self.assertEqual(out["heavy_precip_days"]["count"],2)
        self.assertEqual(out["very_heavy_precip_days"]["count"],1)
        self.assertEqual(out["consecutive_wet_days"],2); self.assertEqual(out["consecutive_dry_days"],1)
        self.assertFalse(out["summer_days"]["complete"])
    def test_events_cross_year_and_missing_break(self):
        windows={(k,v):{"eligible":True,"threshold":30 if v=="tmax_c" else 0,
              "mean":20 if v=="tmax_c" else 5,"sorted_samples":[0,20,30],"sample_count":30}
              for k in CALENDAR for v in ("tmax_c","tmin_c")}
        rows=[row("2020-12-30",tx=32),row("2020-12-31",tx=32),row("2021-01-01",tx=32),
              row("2021-01-03",tx=32),row("2021-01-04",tx=None)]
        out=temperature_events(rows,windows,Policy(),"heatwave")
        self.assertEqual(len(out),1); self.assertEqual(out[0]["duration"],3)
        self.assertEqual(out[0]["cumulative_temperature_anomaly"],36)
        self.assertEqual(out[0]["mean_temperature_anomaly"],12)
        cold=temperature_events([row(f"2020-01-{d:02d}",tn=-2) for d in range(1,4)],windows,Policy(),"cold")
        self.assertEqual(cold[0]["duration"],3); self.assertEqual(cold[0]["cumulative_temperature_anomaly"],-21)
    def test_custom_window_percentiles_and_cold_variable(self):
        policy=Policy(window_radius=1,heat_percentile=95,cold_percentile=5,min_duration=2,cold_variable="tmean_c")
        rows=[]
        for year in range(1991,2021):
            for day,tx,ta in ((14,10,2),(15,20,4),(16,30,6)):
                rows.append(row(f"{year}-07-{day:02d}",tx=tx,ta=ta))
        daily,windows,_=daily_products(rows,policy)
        heat=windows[("07-15","tmax_c")]
        self.assertTrue(heat["eligible"]); self.assertEqual(heat["sample_count"],90)
        self.assertEqual(heat["expected_count"],90); self.assertEqual(heat["threshold"],30)
        self.assertEqual(windows[("07-15","tmean_c")]["threshold"],2)
        mock={(key,"tmean_c"):{"eligible":True,"threshold":2,"mean":4,"sorted_samples":[2,4,6],"sample_count":90} for key in CALENDAR}
        events=temperature_events([row("2024-07-15",ta=1),row("2024-07-16",ta=2)],mock,policy,"cold")
        self.assertEqual(events[0]["duration"],2)

    def test_percentile_rain_does_not_mark_dry_or_trace_days(self):
        policy=Policy()
        baseline=[row(f"{y}-07-15",rain=0,trace=y%2==0) for y in range(1991,2021)]
        daily,_,_=daily_products(baseline,policy)
        events=precipitation_events(baseline+[row("2024-07-15",rain=1),row("2025-07-15",rain=50)],daily,policy)
        self.assertEqual([e["date"] for e in events],["2024-07-15","2025-07-15"])
        self.assertTrue(events[0]["percentile_extreme"])
        self.assertEqual(events[1]["thresholds_ge"],[20,30,50])

    def test_calendar_window_wrap_and_leap(self):
        self.assertEqual(window_keys("01-01",1),["12-31","01-01","01-02"])
        self.assertEqual(window_keys("03-01",1),["02-29","03-01","03-02"])

class ApiTests(unittest.TestCase):
    def test_database_api_and_missing_baseline(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as tmp:
            path=Path(tmp)/"derived.sqlite"
            db=sqlite3.connect(path); db.executescript(SCHEMA)
            policy=Policy(window_radius=0)
            rows=[row(f"{y}-07-15",tx=30,rain=50) for y in range(1991,2021)]
            with db:
                save_station(db,"test",rows,policy)
                db.executemany("INSERT INTO metadata VALUES (?,?)",[("policy",dumps(vars(policy))),("state",dumps("complete"))])
            db.close()
            with ClimatologyStore(path) as api:
                self.assertEqual(api.get_daily_climatology("test",7,15)["variables"]["tmax_c"]["sample_count"],30)
                self.assertEqual(api.get_temperature_percentile("test",7,15,30)["percentile"],50)
                context=api.forecast_context("test",7,15,35)
                self.assertEqual(context["anomaly"],5); self.assertEqual(len(context["record"]["dates"]),30)
                self.assertEqual(len(api.get_extreme_precip_events("test",50)),30)
                self.assertEqual(api.forecast_context("test",2,29,20)["normal_value"],None)
                with self.assertRaises(ValueError): api.get_extreme_precip_events("test",10)
                with self.assertRaises(ValueError): api.get_daily_climatology("test",2,30)
    def test_unfinished_database_rejected(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as tmp:
            path=Path(tmp)/"d.sqlite"; db=sqlite3.connect(path);db.executescript(SCHEMA)
            db.execute("INSERT INTO metadata VALUES ('policy',?)",(dumps(vars(Policy())),));db.commit();db.close()
            with self.assertRaises(RuntimeError): ClimatologyStore(path)

if __name__=="__main__": unittest.main()
