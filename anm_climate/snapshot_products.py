"""Station product writer shared with the original verified Phase 3 build."""
import json
from .phase3_products import *

def dumps(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)

def save_station(db,sid,rows,policy):
    daily,windows,records=daily_products(rows,policy)
    monthly,annual,normals=summaries(rows,policy)
    yearly_indices=indices(rows,policy)
    heat=temperature_events(rows,windows,policy,"heatwave")
    cold=temperature_events(rows,windows,policy,"cold")
    rain=precipitation_events(rows,daily,policy)
    db.executemany("INSERT INTO daily_climatology VALUES (?,?,?,?,?,?,?,?)",
      [(sid,n,k,v,o["sample_count"],o["expected_count"],o["eligible"],dumps(o)) for (n,k,v),o in daily.items()])
    db.executemany("INSERT INTO window_thresholds VALUES (?,?,?,?)",
      [(sid,k,v,dumps({a:b for a,b in o.items() if a!="sorted_samples"})) for (k,v),o in windows.items()])
    db.executemany("INSERT INTO daily_records VALUES (?,?,?)",[(sid,k,dumps(o)) for k,o in records.items()])
    db.executemany("INSERT INTO monthly_summary VALUES (?,?,?,?)",[(sid,y,m,dumps(o)) for (y,m),o in monthly.items()])
    db.executemany("INSERT INTO annual_summary VALUES (?,?,?)",[(sid,y,dumps(o)) for y,o in annual.items()])
    db.executemany("INSERT INTO period_climatology VALUES (?,?,?,?)",[(sid,n,m,dumps(o)) for (n,m),o in normals.items()])
    db.executemany("INSERT INTO climate_indices VALUES (?,?,?)",[(sid,y,dumps(o)) for y,o in yearly_indices.items()])
    db.executemany("INSERT INTO temperature_events VALUES (?,?,?,?,?,?)",
      [(sid,o["kind"],o["start_date"],o["end_date"],o["duration"],dumps({"station_id":sid,**o})) for o in heat+cold])
    db.executemany("INSERT INTO precipitation_events VALUES (?,?,?,?,?)",
      [(sid,o["date"],o["precip_mm"],o["percentile_extreme"],dumps(o)) for o in rain])

SCHEMA="""
CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS station_build(station_id TEXT PRIMARY KEY,seconds REAL NOT NULL);
CREATE TABLE IF NOT EXISTS qc_exclusions(station_id TEXT,date TEXT,variable TEXT,reason TEXT,value REAL,
 PRIMARY KEY(station_id,date,variable));
CREATE TABLE IF NOT EXISTS qc_counts(station_id TEXT,variable TEXT,eligible_count INTEGER,missing_count INTEGER,excluded_count INTEGER,
 PRIMARY KEY(station_id,variable));
CREATE TABLE IF NOT EXISTS pressure_quarantine(station_id TEXT,year INTEGER,PRIMARY KEY(station_id,year));
CREATE TABLE IF NOT EXISTS daily_climatology(station_id TEXT,normal TEXT,calendar_day TEXT,variable TEXT,
 sample_count INTEGER,expected_count INTEGER,eligible INTEGER,statistics_json TEXT,
 PRIMARY KEY(station_id,normal,calendar_day,variable));
CREATE TABLE IF NOT EXISTS window_thresholds(station_id TEXT,calendar_day TEXT,variable TEXT,data_json TEXT,
 PRIMARY KEY(station_id,calendar_day,variable));
CREATE TABLE IF NOT EXISTS daily_records(station_id TEXT,calendar_day TEXT,data_json TEXT,PRIMARY KEY(station_id,calendar_day));
CREATE TABLE IF NOT EXISTS monthly_summary(station_id TEXT,year INTEGER,month INTEGER,data_json TEXT,PRIMARY KEY(station_id,year,month));
CREATE TABLE IF NOT EXISTS annual_summary(station_id TEXT,year INTEGER,data_json TEXT,PRIMARY KEY(station_id,year));
CREATE TABLE IF NOT EXISTS period_climatology(station_id TEXT,normal TEXT,month INTEGER,data_json TEXT,PRIMARY KEY(station_id,normal,month));
CREATE TABLE IF NOT EXISTS climate_indices(station_id TEXT,year INTEGER,data_json TEXT,PRIMARY KEY(station_id,year));
CREATE TABLE IF NOT EXISTS temperature_events(station_id TEXT,kind TEXT,start_date TEXT,end_date TEXT,duration INTEGER,data_json TEXT,
 PRIMARY KEY(station_id,kind,start_date));
CREATE TABLE IF NOT EXISTS precipitation_events(station_id TEXT,date TEXT,precip_mm REAL,percentile_extreme INTEGER,data_json TEXT,
 PRIMARY KEY(station_id,date));
CREATE INDEX IF NOT EXISTS precip_amount_date ON precipitation_events(precip_mm,date);
CREATE INDEX IF NOT EXISTS precip_date ON precipitation_events(date);
"""
