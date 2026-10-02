"""Compact national extremes, retaining every tied station/date and variable QC."""
import json
import math
from bisect import insort
from datetime import date

from .phase3_products import RECORDS
from .station_metadata import resolve_station_elevation


def period(scope, month, day, year):
    date(2000, month, day)
    if scope == 'day': return f'{month:02d}-{day:02d}', f'Calendar day {month:02d}-{day:02d} · all available years'
    if scope == 'month': return f'{month:02d}', f'{date(2000,month,1):%B} · all available years'
    if scope == 'year': return str(year), f'Year {year}'
    if scope == 'month-year': return f'{year}-{month:02d}', f'{date(2000,month,1):%B} {year}'
    if scope == 'all': return 'all', 'All available years'
    raise ValueError('Record scope must be day, month, year, month-year or all')


def empty():
    return {'stations': set(), 'records': {label: {'value': None, 'sample_count': 0, 'holders': []}
                                         for label, _, _ in RECORDS}}


def aggregate(source, products, scope=None, key=None, station_ids=None, include_days=True, include_values=False):
    """Build all periods once, or a single period for an unprepared local archive."""
    buckets = {}
    variables = list(dict.fromkeys(variable for _, variable, _ in RECORDS))
    positions = [(label, variables.index(variable)+1, variable, op == 'min') for label, variable, op in RECORDS]
    stations = station_ids if station_ids is not None else [r[0] for r in source.execute('SELECT station_id FROM stations ORDER BY station_id')]
    for station in stations:
        exclusions = {(r[0], r[1]) for r in products.execute(
            'SELECT date,variable FROM qc_exclusions WHERE station_id=?', (station,))}
        sql = 'SELECT date,' + ','.join(variables) + ' FROM daily_observations WHERE station_id=?'
        args = [station]
        if scope in ('year', 'month-year'):
            sql += ' AND date BETWEEN ? AND ?'
            args.extend((key + ('-01-01' if scope == 'year' else '-01'), key + ('-12-31' if scope == 'year' else '-31')))
        elif scope in ('day', 'month'):
            sql += ' AND substr(date,6,?)=?'
            args.extend((len(key), key))
        for row in source.execute(sql + ' ORDER BY date', args):
            when = row[0]
            keys = [(scope, key)] if scope else ([('day', when[5:])] if include_days else []) + [('month-year', when[:7])]
            targets = []
            for bucket_key in keys:
                if bucket_key not in buckets: buckets[bucket_key] = empty()
                targets.append(buckets[bucket_key])
            for label, index, variable, lowest in positions:
                value = row[index]
                if value is None or not math.isfinite(value) or (when, variable) in exclusions:
                    continue
                for target in targets:
                    target['stations'].add(station)
                    record = target['records'][label]
                    record['sample_count'] += 1
                    if include_values:
                        values = record.setdefault('top_values', [])
                        candidate = (value if lowest else -value, when)
                        if len(values) < 10 or candidate < values[-1]:
                            insort(values, candidate)
                            del values[10:]
                    old = record['value']
                    if old is None or (value < old if lowest else value > old):
                        record['value'] = value
                        record['holders'] = []
                    if value == record['value']:
                        record['holders'].append([station, when])
    if scope:
        buckets.setdefault((scope, key), empty())
    else:
        # Roll up disjoint month/year samples without scanning observations again.
        for (kind, period_key), data in list(buckets.items()):
            if kind != 'month-year': continue
            for target_key in [('month', period_key[5:]), ('year', period_key[:4]), ('all', 'all')]:
                if target_key not in buckets: buckets[target_key] = empty()
                target = buckets[target_key]
                target['stations'].update(data['stations'])
                for label, record in data['records'].items():
                    merged = target['records'][label]
                    merged['sample_count'] += record['sample_count']
                    if include_values:
                        merged['top_values'] = sorted(merged.get('top_values', []) + record.get('top_values', []))[:10]
                    value, old = record['value'], merged['value']
                    if value is None: continue
                    if old is None or (value < old if label.startswith('lowest') else value > old):
                        merged['value'] = value
                        merged['holders'] = list(record['holders'])
                    elif value == old:
                        merged['holders'].extend(record['holders'])
    for data in buckets.values():
        data['station_count'] = len(data.pop('stations'))
        for record in data['records'].values():
            record['holders'].sort(key=lambda holder: (holder[1], holder[0]))
    return buckets


def station_highlights(source, products, scope=None, key=None):
    """One extreme per station/category, with ten stations per period.

    Roll up each station before ranking: one station must not fill multiple
    places with different dates or years. Retain all dates tied at its extreme.
    Bounded national lists keep the serving index small.
    """
    buckets = {}
    for (station,) in source.execute('SELECT station_id FROM stations ORDER BY station_id'):
        periods = aggregate(source, products, scope, key, [station], include_days=False)
        for period_key, data in periods.items():
            target = buckets.setdefault(period_key, {'station_count': 0, 'records': {k: [] for k, _, _ in RECORDS}})
            target['station_count'] += data['station_count']
            for label, record in data['records'].items():
                if record['value'] is None:
                    continue
                ranking = target['records'][label]
                ranking.append({'station_id': station, 'record_type': label,
                                'value': record['value'], 'sample_count': record['sample_count'],
                                'dates': [when for _, when in record['holders']]})
                ranking.sort(key=lambda r: (r['value'] if label.startswith('lowest') else -r['value'], r['station_id']))
                del ranking[10:]
    return buckets


def is_flat_station(station):
    """User-defined lowland group; unknown elevations are not assumed flat."""
    elevation = resolve_station_elevation(station['station_id'], station.get('elevation_m'))
    return (station['station_id'] != '0-20000-0-15319'
            and elevation is not None and math.isfinite(elevation) and elevation <= 800)


def ranked_highlights(source, products, scope=None, key=None, ranking=None, station_group=None):
    """Bounded rankings for both modes/groups, using a single scan per station.

    Ten candidates from each disjoint month/year are sufficient for every
    rolled-up top ten. Filtering happens before merging, never after truncation.
    """
    buckets = {}
    cursor = source.execute('SELECT * FROM stations ORDER BY station_id')
    columns = [column[0] for column in cursor.description]
    stations = [dict(zip(columns, row)) for row in cursor]
    for station in stations:
        sid = station['station_id']
        groups = ['all'] + (['flat'] if is_flat_station(station) else [])
        if station_group is not None:
            groups = [group for group in groups if group == station_group]
        if not groups:
            continue
        periods = aggregate(source, products, scope, key, [sid], include_values=ranking != 'station')
        for period_key, data in periods.items():
            for mode in ([ranking] if ranking else ['station', 'value']):
                for group in groups:
                    target = buckets.setdefault((*period_key, mode, group),
                        {'station_count': 0, 'records': {label: [] for label, _, _ in RECORDS}})
                    target['station_count'] += data['station_count']
                    for label, record in data['records'].items():
                        if record['value'] is None:
                            continue
                        if mode == 'station':
                            candidates = [{'station_id': sid, 'record_type': label, 'value': record['value'],
                                           'sample_count': record['sample_count'],
                                           'dates': [when for _, when in record['holders']]}]
                        else:
                            candidates = [{'station_id': sid, 'record_type': label,
                                           'value': value if label.startswith('lowest') else -value,
                                           'sample_count': 1, 'dates': [when]}
                                          for value, when in record.get('top_values', [])]
                        rows = target['records'][label]
                        rows.extend(candidates)
                        rows.sort(key=lambda r: (r['value'] if label.startswith('lowest') else -r['value'],
                                                 *( (r['dates'][0], r['station_id']) if mode == 'value'
                                                    else (r['station_id'],) )))
                        del rows[10:]
    return buckets


def build_index(source, products):
    buckets = aggregate(source, products)
    products.execute('CREATE TABLE national_records (scope TEXT, period TEXT, data_json TEXT NOT NULL, PRIMARY KEY(scope,period)) WITHOUT ROWID')
    products.executemany('INSERT INTO national_records VALUES (?,?,?)',
                         ((scope, key, json.dumps(data, separators=(',', ':'), allow_nan=False))
                          for (scope, key), data in buckets.items()))
    products.commit()
    highlights = ranked_highlights(source, products)
    products.execute('CREATE TABLE national_rankings (scope TEXT, period TEXT, ranking TEXT, station_group TEXT, data_json TEXT NOT NULL, PRIMARY KEY(scope,period,ranking,station_group)) WITHOUT ROWID')
    products.executemany('INSERT INTO national_rankings VALUES (?,?,?,?,?)',
                         ((*key, json.dumps(data, separators=(',', ':'), allow_nan=False))
                          for key, data in highlights.items()))
    products.commit()
    return len(buckets)
