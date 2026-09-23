"""Compact national extremes, retaining every tied station/date and variable QC."""
import json
import math
from datetime import date

from .phase3_products import RECORDS


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


def aggregate(source, products, scope=None, key=None):
    """Build all periods once, or a single period for an unprepared local archive."""
    buckets = {}
    variables = list(dict.fromkeys(variable for _, variable, _ in RECORDS))
    positions = [(label, variables.index(variable)+1, variable, op == 'min') for label, variable, op in RECORDS]
    for (station,) in source.execute('SELECT station_id FROM stations ORDER BY station_id'):
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
            keys = [(scope, key)] if scope else [('day', when[5:]), ('month-year', when[:7])]
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


def build_index(source, products):
    buckets = aggregate(source, products)
    products.execute('CREATE TABLE national_records (scope TEXT, period TEXT, data_json TEXT NOT NULL, PRIMARY KEY(scope,period)) WITHOUT ROWID')
    products.executemany('INSERT INTO national_records VALUES (?,?,?)',
                         ((scope, key, json.dumps(data, separators=(',', ':'), allow_nan=False))
                          for (scope, key), data in buckets.items()))
    products.commit()
    return len(buckets)
