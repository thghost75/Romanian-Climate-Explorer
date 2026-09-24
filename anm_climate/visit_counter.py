"""Small persistent visit total, separate from the read-only climate archive."""
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from datetime import datetime, timezone
from http.cookies import SimpleCookie, CookieError
from urllib.request import Request, urlopen

ORIGIN = 'https://romanian-climate-explorer.vercel.app'
COOKIE = '__Host-rce-visit'
WINDOW = 30 * 60
KEY = 'rce:public-visits:v1'
SCRIPT = """
if ARGV[1] == '1' then
  redis.call('HSETNX', KEYS[1], 'since', ARGV[2])
  redis.call('HINCRBY', KEYS[1], 'total', 1)
end
return {redis.call('HGET', KEYS[1], 'total') or '0',
        redis.call('HGET', KEYS[1], 'since') or ''}
"""


def credentials():
    for prefix, url_suffix, token_suffix in (
        ('COUNTER_REDIS', '_REST_URL', '_REST_TOKEN'),
        ('KV', '_REST_API_URL', '_REST_API_TOKEN'),
        ('UPSTASH_REDIS', '_REST_URL', '_REST_TOKEN'),
    ):
        url, token = os.getenv(prefix + url_suffix), os.getenv(prefix + token_suffix)
        if url and token:
            if not re.fullmatch(r'https://[a-zA-Z0-9.-]+\.upstash\.io/?', url):
                raise ValueError('Invalid counter storage URL')
            return url.rstrip('/'), token
    raise ValueError('Counter storage is not configured')


def signature(value, secret):
    return hmac.new(secret.encode(), ('rce-visit:' + value).encode(), hashlib.sha256).hexdigest()


def recent_visit(cookie_header, secret, now):
    try:
        cookies = SimpleCookie()
        cookies.load(cookie_header)
        value = cookies[COOKIE].value
        stamp, nonce, signed = value.split('.')
        message = stamp + '.' + nonce
        return (0 <= now - int(stamp) < WINDOW
                and hmac.compare_digest(signature(message, secret), signed))
    except (CookieError, KeyError, ValueError):
        return False


def storage_total(url, token, increment, now):
    day = datetime.fromtimestamp(now, timezone.utc).date().isoformat()
    command = ['EVAL', SCRIPT, 1, KEY, '1' if increment else '0', day]
    request = Request(url, data=json.dumps(command).encode(), headers={
        'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json',
    }, method='POST')
    # Do not retry increments: a timeout can occur after Redis has committed.
    with urlopen(request, timeout=4) as response:
        result = json.load(response)
    total, since = result['result']
    total = int(total)
    if total < 0 or (since and not re.fullmatch(r'\d{4}-\d{2}-\d{2}', since)):
        raise ValueError('Invalid counter response')
    return {'visits': total, 'since': since or None}


def visit_response(method, headers):
    """Return status, public payload and headers; never expose storage credentials."""
    extra = {'Cache-Control': 'no-store'}
    if method == 'POST':
        if (os.getenv('VERCEL_ENV') != 'production'
                or headers.get('Origin') != ORIGIN
                or headers.get('X-RCE-Visit') != '1'):
            return 403, {'error': 'Visits can only be counted on the live site.'}, extra
    elif method != 'GET':
        return 405, {'error': 'Use GET or POST.'}, extra
    try:
        url, token = credentials()
        now = int(time.time())
        bot = re.search(r'bot|crawler|spider|headless|preview', headers.get('User-Agent', ''), re.I)
        increment = method == 'POST' and not bot and not recent_visit(headers.get('Cookie', ''), token, now)
        payload = storage_total(url, token, increment, now)
        if increment:
            value = str(now) + '.' + secrets.token_hex(8)
            value += '.' + signature(value, token)
            extra['Set-Cookie'] = f'{COOKIE}={value}; Path=/; Max-Age={WINDOW}; Secure; HttpOnly; SameSite=Lax'
        if method == 'GET':
            extra['Cache-Control'] = 'public, max-age=30, s-maxage=60'
        return 200, payload, extra
    except (OSError, ValueError, KeyError, TypeError):
        return 503, {'error': 'Visit counter temporarily unavailable.'}, extra
