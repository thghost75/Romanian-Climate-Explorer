"""Temperature ranges calculated from eligible observations at one station."""
import calendar
import math

AMPLITUDE = 'thermal_amplitude_c'
AMPLITUDE_SQL = '(CASE WHEN tmax_c >= tmin_c THEN ROUND(tmax_c-tmin_c, 6) END)'


def expression(variable):
    return AMPLITUDE_SQL if variable == AMPLITUDE else variable


def inputs(variable):
    return ('tmin_c', 'tmax_c') if variable == AMPLITUDE else (variable,)


def amplitude(low, high):
    if low is None or high is None or not math.isfinite(low) or not math.isfinite(high) or high < low:
        return None
    return round(high-low, 6)


def excursion(period_key, data):
    kind, key = period_key
    if kind not in ('month-year', 'year'):
        return None
    low, high = data['records']['lowest_tmin'], data['records']['highest_tmax']
    value = amplitude(low['value'], high['value'])
    if value is None:
        return None
    year = int(key[:4])
    month = int(key[5:]) if kind == 'month-year' else None
    expected = calendar.monthrange(year, month)[1] if month else 365 + calendar.isleap(year)
    return {'period': key, 'year': year, 'month': month, 'value': value,
            'tmin_c': low['value'], 'tmax_c': high['value'],
            'tmin_dates': [d for _, d in low['holders']], 'tmax_dates': [d for _, d in high['holders']],
            'tmin_days': low['sample_count'], 'tmax_days': high['sample_count'],
            'expected_days': expected,
            'complete': low['sample_count'] == expected and high['sample_count'] == expected}


def merge_excursion(rows, candidate, mode):
    """Station mode keeps its largest individual period, retaining tied periods."""
    if mode == 'station':
        previous = next((r for r in rows if r['station_id'] == candidate['station_id']), None)
        if previous:
            if previous['value'] > candidate['value']:
                return
            if previous['value'] == candidate['value']:
                previous['periods'].extend(candidate['periods'])
                previous['periods'].sort(key=lambda p: p['period'])
                return
            rows.remove(previous)
    rows.append(candidate)
    rows.sort(key=lambda r: (-r['value'], r['periods'][0]['period'] if mode == 'value' else '', r['station_id']))
    del rows[10:]
