"""Read-only API over precomputed Phase 3 products. No raw archive scans."""
import json
import math
import sqlite3
from datetime import date
from pathlib import Path
from .config import DEFAULT_ROOT
from .phase3_policy import VARIABLES, PERIODS, percentile_rank

ALIASES={"tmean":"tmean_c","tmin":"tmin_c","tmax":"tmax_c","precip":"precip_mm",
         "wind":"wind_mean_ms","pressure":"pressure_msl_hpa"}

class ClimatologyStore:
    def __init__(self,path=None):
        self.path=Path(path or DEFAULT_ROOT/"climatology.sqlite").resolve()
        self.db=sqlite3.connect(self.path.as_uri()+"?mode=ro",uri=True)
        self.db.row_factory=sqlite3.Row
        row=self.db.execute("SELECT value FROM metadata WHERE key='policy'").fetchone()
        self.policy=json.loads(row[0])
        state=self.db.execute("SELECT value FROM metadata WHERE key='state'").fetchone()
        if not state or json.loads(state[0])!="complete":
            self.db.close()
            raise RuntimeError("Derived database has not completed and passed validation")
    def close(self): self.db.close()
    def __enter__(self): return self
    def __exit__(self,*args): self.close()
    @staticmethod
    def day(month,day): return date(2000,month,day).strftime("%m-%d")
    @staticmethod
    def variable(variable):
        variable=ALIASES.get(variable,variable)
        if variable not in VARIABLES: raise ValueError("Unknown variable")
        return variable
    def get_daily_climatology(self,station,month,day,normal="1991-2020"):
        if normal not in PERIODS: raise ValueError("Unsupported normal")
        key=self.day(month,day)
        rows=self.db.execute("SELECT variable,statistics_json FROM daily_climatology WHERE station_id=? AND normal=? AND calendar_day=?",(station,normal,key))
        values={r["variable"]:json.loads(r["statistics_json"]) for r in rows}
        for v in values.values(): v.pop("sorted_samples",None)
        return {"station_id":station,"calendar_day":key,"normal":normal,"variables":values,
                "available":bool(values),"qc_policy":self.policy["version"]}
    def get_temperature_percentile(self,station,month,day,value,variable="tmax",normal="1991-2020"):
        variable=self.variable(variable)
        if variable not in ("tmean_c","tmin_c","tmax_c"): raise ValueError("Temperature variable required")
        if normal not in PERIODS or not math.isfinite(value): raise ValueError("Invalid normal/value")
        key=self.day(month,day)
        row=self.db.execute("SELECT statistics_json FROM daily_climatology WHERE station_id=? AND normal=? AND calendar_day=? AND variable=?",(station,normal,key,variable)).fetchone()
        obj=json.loads(row[0]) if row else {}
        return {"percentile":percentile_rank(obj["sorted_samples"],value) if obj.get("eligible") else None,
                "sample_count":obj.get("sample_count",0),"eligible":obj.get("eligible",False),
                "method":"empirical_midrank","variable":variable,"normal":normal}
    def get_daily_records(self,station,month,day):
        key=self.day(month,day)
        row=self.db.execute("SELECT data_json FROM daily_records WHERE station_id=? AND calendar_day=?",(station,key)).fetchone()
        return {"station_id":station,"calendar_day":key,"records":json.loads(row[0]) if row else {},
                "scope":"All available variable-QC-eligible observations; all tied dates retained."}
    def get_monthly_summary(self,station,year,month):
        date(year,month,1)
        row=self.db.execute("SELECT data_json FROM monthly_summary WHERE station_id=? AND year=? AND month=?",(station,year,month)).fetchone()
        return json.loads(row[0]) if row else None
    def get_annual_summary(self,station,year):
        date(year,1,1)
        row=self.db.execute("SELECT data_json FROM annual_summary WHERE station_id=? AND year=?",(station,year)).fetchone()
        return json.loads(row[0]) if row else None
    def get_monthly_climatology(self,station,month,normal="1991-2020"):
        if normal not in PERIODS or not 0<=month<=12: raise ValueError("Invalid normal/month; 0 means annual")
        row=self.db.execute("SELECT data_json FROM period_climatology WHERE station_id=? AND normal=? AND month=?",(station,normal,month)).fetchone()
        obj=json.loads(row[0]) if row else None
        if obj:
            for v in obj.values():
                if isinstance(v,dict): v.pop("sorted_samples",None)
        return obj
    def get_indices(self,station,year):
        row=self.db.execute("SELECT data_json FROM climate_indices WHERE station_id=? AND year=?",(station,year)).fetchone()
        return json.loads(row[0]) if row else None
    def _events(self,station,kind,start_year,end_year):
        start=f"{start_year or 1:04d}-01-01"; end=f"{end_year or 9999:04d}-12-31"
        if start>end: raise ValueError("Invalid year range")
        return [json.loads(r[0]) for r in self.db.execute(
            "SELECT data_json FROM temperature_events WHERE station_id=? AND kind=? AND end_date>=? AND start_date<=? ORDER BY start_date",(station,kind,start,end))]
    def get_heatwaves(self,station,start_year=None,end_year=None): return self._events(station,"heatwave",start_year,end_year)
    def get_cold_events(self,station,start_year=None,end_year=None): return self._events(station,"cold",start_year,end_year)
    def get_extreme_precip_events(self,station=None,threshold_mm=50,start_date=None,end_date=None,percentile_only=False):
        floor=min(self.policy["extreme_thresholds"])
        if not math.isfinite(threshold_mm) or threshold_mm<floor:
            raise ValueError(f"Catalogue supports thresholds >= {floor} mm; rebuild with a lower configured floor if needed")
        start_date=start_date or "0001-01-01"; end_date=end_date or "9999-12-31"
        date.fromisoformat(start_date); date.fromisoformat(end_date)
        if start_date>end_date: raise ValueError("Invalid date range")
        sql="SELECT station_id,data_json FROM precipitation_events WHERE precip_mm>=? AND date BETWEEN ? AND ?"
        params=[threshold_mm,start_date,end_date]
        if station is not None: sql+=" AND station_id=?"; params.append(station)
        if percentile_only: sql+=" AND percentile_extreme=1"
        sql+=" ORDER BY date,station_id"
        return [{"station_id":r[0],**json.loads(r[1])} for r in self.db.execute(sql,params)]
    def get_percentile_precip_events(self,station,start_date="0001-01-01",end_date="9999-12-31"):
        date.fromisoformat(start_date); date.fromisoformat(end_date)
        if start_date>end_date: raise ValueError("Invalid date range")
        return [json.loads(r[0]) for r in self.db.execute(
            "SELECT data_json FROM precipitation_events WHERE station_id=? AND date BETWEEN ? AND ? AND percentile_extreme=1 ORDER BY date",(station,start_date,end_date))]
    def forecast_context(self,station,month,day,value,variable="tmax",normal="1991-2020"):
        variable=self.variable(variable)
        if variable not in ("tmean_c","tmin_c","tmax_c"): raise ValueError("Temperature variable required")
        if not math.isfinite(value): raise ValueError("Finite forecast value required")
        d=self.get_daily_climatology(station,month,day,normal)
        baseline=d["variables"].get(variable,{})
        rank=self.get_temperature_percentile(station,month,day,value,variable,normal)
        labels={"tmax_c":"highest_tmax","tmin_c":"lowest_tmin","tmean_c":"highest_tmean"}
        record=self.get_daily_records(station,month,day)["records"].get(labels[variable])
        mean=baseline.get("mean")
        return {"station_id":station,"calendar_day":self.day(month,day),"variable":variable,
                "forecast_value":value,"unit":"degC","normal_period":normal,"normal_value":mean,
                "normal_sample_count":baseline.get("sample_count",0),"normal_eligible":baseline.get("eligible",False),
                "anomaly":value-mean if mean is not None else None,"historical_percentile":rank["percentile"],
                "percentile_method":rank["method"],"record":record,"qc_policy":self.policy["version"]}

# Module-level conveniences for callers that do not maintain a persistent connection.
def _call(name,*args,**kwargs):
    path=kwargs.pop("path",None)
    with ClimatologyStore(path) as store: return getattr(store,name)(*args,**kwargs)
def get_daily_climatology(*args,**kwargs): return _call("get_daily_climatology",*args,**kwargs)
def get_temperature_percentile(*args,**kwargs): return _call("get_temperature_percentile",*args,**kwargs)
def get_daily_records(*args,**kwargs): return _call("get_daily_records",*args,**kwargs)
def get_monthly_summary(*args,**kwargs): return _call("get_monthly_summary",*args,**kwargs)
def get_annual_summary(*args,**kwargs): return _call("get_annual_summary",*args,**kwargs)
def get_heatwaves(*args,**kwargs): return _call("get_heatwaves",*args,**kwargs)
def get_cold_events(*args,**kwargs): return _call("get_cold_events",*args,**kwargs)
def get_extreme_precip_events(*args,**kwargs): return _call("get_extreme_precip_events",*args,**kwargs)
def forecast_context(*args,**kwargs): return _call("forecast_context",*args,**kwargs)
