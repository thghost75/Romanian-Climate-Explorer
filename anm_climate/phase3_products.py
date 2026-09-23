"""Pure climatological aggregation and event algorithms; input is variable-QC eligible data."""
import calendar
import math
from collections import defaultdict
from datetime import date,timedelta
from .phase3_policy import *

RECORDS = (("highest_tmax","tmax_c","max"),("lowest_tmin","tmin_c","min"),
 ("lowest_tmax","tmax_c","min"),("highest_tmin","tmin_c","max"),
 ("highest_tmean","tmean_c","max"),("lowest_tmean","tmean_c","min"),
 ("highest_precip","precip_mm","max"),("highest_mean_wind","wind_mean_ms","max"),
 ("highest_pressure","pressure_msl_hpa","max"),("lowest_pressure","pressure_msl_hpa","min"))

def stats(values,expected,policy,include_samples=False):
    values=sorted(values); n=len(values)
    enough=n>=required_count(expected,policy.normal_fraction) and expected>0
    result={"sample_count":n,"expected_count":expected,"required_count":required_count(expected,policy.normal_fraction),
            "eligible":enough,"complete_percent":100*n/expected if expected else None}
    result.update({"mean":math.fsum(values)/n if enough else None,
                   "minimum":values[0] if enough else None,"maximum":values[-1] if enough else None})
    result.update({f"p{p}":quantile(values,p) if enough else None for p in PERCENTILES})
    result["median"]=result["p50"]
    if include_samples: result["sorted_samples"]=values
    # Every statistic uses precisely this sample_count, including zero/trace precipitation.
    return result

def daily_products(rows,policy):
    all_days=defaultdict(list)
    for r in rows: all_days[r["date"][5:]].append(r)
    daily={}; windows={}; records={}
    for key in CALENDAR:
        data=all_days[key]
        record={}
        for label,v,op in RECORDS:
            valid=[r for r in data if r[v] is not None]
            value=(max if op=="max" else min)(r[v] for r in valid) if valid else None
            record[label]={"value":value,"dates":[r["date"] for r in valid if r[v]==value],
                           "years":[int(r["date"][:4]) for r in valid if r[v]==value],"sample_count":len(valid)}
        records[key]=record
    for normal in PERIODS:
        start,end=map(int,normal.split("-"))
        expected=calendar_expected(normal)
        by_day={k:[r for r in all_days[k] if start<=int(r["date"][:4])<=end] for k in CALENDAR}
        for key in CALENDAR:
            for v in VARIABLES:
                valid=[r for r in by_day[key] if r[v] is not None]
                obj=stats([r[v] for r in valid],expected[key],policy,v in (*TEMPERATURES,"precip_mm"))
                if v=="precip_mm":
                    n=len(valid)
                    obj.update({"measurable_rain_days":sum(r[v]>0 for r in valid),
                      "trace_days":sum(bool(r["precip_trace"]) for r in valid),
                      "dry_days":sum(r[v]==0 and not r["precip_trace"] for r in valid),
                      "probability_ge":{str(t):sum(r[v]>=t for r in valid)/n if n and obj["eligible"] else None for t in policy.rain_probabilities},
                      "threshold_exceedance_counts":{str(t):sum(r[v]>=t for r in valid) for t in policy.rain_probabilities},
                      "maximum_dates":[r["date"] for r in valid if obj["eligible"] and r[v]==obj["maximum"]],
                      "maximum_years":[int(r["date"][:4]) for r in valid if obj["eligible"] and r[v]==obj["maximum"]]})
                daily[(normal,key,v)]=obj
        if normal==policy.normal:
            for key in CALENDAR:
                keys=window_keys(key,policy.window_radius)
                for v in dict.fromkeys(("tmax_c",policy.cold_variable)):
                    valid=[r for k in keys for r in by_day[k] if r[v] is not None]
                    obj=stats([r[v] for r in valid],sum(expected[k] for k in keys),policy,True)
                    obj["year_count"]=len({r["date"][:4] for r in valid})
                    # Window=0 on leap day has only leap years available; otherwise all 30.
                    expected_years=expected[key] if policy.window_radius==0 else end-start+1
                    obj["expected_years"]=expected_years
                    obj["eligible"]=obj["eligible"] and obj["year_count"]>=required_count(expected_years,policy.normal_fraction)
                    obj["threshold"]=quantile(obj["sorted_samples"],policy.heat_percentile if v=="tmax_c" else policy.cold_percentile) if obj["eligible"] else None
                    windows[(key,v)]=obj
    return daily,windows,records

def missing_run(values):
    longest=current=0
    for v in values:
        current=current+1 if v is None else 0
        longest=max(longest,current)
    return longest

def month_summary(year,month,rows,policy):
    ndays=calendar.monthrange(year,month)[1]
    by_day={int(r["date"][-2:]):r for r in rows}
    result={"year":year,"month":month,"expected_days":ndays,"source_days":len(rows),"variables":{}}
    for v in VARIABLES:
        seq=[by_day.get(d,{}).get(v) for d in range(1,ndays+1)]
        valid=[x for x in seq if x is not None]; n=len(valid)
        fraction=policy.precip_monthly_fraction if v=="precip_mm" else policy.monthly_fraction
        complete=n>=required_count(ndays,fraction) and missing_run(seq)<=policy.monthly_max_missing_run
        result["variables"][v]={"sample_count":n,"missing_days":ndays-n,"max_missing_run":missing_run(seq),
             "eligible":complete,"mean":math.fsum(valid)/n if complete and n else None,
             "observed_mean":math.fsum(valid)/n if n else None,
             "minimum":min(valid) if valid else None,"maximum":max(valid) if valid else None}
        if v=="precip_mm":
            validrows=[r for r in rows if r[v] is not None]
            result["variables"][v].update({"total":math.fsum(valid) if complete else None,
              "observed_total":math.fsum(valid) if n else None,
              "rain_days":sum(r[v]>=policy.wet_day_mm for r in validrows),
              "measurable_rain_days":sum(r[v]>0 for r in validrows),
              "trace_days":sum(bool(r["precip_trace"]) for r in validrows),
              "dry_days":sum(r[v]==0 and not r["precip_trace"] for r in validrows),
              "wettest_dates":[r["date"] for r in validrows if r[v]==max(valid)] if n else []})
    return result

def annual_summary(year,months,policy):
    result={"year":year,"expected_days":365+int(calendar.isleap(year)),"variables":{}}
    for v in VARIABLES:
        entries=[m["variables"][v] for m in months]
        eligible=all(e["eligible"] for e in entries) and len(entries)==12
        n=sum(e["sample_count"] for e in entries)
        # A full year uses day-weighted eligible monthly means; precipitation sums complete months.
        obj={"sample_count":n,"eligible_months":sum(e["eligible"] for e in entries),"eligible":eligible,
             "minimum":min((e["minimum"] for e in entries if e["minimum"] is not None),default=None),
             "maximum":max((e["maximum"] for e in entries if e["maximum"] is not None),default=None)}
        if v=="precip_mm":
            obj["total"]=math.fsum(e["total"] for e in entries) if eligible else None
            obj["observed_total"]=math.fsum(e["observed_total"] for e in entries if e["observed_total"] is not None) if n else None
        else:
            obj["mean"]=math.fsum(e["mean"]*calendar.monthrange(year,i+1)[1] for i,e in enumerate(entries))/result["expected_days"] if eligible else None
        result["variables"][v]=obj
    return result

def summaries(rows,policy):
    by_month=defaultdict(list)
    for r in rows: by_month[(int(r["date"][:4]),int(r["date"][5:7]))].append(r)
    years=range(int(rows[0]["date"][:4]),int(rows[-1]["date"][:4])+1) if rows else []
    monthly={(y,m):month_summary(y,m,by_month[(y,m)],policy) for y in years for m in range(1,13)}
    annual={y:annual_summary(y,[monthly[(y,m)] for m in range(1,13)],policy) for y in years}
    normals={}
    for normal in PERIODS:
        start,end=map(int,normal.split("-"))
        for month in range(13):
            normal_obj={}
            for v in VARIABLES:
                metric="total" if v=="precip_mm" else "mean"
                series=annual if month==0 else {y:monthly.get((y,month)) for y in range(start,end+1)}
                vals=[]
                for y in range(start,end+1):
                    obj=series.get(y)
                    if obj and obj["variables"][v]["eligible"]:
                        x=obj["variables"][v].get(metric)
                        if x is not None: vals.append(x)
                normal_obj[v]=stats(vals,end-start+1,policy,True)
                normal_obj[v]["metric"]=metric
                # Interannual monthly/annual extremes and rain-day normal statistics.
                extra_fields=("minimum","maximum","rain_days","measurable_rain_days","trace_days","dry_days")
                extra={}
                for field in extra_fields:
                    samples=[]
                    for y in range(start,end+1):
                        item=series.get(y)
                        if item and item["variables"][v]["eligible"]:
                            x=item["variables"][v].get(field)
                            if x is not None: samples.append(x)
                    if samples:
                        extra[field]=stats(samples,end-start+1,policy)
                normal_obj[v]["additional_metrics"]=extra
            normals[(normal,month)]=normal_obj
    for key,summary in list(monthly.items())+[(y,a) for y,a in annual.items()]:
        month=key[1] if isinstance(key,tuple) else 0
        for v,obj in summary["variables"].items():
            norm=normals[(policy.normal,month)][v]; metric="total" if v=="precip_mm" else "mean"
            value=obj.get(metric)
            obj["normal"]=norm["mean"]; obj["normal_sample_count"]=norm["sample_count"]
            obj["anomaly"]=value-norm["mean"] if value is not None and norm["mean"] is not None else None
            obj["historical_percentile"]=percentile_rank(norm["sorted_samples"],value) if value is not None and norm["eligible"] else None
    return monthly,annual,normals

def indices(rows,policy):
    by_year=defaultdict(dict)
    for r in rows: by_year[int(r["date"][:4])][r["date"]]=r
    result={}
    tests={"frost_days":("tmin_c",lambda x:x<policy.frost_c),"ice_days":("tmax_c",lambda x:x<policy.ice_c),
      "summer_days":("tmax_c",lambda x:x>=policy.summer_c),"hot_days":("tmax_c",lambda x:x>=policy.hot_c),
      "very_hot_days":("tmax_c",lambda x:x>=policy.very_hot_c),"tropical_nights":("tmin_c",lambda x:x>=policy.tropical_c),
      "heavy_precip_days":("precip_mm",lambda x:x>=policy.heavy_mm),
      "very_heavy_precip_days":("precip_mm",lambda x:x>=policy.very_heavy_mm)}
    for y,items in by_year.items():
        expected=365+int(calendar.isleap(y)); out={}
        for name,(v,fn) in tests.items():
            vals=[r[v] for r in items.values() if r[v] is not None]
            out[name]={"count":sum(fn(x) for x in vals),"sample_count":len(vals),"expected_days":expected,"complete":len(vals)==expected}
        dry=wet=maxdry=maxwet=0
        for i in range(expected):
            key=(date(y,1,1)+timedelta(days=i)).isoformat(); rain=items.get(key,{}).get("precip_mm")
            dry=dry+1 if rain is not None and rain<policy.wet_day_mm else 0
            wet=wet+1 if rain is not None and rain>=policy.wet_day_mm else 0
            maxdry=max(maxdry,dry); maxwet=max(maxwet,wet)
        out["consecutive_dry_days"]=maxdry; out["consecutive_wet_days"]=maxwet
        out["spell_scope"]="Within calendar year; missing/ineligible dates break spells; incomplete years give observed lower bounds."
        result[y]=out
    return result

def temperature_events(rows,windows,policy,kind):
    variable="tmax_c" if kind=="heatwave" else policy.cold_variable
    events=[]; run=[]
    def finish():
        if len(run)>=policy.min_duration:
            anomalies=[r[1]-r[2]["mean"] for r in run]
            ranks=[percentile_rank(r[2]["sorted_samples"],r[1]) for r in run]
            values=[r[1] for r in run]
            events.append({"kind":kind,"variable":variable,"normal":policy.normal,
              "start_date":run[0][0],"end_date":run[-1][0],"duration":len(run),
              "maximum_temperature":max(values),"minimum_temperature":min(values),
              "maximum_tmax":max(values) if kind=="heatwave" else None,
              "mean_temperature_anomaly":math.fsum(anomalies)/len(run),
              "mean_tmax_anomaly":math.fsum(anomalies)/len(run) if kind=="heatwave" else None,
              "cumulative_temperature_anomaly":math.fsum(anomalies),
              "peak_percentile":max(ranks) if kind=="heatwave" else min(ranks),
              "minimum_threshold_sample_count":min(r[2]["sample_count"] for r in run),
              "window_radius":policy.window_radius})
        run.clear()
    previous=None
    for r in rows:
        current=date.fromisoformat(r["date"])
        if previous is not None and (current-previous).days!=1: finish()
        previous=current; v=r[variable]; w=windows[(r["date"][5:],variable)]
        hit=v is not None and w["eligible"] and (v>=w["threshold"] if kind=="heatwave" else v<=w["threshold"])
        if hit: run.append((r["date"],v,w))
        else: finish()
    finish()
    return events

def precipitation_events(rows,daily,policy):
    events=[]
    for r in rows:
        rain=r["precip_mm"]
        if rain is None: continue
        d=daily[(policy.normal,r["date"][5:],"precip_mm")]
        threshold=quantile(d["sorted_samples"],policy.precip_extreme_percentile) if d["eligible"] else None
        extreme=threshold is not None and rain>=policy.wet_day_mm and rain>=threshold
        exceeded=[t for t in policy.extreme_thresholds if rain>=t]
        if exceeded or extreme:
            events.append({"date":r["date"],"precip_mm":rain,"thresholds_ge":exceeded,
              "percentile":percentile_rank(d["sorted_samples"],rain) if d["eligible"] else None,
              "percentile_extreme":extreme,"percentile_threshold_mm":threshold,
              "normal":policy.normal,"normal_sample_count":d["sample_count"],
              "normal_eligible":d["eligible"]})
    return events
