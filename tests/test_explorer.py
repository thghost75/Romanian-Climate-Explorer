"""Read-only integration checks against the verified local Phase 3 snapshot."""
import io
import json
import unittest
from pathlib import Path
from anm_climate.explorer_api import Explorer, search_key
from anm_climate.explorer_http import handle_climate

ROOT=Path(__file__).resolve().parents[1]/"data/anm"
SID="0-20000-0-15085"

@unittest.skipUnless((ROOT/"climatology.sqlite").exists(),"Verified climate snapshot required")
class ExplorerTests(unittest.TestCase):
    def setUp(self): self.api=Explorer(ROOT)
    def tearDown(self): self.api.close()
    def test_valid_station_catalogue_and_search(self):
        self.assertEqual(len(self.api.catalogue()),160)
        self.assertEqual(self.api.catalogue("Bistrița"),self.api.catalogue("Bistrita"))
        self.assertEqual(self.api.catalogue(SID)[0]["station_id"],SID)
        self.assertEqual(sum(s["has_coordinates"] for s in self.api.catalogue()),140)
    def test_invalid_station_and_parameters(self):
        with self.assertRaises(LookupError): self.api.daily("bad",1,1,"1991-2020")
        for p in ({"year":"100000"},{"normal":"bad"},{"unexpected":"x"},{"month":"2","day":"30"}):
            with self.assertRaises(ValueError): self.api.dispatch("overview",{"station":SID,**p})
        with self.assertRaises(ValueError): self.api.events(SID,"rain","2024-12-31","2024-01-01")
    def test_normal_switch_and_february29(self):
        modern=self.api.daily(SID,7,15,"1991-2020")
        older=self.api.daily(SID,7,15,"1961-1990")
        self.assertNotEqual(modern["variables"]["tmean_c"]["mean"],older["variables"]["tmean_c"]["mean"])
        leap=self.api.daily(SID,2,29,"1991-2020")["variables"]["tmean_c"]
        self.assertEqual(leap["expected_count"],8)
        self.assertLessEqual(leap["sample_count"],8)
        self.assertEqual(self.api.daily(SID,2,28,"1991-2020")["variables"]["tmean_c"]["expected_count"],30)
    def test_all_record_ties_survive_aggregation(self):
        out=self.api.records(SID,"all")
        for label,r in out["records"].items():
            self.assertEqual(r["dates"],sorted(set(r["dates"])))
            self.assertEqual(r["dates"],[x["date"] for x in r["observations"]])
        # A known tied calendar record is selected from the independent stored table.
        for row in self.api.products.db.execute("SELECT calendar_day,data_json FROM daily_records WHERE station_id=?",(SID,)):
            records=json.loads(row["data_json"])
            tied=next((k for k,r in records.items() if len(r.get("dates",[]))>1),None)
            if tied:
                m,d=map(int,row["calendar_day"].split("-"))
                result=self.api.records(SID,"day",m,d)["records"][tied]
                self.assertEqual(result["dates"],records[tied]["dates"]); break
        else: self.fail("Expected a tied record in test station")
    def test_qc_flags_and_review_notes(self):
        sid="0-20000-0-15324"
        rows=self.api.observation_rows(sid,"1931-12-01","1931-12-31")
        self.assertTrue(all(r["verification_notes"] for r in rows))
        events=self.api.events(sid,"heatwave","1931-12-01","1931-12-31")
        self.assertTrue(any(e["verification_notes"] for e in events))
        raw=self.api.source.execute("SELECT station_id,date FROM daily_observations WHERE quality_flags!='[]' LIMIT 1").fetchone()
        r=self.api.observation_rows(raw["station_id"],raw["date"],raw["date"])[0]
        self.assertTrue(r["quality_flags"])
        annotated=self.api.annotate_record(raw["station_id"],{"dates":[raw["date"]],"value":r["tmax_c"]},"tmax_c")
        self.assertTrue(annotated["needs_verification"])
    def test_missing_climatology_and_incomplete_year(self):
        short="0-20000-0-15088"
        old=self.api.daily(short,7,15,"1961-1990")["variables"]["tmax_c"]
        self.assertFalse(old["eligible"]); self.assertIsNone(old["mean"])
        h=self.api.history(SID,2026,"1991-2020")
        self.assertFalse(h["annual"]["variables"]["precip_mm"]["eligible"])
        self.assertIsNone(h["annual"]["variables"]["precip_mm"]["total"])
        self.assertTrue(any(s["incomplete"] for s in self.api.catalogue()))
    def test_precip_inclusive_thresholds(self):
        # Confirm actual observations exactly at the threshold remain included.
        match=self.api.products.db.execute("SELECT station_id,date FROM precipitation_events WHERE precip_mm=20 LIMIT 1").fetchone()
        result=self.api.events(match["station_id"],"rain",match["date"],match["date"],20)
        self.assertTrue(any(r["precip_mm"]==20 for r in result))
        for threshold in (20,30,50,75,100):
            self.assertTrue(all(r["precip_mm"]>=threshold for r in self.api.events(SID,"rain","1900-01-01","2026-12-31",threshold)))
        for threshold in (0,10,19,21,float("nan")):
            with self.assertRaises(ValueError): self.api.events(SID,"rain","2024-01-01","2024-12-31",threshold)
    def test_trace_is_not_dry_or_measurable(self):
        for key in ("01-01","02-15","04-15","07-15","10-15"):
            m,d=map(int,key.split("-"))
            r=self.api.daily(SID,m,d,"1991-2020")["variables"]["precip_mm"]
            self.assertEqual(r["sample_count"],r["trace_days"]+r["dry_days"]+r["measurable_rain_days"])
        trace=self.api.source.execute("SELECT date FROM daily_observations WHERE station_id=? AND precip_trace=1 LIMIT 1",(SID,)).fetchone()[0]
        r=self.api.observation_rows(SID,trace,trace)[0]
        self.assertEqual(r["precip_mm"],0); self.assertEqual(r["precip_raw"],-1); self.assertTrue(r["precip_trace"])
    def test_date_filters_context_and_dry_wet_match_indices(self):
        events=self.api.events(SID,"heatwave","2024-07-10","2024-07-20")
        self.assertTrue(all(r["start_date"]<="2024-07-20" and r["end_date"]>="2024-07-10" for r in events))
        context=self.api.context(SID,"2024-07-10","2024-07-12")["observations"]
        self.assertEqual(context[0]["date"],"2024-07-08"); self.assertEqual(context[-1]["date"],"2024-07-14")
        indices=self.api.products.get_indices(SID,2024)
        for kind in ("dry","wet"):
            events=self.api.events(SID,kind,"2024-01-01","2024-12-31")
            self.assertEqual(max((e["duration"] for e in events),default=0),indices[f"consecutive_{kind}_days"])
        with self.assertRaises(ValueError): self.api.events(SID,"dry","1900-01-01","2026-01-01")
        with self.assertRaises(ValueError): self.api.context(SID,"1900-01-01","2026-01-01")
    def test_on_this_day_and_map(self):
        result=self.api.on_this_day(2,29)
        self.assertTrue(result["records"])
        self.assertTrue(all(r["precip_mm"]>=20 and r["date"].endswith("02-29") for r in result["extreme_rainfall"]))
        self.assertEqual(len(self.api.quality(SID)["variables"]),6)
        context=self.api.context("0-20000-0-15324","1931-12-01","1931-12-31")
        self.assertIn("1931-11-30",context["missing_dates"])
        self.assertTrue(all(d.endswith("02-29") for r in result["records"] for d in r["dates"]))
        result=self.api.map_values("temperature",7,15,"1991-2020",2024)
        self.assertEqual(len(result["stations"]),160)
    def test_daily_year_complete_leap_and_missing_days(self):
        data=self.api.daily_year("0-20000-0-15420",2025,"1991-2020")
        self.assertEqual(len(data["days"]),365)
        self.assertEqual(data["days"][0]["date"],"2025-01-01")
        self.assertEqual(data["days"][-1]["date"],"2025-12-31")
        self.assertEqual(data["coverage"]["tmean_c"],365)
        self.assertEqual(data["trace_days"],17)
        self.assertEqual(len(self.api.daily_year(SID,2024,"1991-2020")["days"]),366)
        empty=self.api.daily_year("0-20000-0-15088",1800,"1961-1990")
        self.assertTrue(all(not d["source_present"] for d in empty["days"]))
        self.assertTrue(all(d["values"]["tmean_c"] is None for d in empty["days"]))
    def test_daily_year_qc_trace_anomaly_and_normal_switch(self):
        days=self.api.daily_year("0-20000-0-15010",1897,"1991-2020")["days"]
        bad=next(d for d in days if d["date"]=="1897-03-16")
        self.assertIsNotNone(bad["raw"]["tmax_c"])
        self.assertIsNone(bad["values"]["tmax_c"])
        self.assertIn("tmax_c",bad["raw"]["excluded_variables"])
        new=self.api.daily_year(SID,2025,"1991-2020")
        old=self.api.daily_year(SID,2025,"1961-1990")
        self.assertNotEqual(new["days"][0]["normal"]["tmean_c"],old["days"][0]["normal"]["tmean_c"])
        for d in new["days"]:
            if d["tmean_anomaly"] is not None:
                self.assertAlmostEqual(d["tmean_anomaly"],d["values"]["tmean_c"]-d["normal"]["tmean_c"]["mean"])
            if d["raw"] and d["raw"]["precip_trace"]:
                self.assertEqual(d["raw"]["precip_raw"],-1)
                self.assertEqual(d["values"]["precip_mm"],0)
    def test_databases_are_read_only(self):
        import sqlite3
        for db in (self.api.source,self.api.products.db):
            with self.assertRaises(sqlite3.OperationalError): db.execute("CREATE TABLE forbidden_test(x)")

class FakeHandler:
    def __init__(self,headers=None):
        self.headers=headers or {}; self.wfile=io.BytesIO(); self.response_headers={}
    def send_response(self,status): self.status=status
    def send_header(self,k,v): self.response_headers[k]=v
    def end_headers(self): pass

@unittest.skipUnless((ROOT/"climatology.sqlite").exists(),"Verified climate snapshot required")
class HttpTests(unittest.TestCase):
    def test_http_errors_cache_and_etag(self):
        h=FakeHandler(); self.assertTrue(handle_climate(h,"/api/climate/stations","",ROOT))
        self.assertEqual(h.status,200)
        h2=FakeHandler({"If-None-Match":h.response_headers["ETag"]})
        handle_climate(h2,"/api/climate/stations","",ROOT); self.assertEqual(h2.status,304)
        for query,status in (("station=bad",404),("station=x&station=y",400),("year=no",400)):
            h=FakeHandler(); handle_climate(h,"/api/climate/overview",query,ROOT); self.assertEqual(h.status,status)
        self.assertFalse(handle_climate(FakeHandler(),"/api/other","",ROOT))
