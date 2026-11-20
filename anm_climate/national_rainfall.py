"""Rank complete station precipitation totals, never partial sums."""
import calendar
import json
import math


def totals(db, monthly, month=None, year=None):
    table = 'monthly_summary' if monthly else 'annual_summary'
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name=?", (table,)).fetchone():
        return
    query = f"SELECT station_id,year,{'month' if monthly else '0'},data_json FROM {table} WHERE 1=1"
    args = []
    for column, value in [('month', month), ('year', year)]:
        if value is not None:
            query += f' AND {column}=?'
            args.append(value)
    for sid, y, m, raw in db.execute(query, args):
        rain = json.loads(raw).get('variables', {}).get('precip_mm', {})
        days = calendar.monthrange(y, m)[1] if m else 365 + calendar.isleap(y)
        value = rain.get('total')
        if (rain.get('eligible') and rain.get('sample_count') == days and
                (m or rain.get('eligible_months') == 12) and value is not None
                and math.isfinite(value) and value >= 0):
            yield sid, y, m, round(value, 1)


def build_rain_index(db):
    db.execute('CREATE TABLE rain_periods (station_id TEXT,year INTEGER,month INTEGER,total REAL)')
    for monthly in (True, False):
        db.executemany('INSERT INTO rain_periods VALUES (?,?,?,?)', totals(db, monthly))
    db.execute('CREATE INDEX rain_period_selection ON rain_periods(month,year,total,station_id)')
    db.commit()


def highlights(api, scope, month, year, ranking, stations, *, all_months=False):
    monthly = all_months or scope in ('month', 'month-year')
    m = None if all_months else month if monthly else 0
    y = year if scope in ('year', 'month-year') else None
    db = api.products.db
    if db.execute("SELECT 1 FROM sqlite_master WHERE name='rain_periods'").fetchone():
        sql = 'SELECT station_id,year,month,total FROM rain_periods WHERE ' + ('month BETWEEN 1 AND 12' if all_months else 'month=?')
        args = [] if all_months else [m]
        if y is not None:
            sql += ' AND year=?'
            args.append(y)
        rows = db.execute(sql, args)
    else:
        rows = totals(db, monthly, m if monthly else None, y)
    entries = [(sid, f'{yr:04}-{mo:02}' if mo else str(yr), value)
               for sid,yr,mo,value in rows if sid in stations]
    result = []
    details = {}
    for prefix, direction in [('wettest', -1), ('driest', 1)]:
        if all_months and prefix == 'driest':
            continue
        ordered = sorted(entries, key=lambda e: (direction*e[2], e[0], e[1]) if ranking=='station'
                         else (direction*e[2], e[1], e[0]))
        winners = []
        leaders = {}
        for sid, period, value in ordered:
            if ranking=='station' and sid in leaders:
                if leaders[sid]['value']==value:
                    leaders[sid]['periods'].append(period)
                continue
            if len(winners)==10:
                if ranking=='value' or value!=winners[-1]['value']:
                    break
                continue
            item = dict(station_id=sid, station_name=stations[sid]['station_name'], value=value,
                        record_type=prefix+('_month' if monthly else '_year'), rank=len(winners)+1,
                        periods=[period])
            winners.append(item)
            leaders[sid] = item
        for item in winners:
            sid = item['station_id']
            for i, p in enumerate(item['periods']):
                if (sid,p) not in details:
                    first = p+'-01' if monthly else p+'-01-01'
                    last = p+f'-{calendar.monthrange(int(p[:4]),int(p[5:7]))[1]:02}' if monthly else p+'-12-31'
                    flags = [r[0] for r in api.source.execute(
                        "SELECT date FROM daily_observations WHERE station_id=? AND date BETWEEN ? AND ? AND quality_flags!='[]' ORDER BY date",
                        (sid,first,last))]
                    details[sid,p] = dict(period=p,flagged_dates=flags,verification_notes=api.reviews(sid,first,last))
                item['periods'][i] = details[sid,p]
            item['needs_verification'] = any(p['flagged_dates'] or p['verification_notes'] for p in item['periods'])
        result.extend(winners)
    return result
