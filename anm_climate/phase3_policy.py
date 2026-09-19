"""Explicit variable-level eligibility; never writes the Phase 2 source."""
import math
from dataclasses import dataclass, asdict
from bisect import bisect_left, bisect_right
from datetime import date, timedelta

VARIABLES = ("tmean_c", "tmin_c", "tmax_c", "precip_mm", "wind_mean_ms", "pressure_msl_hpa")
TEMPERATURES = VARIABLES[:3]
PERIODS = ("1961-1990", "1971-2000", "1981-2010", "1991-2020")
PERCENTILES = (1, 5, 10, 25, 50, 75, 90, 95, 99)
CALENDAR = [(date(2000,1,1)+timedelta(days=i)).strftime("%m-%d") for i in range(366)]
CAL_INDEX = {key:i for i,key in enumerate(CALENDAR)}
BOUNDS = {**{v:(-60,60) for v in TEMPERATURES}, "precip_mm":(0,1000),
          "wind_mean_ms":(0,100), "pressure_msl_hpa":(850,1100)}

@dataclass(frozen=True)
class Policy:
    version: str = "phase3-v1"
    normal: str = "1991-2020"
    normal_fraction: float = 0.8
    monthly_fraction: float = 0.9
    monthly_max_missing_run: int = 3
    precip_monthly_fraction: float = 1.0
    window_radius: int = 7
    heat_percentile: float = 90
    cold_percentile: float = 10
    min_duration: int = 3
    cold_variable: str = "tmin_c"
    wet_day_mm: float = 1.0
    frost_c: float = 0
    ice_c: float = 0
    summer_c: float = 25
    hot_c: float = 30
    very_hot_c: float = 35
    tropical_c: float = 20
    heavy_mm: float = 10
    very_heavy_mm: float = 20
    rain_probabilities: tuple = (0.1,1,5,10,20,30,50)
    extreme_thresholds: tuple = (20,30,50,75,100)
    precip_extreme_percentile: float = 99

    def validate(self):
        if self.normal not in PERIODS: raise ValueError("Unsupported normal")
        if not 0 < self.normal_fraction <= 1 or not 0 < self.monthly_fraction <= 1:
            raise ValueError("Completeness fractions must be in (0,1]")
        if not 0 < self.precip_monthly_fraction <= 1: raise ValueError("Invalid rainfall completeness")
        if not 0 <= self.window_radius <= 30 or self.min_duration < 1: raise ValueError("Invalid event window/duration")
        if not 0 < self.cold_percentile < 50 < self.heat_percentile < 100: raise ValueError("Invalid temperature percentiles")
        if self.cold_variable not in ("tmin_c","tmean_c"): raise ValueError("Cold variable must be Tmin or Tmean")
        if self.wet_day_mm <= 0 or any(t <= 0 for t in (*self.rain_probabilities,*self.extreme_thresholds)):
            raise ValueError("Rain thresholds must be positive")
        if not 0 < self.precip_extreme_percentile < 100: raise ValueError("Invalid rainfall percentile")
        return self

def quantile(values, percentile):
    """Hyndman-Fan type 7, sorted values, linear interpolation at (n-1)*p."""
    if not values: return None
    position=(len(values)-1)*percentile/100
    lo=int(math.floor(position)); hi=int(math.ceil(position))
    return values[lo]+(values[hi]-values[lo])*(position-lo)

def percentile_rank(values,value):
    """Empirical midrank in percent; ties receive half their mass."""
    if not values: return None
    return 100*(bisect_left(values,value)+bisect_right(values,value))/(2*len(values))

def required_count(expected, fraction):
    return math.ceil(expected*fraction-1e-12)

def pressure_quarantine(rows):
    """Station/year pressure suspect if >50% of >=30 reported values fail broad bounds."""
    counts={}
    for r in rows:
        x=r["pressure_msl_hpa"]
        if x is not None:
            y=int(r["date"][:4]); n,bad=counts.get(y,(0,0))
            counts[y]=(n+1,bad+int(not 850<=x<=1100))
    return {y for y,(n,bad) in counts.items() if n>=30 and bad/n>0.5}

def eligibility(row, variable, suspect_pressure_years=()):
    x=row[variable]
    if x is None: return False,"missing"
    if not math.isfinite(x): return False,"nonfinite"
    if variable=="precip_mm" and (row.get("precip_raw")==-999 or x==-999): return False,"sentinel_-999"
    if variable=="wind_mean_ms" and x==-999: return False,"sentinel_-999"
    lo,hi=BOUNDS[variable]
    if not lo<=x<=hi: return False,"outside_physical_screen"
    if variable=="pressure_msl_hpa" and int(row["date"][:4]) in suspect_pressure_years:
        return False,"suspect_pressure_station_year"
    tn,tx,ta=(row[v] for v in ("tmin_c","tmax_c","tmean_c"))
    if variable in ("tmin_c","tmax_c") and tn is not None and tx is not None and tn>tx:
        return False,"inconsistent_temperature_extrema"
    if variable=="tmean_c" and tn is not None and tx is not None and not tn<=ta<=tx:
        return False,"mean_outside_daily_extrema"
    return True,None

def cleaned_rows(rows, suspect):
    result=[]
    for source in rows:
        r={"date":source["date"],"precip_trace":source.get("precip_trace")}
        for v in VARIABLES:
            r[v]=source[v] if eligibility(source,v,suspect)[0] else None
        result.append(r)
    return result

def calendar_expected(normal):
    first,last=map(int,normal.split("-"))
    import calendar
    return {k:sum(k!="02-29" or calendar.isleap(y) for y in range(first,last+1)) for k in CALENDAR}

def window_keys(key,radius):
    center=CAL_INDEX[key]
    return [CALENDAR[(center+i)%366] for i in range(-radius,radius+1)]
