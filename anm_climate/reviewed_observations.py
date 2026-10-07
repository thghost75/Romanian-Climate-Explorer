"""Apply documented reviews only to a disposable serving copy, never the archive."""
import json
import math
from pathlib import Path

REVIEWS = Path(__file__).with_name('observation_reviews.json')


def apply_reviews(source, products, reviews=None):
    from .phase3_policy import Policy, VARIABLES
    from .snapshot_products import SCHEMA
    from scripts.refresh_daily import refresh_products

    reviews = json.loads(REVIEWS.read_text(encoding='utf-8')) if reviews is None else reviews
    applied = []
    affected = {}
    seen = set()
    for review in reviews:
        sid, when, variable = review['station_id'], review['start_date'], review['variable']
        if variable not in VARIABLES or when != review['end_date']:
            raise ValueError('Review must name one supported variable and date')
        if review['action'] not in ('correct', 'exclude'):
            raise ValueError('Unknown review action')
        identity = (sid, when, variable)
        if identity in seen:
            raise ValueError('Duplicate observation review')
        seen.add(identity)
        if review['action'] == 'correct' and not math.isfinite(review['corrected_value']):
            raise ValueError('Correction must be finite')
        row = source.execute(f'SELECT {variable} FROM daily_observations WHERE station_id=? AND date=?', (sid, when)).fetchone()
        if row is None:
            continue
        # If ANM changes the input, require a fresh review instead of silently
        # applying a correction or exclusion to a different measurement.
        if row[0] != review['original_value']:
            if review['action'] == 'correct' and row[0] == review['corrected_value']:
                continue
            raise ValueError(f'Reviewed source value changed: {sid}/{when}/{variable}')
        exclusions = affected.setdefault(sid, {})
        if review['action'] == 'correct':
            source.execute(f'UPDATE daily_observations SET {variable}=? WHERE station_id=? AND date=?',
                           (review['corrected_value'], sid, when))
        else:
            exclusions[(when, variable)] = 'reviewed_suspect_observation'
        applied.append(review)
    source.commit()
    if affected:
        products.executescript(SCHEMA)
        policy_row = products.execute("SELECT value FROM metadata WHERE key='policy'").fetchone()
        policy = Policy(**json.loads(policy_row[0])) if policy_row else Policy()
        for sid, exclusions in affected.items():
            print('Rebuilding reviewed station: ' + sid, flush=True)
            refresh_products(source, products, sid, policy, exclusions)
        for table in ('window_thresholds', 'station_build', 'pressure_quarantine'):
            products.execute(f'DROP TABLE {table}')
        products.commit()
    return applied
