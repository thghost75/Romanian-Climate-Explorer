"""Strict-threshold day counts, precomputed once per deployment."""
import calendar
import json
import math
from collections import defaultdict
from datetime import date

COUNTS = {
 'tropical_nights': ('tmin_c', '>', 20),
 'summer_days': ('tmax_c', '>', 25),
 'tropical_days': ('tmax_c', '>', 30),
 'scorching_days': ('tmax_c', '>', 35),
 'frosty_days': ('tmax_c', '<', 0),
 'freezing_days': ('tmax_c', '<', -10),
 'frosty_nights': ('tmin_c', '<', 0),
 'freezing_nights': ('tmin_c', '<', -10),
 'polar_nights': ('tmin_c', '<', -20),
 'rain_01_days': ('precip_mm', '>', 0.1),
 'rain_1_days': ('precip_mm', '>', 1),
 'rain_10_days': ('precip_mm', '>', 10),
}
KINDS = {f'count_{k}_{unit}': (k, unit) for k in COUNTS for unit in ('month','year')}
POLICY = ('Counts use strict > or < thresholds; equality does not count. Only complete calendar periods '
          'with eligible observations for the relevant variable every day qualify. Trace rainfall counts as 0 mm. '
          'Source flags and pending reviews remain visible. Monthly counts are raw day counts, not adjusted for month length.')


def station_periods(source, products, sid):
    excluded = {(r[0],r[1]) for r in products.execute(
        'SELECT date,variable FROM qc_exclusions WHERE station_id=?', (sid,))}
    buckets = {}
    for when, tn, tx, rain, trace, flags in source.execute(
            'SELECT date,tmin_c,tmax_c,precip_mm,precip_trace,quality_flags FROM daily_observations WHERE station_id=? ORDER BY date', (sid,)):
        monthly = when[:7]
        if monthly not in buckets:
            buckets[monthly] = {'coverage':defaultdict(int),'counts':defaultdict(int),'flagged_dates':[]}
        b = buckets[monthly]
        if flags and flags != '[]': b['flagged_dates'].append(when)
        for variable,value in [('tmin_c',tn),('tmax_c',tx),('precip_mm',0 if trace else rain)]:
            if value is None or not math.isfinite(value) or (when,variable) in excluded:
                continue
            if variable=='precip_mm' and value<0: continue
            b['coverage'][variable] += 1
            for key,(v,op,threshold) in COUNTS.items():
                if v==variable and (value>threshold if op=='>' else value<threshold):
                    b['counts'][key] += 1
    annual = {}
    for period,b in list(buckets.items()):
        y = period[:4]
        if y not in annual: annual[y] = {'coverage':defaultdict(int),'counts':defaultdict(int),'flagged_dates':[]}
        a = annual[y]
        for field in ('coverage','counts'):
            for k,v in b[field].items(): a[field][k] += v
        a['flagged_dates'].extend(b['flagged_dates'])
    for period,b in {**buckets,**annual}.items():
        y = int(period[:4]); m = int(period[5:7]) if len(period)>4 else 0
        expected = calendar.monthrange(y,m)[1] if m else 365+calendar.isleap(y)
        yield y,m,{'period':period,'year':y,'month':m or None,'expected_days':expected,
                   'coverage':dict(b['coverage']),'counts':{k:b['counts'][k] for k in COUNTS},
                   'flagged_dates':b['flagged_dates']}


def build_count_index(source, products):
    products.execute('CREATE TABLE threshold_periods (station_id TEXT,year INTEGER,month INTEGER,data_json TEXT,PRIMARY KEY(station_id,year,month))')
    for sid, in source.execute('SELECT station_id FROM stations ORDER BY station_id'):
        products.executemany('INSERT INTO threshold_periods VALUES (?,?,?,?)',
                            ((sid,y,m,json.dumps(p,separators=(",",":"))) for y,m,p in station_periods(source,products,sid)))
    products.execute('CREATE INDEX threshold_period_selection ON threshold_periods(month,year)')
    products.commit()


def candidates(api, stations, monthly, month=None, year=None):
    db=api.products.db
    if db.execute("SELECT 1 FROM sqlite_master WHERE name='threshold_periods'").fetchone():
        sql='SELECT station_id,data_json FROM threshold_periods WHERE '+('month>0' if monthly else 'month=0')
        args=[]
        for key,value in [('month',month),('year',year)]:
            if value is not None: sql+=' AND '+key+'=?'; args.append(value)
        if len(stations)==1: sql+=' AND station_id=?'; args.append(next(iter(stations)))
        return [(sid,json.loads(raw)) for sid,raw in db.execute(sql,args) if sid in stations]
    return [(sid,p) for sid in stations for y,m,p in station_periods(api.source,db,sid)
            if bool(m)==monthly and (month is None or m==month) and (year is None or y==year)]


def rank(api, entries, stations, kind, mode):
    key,unit=KINDS[kind]
    variable=COUNTS[key][0]
    eligible=[(sid,p) for sid,p in entries if p['coverage'].get(variable,0)==p['expected_days']]
    eligible.sort(key=lambda x:(-x[1]['counts'][key],x[0] if mode=='station' else x[1]['period'],x[1]['period'] if mode=='station' else x[0]))
    groups=[]; leaders={}
    for sid,p in eligible:
        value=p['counts'][key]
        if mode=='station' and sid in leaders:
            if leaders[sid]['value']!=value: continue
            group=leaders[sid]
        elif mode=='distinct' and groups and groups[-1]['value']==value:
            group=groups[-1]
        else:
            if len(groups)==10:
                if mode=='station': continue
                break
            group={'rank':len(groups)+1,'value':value,'station_id':sid,'station_name':stations[sid]['station_name'],
                   'record_type':kind,'day_count':True,'periods':[],'needs_verification':False}
            groups.append(group); leaders[sid]=group
        start=p['period']+'-01' if unit=='month' else p['period']+'-01-01'
        end=p['period']+f"-{p['expected_days']:02}" if unit=='month' else p['period']+'-12-31'
        notes=api.reviews(sid,start,end)
        detail={k:v for k,v in p.items() if k not in ('counts','coverage')}
        detail.update(value=value,sample_count=p['coverage'][variable],verification_notes=notes)
        group['periods'].append(detail)
        group['needs_verification'] |= bool(p['flagged_dates'] or notes)
    return groups,len(eligible),len(entries)-len(eligible)


def station_rankings(api, station, kind, scope, month, year):
    info=api.station(station); key,unit=KINDS[kind]; monthly=unit=='month'
    if scope not in ('month','month-year','year','all'): raise ValueError('Select a monthly or yearly record scope')
    selected_year=api.year(year) if year is not None and scope in ('year','month-year') else None
    if selected_year is not None and not info['first_year']<=selected_year<=info['last_year']:
        raise ValueError('Year is outside this station archive')
    selected_month=int(month) if monthly and scope in ('month','month-year') else None
    if selected_month is not None and not 1<=selected_month<=12: raise ValueError('Invalid month')
    entries=candidates(api,{station:info},monthly,selected_month,selected_year)
    rows,n,excluded=rank(api,entries,{station:info},kind,'distinct')
    label=(date(2000,selected_month,1).strftime('%B') if selected_month else 'All months' if monthly else 'Calendar years')
    label+=f' · {selected_year}' if selected_year else ' · all available years'
    return dict(station_id=station,station_name=info['station_name'],kind=kind,scope=scope,
                period_unit=unit,day_count=True,period_label=label,ranking=rows,sample_count=n,
                excluded_period_count=excluded,qc_policy=POLICY)


def national(api, scope, month, year, mode, stations):
    monthly=scope in ('month','month-year')
    entries=candidates(api,stations,monthly,int(month) if monthly else None,year if scope in ('year','month-year') else None)
    return [r for key in COUNTS for r in rank(api,entries,stations,f"count_{key}_{'month' if monthly else 'year'}",mode)[0]]
