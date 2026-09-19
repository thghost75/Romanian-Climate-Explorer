"""Phase 4A transport-neutral, read-only explorer service.

Source reads are bounded by station/date. Statistical products always come from
Phase 3. No ingestion, migration, database writes, or network access occurs here.
"""
import json
import math
import sqlite3
import unicodedata
from datetime import date, timedelta
from pathlib import Path

from .config import DEFAULT_ROOT, readonly_uri
from .phase3_api import ClimatologyStore
from .phase3_policy import PERIODS, VARIABLES, CALENDAR

RECORD_VARIABLES = {
    "highest_tmax": "tmax_c", "lowest_tmin": "tmin_c",
    "highest_tmean": "tmean_c", "lowest_tmean": "tmean_c",
    "highest_precip": "precip_mm", "highest_mean_wind": "wind_mean_ms",
    "highest_pressure": "pressure_msl_hpa", "lowest_pressure": "pressure_msl_hpa",
}
def search_key(value):
    return "".join(c for c in unicodedata.normalize("NFKD", str(value)).casefold()
                   if not unicodedata.combining(c)).replace("ţ", "t").replace("ş", "s")

def readonly(path):
    db = sqlite3.connect(readonly_uri(path), uri=True)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA query_only=ON")
    return db

class Explorer:
    def __init__(self, root=DEFAULT_ROOT):
        self.root = Path(root)
        self.source = readonly(self.root / "climate.sqlite")
        try:
            self.products = ClimatologyStore(self.root / "climatology.sqlite")
        except Exception:
            self.source.close()
            raise
        notes = self.root / "processed/phase3/candidate_review_notes.json"
        self.notes = json.loads(notes.read_text(encoding="utf-8")) if notes.exists() else []
        self.stations = {r["station_id"]: dict(r) for r in self.source.execute(
            "SELECT station_id,station_name,latitude,longitude,elevation_m,first_observation,"
            "last_observation,observation_days,completeness_percent,first_year,last_year,"
            "missing_years FROM stations")}
    def quality(self,station):
        self.station(station)
        return {"station_id":station,"variables":[dict(r) for r in self.products.db.execute(
            "SELECT variable,eligible_count,missing_count,excluded_count FROM qc_counts WHERE station_id=?",(station,))],
            "verification_notes":[n for n in self.notes if n["station_id"]==station],
            "policy":"Variable-level exclusions affect derived statistics only. Raw source measurements are preserved."}
    def close(self):
        self.source.close()
        self.products.close()
    def __enter__(self): return self
    def __exit__(self, *args): self.close()
    def station(self, station):
        if station not in self.stations:
            raise LookupError("Unknown station ID")
        obj = dict(self.stations[station])
        obj["missing_years"] = json.loads(obj["missing_years"])
        obj["has_coordinates"] = (
            isinstance(obj["latitude"], (int, float)) and
            isinstance(obj["longitude"], (int, float)) and
            math.isfinite(obj["latitude"]) and math.isfinite(obj["longitude"]) and
            -90 <= obj["latitude"] <= 90 and -180 <= obj["longitude"] <= 180)
        obj["incomplete"] = obj["completeness_percent"] is None or obj["completeness_percent"] < 100
        return obj
    def catalogue(self, query=""):
        q = search_key(query)
        return [self.station(sid) for sid, s in self.stations.items()
                if q in search_key(sid + " " + (s["station_name"] or ""))]
    @staticmethod
    def normal(normal):
        if normal not in PERIODS: raise ValueError("Unsupported normal period")
        return normal
    @staticmethod
    def year(year):
        year = int(year)
        if not 1800 <= year <= 2200: raise ValueError("Year must be between 1800 and 2200")
        return year
    @staticmethod
    def dates(start, end):
        a, b = date.fromisoformat(start), date.fromisoformat(end)
        if a.isoformat()!=start or b.isoformat()!=end: raise ValueError("Use ISO dates YYYY-MM-DD")
        if a > b: raise ValueError("Start date must not follow end date")
        if a.year < 1800 or b.year > 2200: raise ValueError("Dates must be between 1800 and 2200")
        return a, b
    def reviews(self, station, start, end):
        return [n for n in self.notes if n["station_id"] == station and
                n["start_date"] <= end and n["end_date"] >= start]
    def observation_rows(self, station, start, end, max_days=370):
        self.station(station)
        a, b = self.dates(start, end)
        if (b-a).days + 1 > max_days: raise ValueError(f"Observation range limited to {max_days} days")
        exclusions = {}
        for r in self.products.db.execute(
            "SELECT date,variable,reason FROM qc_exclusions WHERE station_id=? AND date BETWEEN ? AND ?",
            (station, start, end)):
            exclusions.setdefault(r["date"], {})[r["variable"]] = r["reason"]
        rows = []
        for r in self.source.execute(
            "SELECT date,tmean_c,tmin_c,tmax_c,precip_mm,precip_trace,precip_raw,wind_mean_ms,"
            "pressure_msl_hpa,quality_flags,source_member,source_line FROM daily_observations "
            "WHERE station_id=? AND date BETWEEN ? AND ? ORDER BY date", (station,start,end)):
            obj = dict(r)
            obj["quality_flags"] = json.loads(obj["quality_flags"])
            obj["excluded_variables"] = exclusions.get(obj["date"], {})
            obj["verification_notes"] = self.reviews(station,obj["date"],obj["date"])
            rows.append(obj)
        return rows
    def daily(self, station, month, day, normal):
        self.station(station)
        return self.products.get_daily_climatology(station,int(month),int(day),self.normal(normal))
    def annotate_record(self, station, record, variable):
        obj = dict(record)
        obj["observations"] = []
        for when in obj.get("dates", []):
            rows = self.observation_rows(station, when, when)
            if rows:
                r = rows[0]
                obj["observations"].append({"date": when, "value": r[variable],
                    "quality_flags": r["quality_flags"], "excluded_variables": r["excluded_variables"],
                    "verification_notes": r["verification_notes"],
                    "source_member": r["source_member"], "source_line": r["source_line"]})
        obj["needs_verification"] = any(r["quality_flags"] or r["verification_notes"] for r in obj["observations"])
        return obj
    def records(self, station, scope="day", month=1, day=1):
        self.station(station)
        month, day = int(month), int(day)
        self.products.day(month, day)
        if scope not in ("day","month","all"): raise ValueError("Record scope must be day, month or all")
        keys = [f"{month:02d}-{day:02d}"] if scope == "day" else [
            k for k in CALENDAR if scope == "all" or k.startswith(f"{month:02d}-")]
        merged = {}
        for key in keys:
            m,d = map(int,key.split("-"))
            for label,r in self.products.get_daily_records(station,m,d)["records"].items():
                if r.get("value") is None: continue
                old = merged.get(label)
                better = old is None or (r["value"] < old["value"] if label.startswith("lowest") else r["value"] > old["value"])
                total = (old or {}).get("sample_count",0) + r.get("sample_count",0)
                if better: merged[label] = dict(r)
                elif r["value"] == old["value"]:
                    old["dates"] = sorted(set(old["dates"] + r["dates"]))
                    old["years"] = sorted(set(old["years"] + r["years"]))
                merged[label]["sample_count"] = total
        return {"station_id":station,"scope":scope,"calendar_day":f"{month:02d}-{day:02d}",
            "records":{k:self.annotate_record(station,r,RECORD_VARIABLES[k]) for k,r in merged.items()},
            "qc_policy":"Phase 3 variable-level eligibility; all tied dates retained. Other-variable flags remain visible."}
    def overview(self, station, month, day, normal):
        return {"station":self.station(station),"daily":self.daily(station,month,day,normal),
                "records":self.records(station,"day",month,day)}
    def series(self, station, normal):
        s = self.station(station); self.normal(normal)
        return {"station_id":station,"normal":normal,"annual_anomaly_normal":self.products.policy["normal"],
            "monthly_normals":[{"month":m,"variables":self.products.get_monthly_climatology(station,m,normal)}
                               for m in range(1,13)],
            "annual":[a for y in range(s["first_year"],s["last_year"]+1)
                      if (a:=self.products.get_annual_summary(station,y)) is not None]}
    def cycle(self, station, normal):
        self.station(station); self.normal(normal)
        return [self.daily(station,*map(int,k.split("-")),normal) for k in CALENDAR]
    def history(self, station, year, normal):
        self.station(station); year=self.year(year); self.normal(normal)
        monthly=[{"month":m,"actual":self.products.get_monthly_summary(station,year,m),
                  "normal":self.products.get_monthly_climatology(station,m,normal)} for m in range(1,13)]
        annual=self.products.get_annual_summary(station,year)
        wet = [(m["actual"]["variables"]["precip_mm"].get("maximum"),m["actual"]["variables"]["precip_mm"].get("wettest_dates",[]))
               for m in monthly if m["actual"]]
        maximum=max((x for x,ds in wet if x is not None),default=None)
        return {"station_id":station,"year":year,"normal":normal,"annual_anomaly_normal":self.products.policy["normal"],
                "annual":annual,"monthly":monthly,"indices":self.products.get_indices(station,year),
                "wettest_day":{"value":maximum,"dates":[d for x,ds in wet if x==maximum for d in ds]}}
    def events(self, station, kind, start, end, threshold=50):
        self.station(station); a,b=self.dates(start,end)
        if kind in ("dry","wet"):
            if b.year-a.year > 10: raise ValueError("Dry/wet catalogues are limited to 11 calendar years per request")
            result=[]
            # Match Phase 3 annual CDD/CWD: runs are clipped at calendar-year boundaries.
            for y in range(a.year,b.year+1):
                rows=self.observation_rows(station,f"{y}-01-01",f"{y}-12-31",366)
                run=[]; previous=None
                def finish():
                    if run:
                        result.append({"kind":kind,"start_date":run[0]["date"],"end_date":run[-1]["date"],
                            "duration":len(run),"precip_mm":sum(r["precip_mm"] for r in run),
                            "trace_days":sum(bool(r["precip_trace"]) for r in run),
                            "scope":"Calendar-year clipped observed run; missing/ineligible days break runs."})
                    run.clear()
                for r in rows:
                    current=date.fromisoformat(r["date"])
                    if previous is not None and (current-previous).days != 1: finish()
                    previous=current
                    p=r["precip_mm"]
                    valid=p is not None and "precip_mm" not in r["excluded_variables"]
                    hit=valid and (p<self.products.policy["wet_day_mm"] if kind=="dry" else p>=self.products.policy["wet_day_mm"])
                    if hit: run.append(r)
                    else: finish()
                finish()
            result=[r for r in result if r["start_date"]<=end and r["end_date"]>=start]
        elif kind in ("heatwave","cold"):
            method=self.products.get_heatwaves if kind=="heatwave" else self.products.get_cold_events
            result=[r for r in method(station,a.year,b.year) if r["start_date"]<=end and r["end_date"]>=start]
        elif kind=="rain":
            threshold=float(threshold)
            if threshold not in self.products.policy["extreme_thresholds"]: raise ValueError("Use rainfall threshold 20, 30, 50, 75 or 100 mm")
            result=self.products.get_extreme_precip_events(station,threshold,start,end)
        else: raise ValueError("Unknown event kind")
        flagged = [r["date"] for r in self.source.execute(
            "SELECT date FROM daily_observations WHERE station_id=? AND date BETWEEN ? AND ? AND quality_flags!='[]'",
            (station, min((r.get("start_date",r.get("date")) for r in result),default=start),
             max((r.get("end_date",r.get("date")) for r in result),default=end)))]
        for r in result:
            first=r.get("start_date",r.get("date")); last=r.get("end_date",r.get("date"))
            r["station_id"]=station
            r["flagged_dates"]=[d for d in flagged if first<=d<=last]
            r["verification_notes"]=self.reviews(station,first,last)
        return result
    def context(self, station, start, end):
        a,b=self.dates(start,end)
        rows=self.observation_rows(station,(a-timedelta(days=2)).isoformat(),(b+timedelta(days=2)).isoformat())
        present={r["date"] for r in rows}
        missing=[(a+timedelta(days=i)).isoformat() for i in range(-2,(b-a).days+3) if (a+timedelta(days=i)).isoformat() not in present]
        return {"station_id":station,"event_start":start,"event_end":end,"observations":rows,"missing_dates":missing,
                "note":"Raw source values retained; excluded variables are unsuitable for derived statistics."}
    def daily_year(self, station, year, normal):
        """A bounded year of raw observations, QC-eligible values and Phase 3 normals."""
        station_info=self.station(station); year=self.year(year); self.normal(normal)
        start=date(year,1,1); end=date(year,12,31)
        raw={r["date"]:r for r in self.observation_rows(station,start.isoformat(),end.isoformat(),366)}
        rows=[]
        for i in range((end-start).days+1):
            when=start+timedelta(days=i); key=when.isoformat(); observed=raw.get(key)
            norms=self.daily(station,when.month,when.day,normal)["variables"]
            values={v: observed[v] if observed and v not in observed["excluded_variables"] else None for v in VARIABLES}
            baseline={v:{k:obj.get(k) for k in ("mean","p10","p90","sample_count","eligible")} for v,obj in norms.items()}
            rows.append({"date":key,"source_present":observed is not None,
                "raw":observed,"values":values,"normal":baseline,
                "tmean_anomaly":values["tmean_c"]-baseline["tmean_c"]["mean"]
                    if values["tmean_c"] is not None and baseline["tmean_c"]["mean"] is not None else None})
        return {"station":station_info,"year":year,"normal_period":normal,"days":rows,
                "coverage":{v:sum(r["values"][v] is not None for r in rows) for v in VARIABLES},
                "trace_days":sum(bool(r["raw"] and r["raw"]["precip_trace"]) for r in rows),
                "excluded_values":sum(len(r["raw"]["excluded_variables"]) for r in rows if r["raw"]),
                "note":"Charts use Phase 3 variable-level QC. Raw values and exclusions remain inspectable. Missing days remain gaps."}

    def on_this_day(self, month, day):
        self.products.day(int(month),int(day))
        rows=[]
        for sid in self.stations:
            record=self.records(sid,"day",month,day)
            for key in ("highest_tmax","lowest_tmin","highest_precip"):
                r=record["records"].get(key)
                if r:
                    rows.append({"station_id":sid,"station_name":self.stations[sid]["station_name"],"record_type":key,**r})
        key=self.products.day(int(month),int(day))
        rain=[]
        for r in self.products.db.execute(
            "SELECT station_id,data_json FROM precipitation_events WHERE precip_mm>=20 AND substr(date,6)=? ORDER BY precip_mm DESC",(key,)):
            event=json.loads(r["data_json"]); sid=r["station_id"]
            event["station_id"]=sid; event["station_name"]=self.stations[sid]["station_name"]
            observed=self.observation_rows(sid,event["date"],event["date"])
            event["flagged_dates"]=[event["date"]] if observed and observed[0]["quality_flags"] else []
            event["verification_notes"]=self.reviews(sid,event["date"],event["date"])
            rain.append(event)
        return {"calendar_day":key,"records":rows,"extreme_rainfall":rain}
    def map_values(self, mode, month, day, normal, year):
        self.normal(normal); self.products.day(int(month),int(day)); year=self.year(year)
        if mode not in ("stations","temperature","anomaly","rainfall","extremes"): raise ValueError("Unknown map mode")
        rows=[]
        for s in self.catalogue():
            value=None; sample_count=None; sample_unit="years"; needs_verification=False
            if mode in ("temperature","rainfall"):
                v="tmean_c" if mode=="temperature" else "precip_mm"
                stat=self.daily(s["station_id"],month,day,normal)["variables"].get(v,{})
                value=stat.get("mean"); sample_count=stat.get("sample_count")
            elif mode=="anomaly":
                a=self.products.get_annual_summary(s["station_id"],year)
                value=a["variables"]["tmean_c"].get("anomaly") if a else None
                sample_count=a["variables"]["tmean_c"].get("sample_count") if a else 0; sample_unit="days"
            elif mode=="extremes":
                r=self.products.get_daily_records(s["station_id"],int(month),int(day))
                record=r["records"].get("highest_tmax",{})
                value=record.get("value"); sample_count=record.get("sample_count"); sample_unit="days"
                needs_verification=self.annotate_record(s["station_id"],record,"tmax_c").get("needs_verification",False)
            rows.append({**s,"value":value,"sample_count":sample_count,"sample_unit":sample_unit,"needs_verification":needs_verification})
        return {"mode":mode,"normal":self.products.policy["normal"] if mode=="anomaly" else normal,
                "year":year,"stations":rows}
    def dispatch(self, endpoint, params):
        allowed={"station","normal","month","day","year","scope","start","end","kind","threshold","q","mode","value","variable"}
        if set(params)-allowed: raise ValueError("Unknown query parameter")
        def get(k,d=None): return params.get(k,d)
        station=get("station"); normal=get("normal","1991-2020")
        self.normal(normal)
        month=int(get("month",date.today().month)); day=int(get("day",date.today().day))
        year=self.year(get("year",date.today().year))
        if endpoint=="daily-year": return self.daily_year(station,year,normal)
        if endpoint=="quality": return self.quality(station)
        if endpoint=="stations": return self.catalogue(get("q",""))
        if endpoint=="overview": return self.overview(station,month,day,normal)
        if endpoint=="daily": return self.daily(station,month,day,normal)
        if endpoint=="records": return self.records(station,get("scope","day"),month,day)
        if endpoint in ("temperature","rainfall"):
            data=self.series(station,normal)
            keep={"tmean_c","tmin_c","tmax_c"} if endpoint=="temperature" else {"precip_mm"}
            for r in data["monthly_normals"]+data["annual"]:
                if r.get("variables"): r["variables"]={k:v for k,v in r["variables"].items() if k in keep}
            return data
        if endpoint=="cycle": return self.cycle(station,normal)
        if endpoint in ("history","annual","monthly"): return self.history(station,year,normal)
        if endpoint in ("events","heatwaves","cold-events","extreme-precipitation"):
            kind={"heatwaves":"heatwave","cold-events":"cold","extreme-precipitation":"rain"}.get(endpoint,get("kind","heatwave"))
            return self.events(station,kind,get("start",f"{year}-01-01"),get("end",f"{year}-12-31"),get("threshold",50))
        if endpoint=="event-context": return self.context(station,get("start"),get("end"))
        if endpoint=="on-this-day": return self.on_this_day(month,day)
        if endpoint=="map": return self.map_values(get("mode","stations"),month,day,normal,year)
        if endpoint=="forecast-context":
            self.station(station)
            return self.products.forecast_context(station,month,day,float(get("value")),get("variable","tmax"),normal)
        raise LookupError("Unknown climate endpoint")
