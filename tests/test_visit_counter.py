import io
import json
import unittest
from email.message import Message
from unittest.mock import patch

from anm_climate import visit_counter as counter


class VisitCounterTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict('os.environ', {
            'VERCEL_ENV': 'production',
            'COUNTER_REDIS_REST_URL': 'https://example.upstash.io',
            'COUNTER_REDIS_REST_TOKEN': 'test-secret',
        }, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.headers = Message()
        self.headers['Origin'] = counter.ORIGIN
        self.headers['X-RCE-Visit'] = '1'
        self.headers['User-Agent'] = 'Mozilla/5.0'

    @patch.object(counter, 'storage_total', return_value={'visits': 42, 'since': '2026-09-24'})
    def test_refresh_deduplication_and_expiry(self, storage):
        with patch.object(counter.time, 'time', return_value=10000):
            status, payload, headers = counter.visit_response('POST', self.headers)
        self.assertEqual((status, payload['visits']), (200, 42))
        self.assertTrue(storage.call_args.args[2])
        self.assertIn('Secure; HttpOnly; SameSite=Lax', headers['Set-Cookie'])
        self.headers['Cookie'] = headers['Set-Cookie'].split(';')[0]
        with patch.object(counter.time, 'time', return_value=10001):
            _, _, headers = counter.visit_response('POST', self.headers)
        self.assertFalse(storage.call_args.args[2])
        self.assertNotIn('Set-Cookie', headers)
        with patch.object(counter.time, 'time', return_value=11800):
            counter.visit_response('POST', self.headers)
        self.assertTrue(storage.call_args.args[2])

    @patch.object(counter, 'storage_total', return_value={'visits': 42, 'since': '2026-09-24'})
    def test_get_and_known_bots_do_not_increment(self, storage):
        status, _, headers = counter.visit_response('GET', self.headers)
        self.assertEqual(status, 200)
        self.assertFalse(storage.call_args.args[2])
        self.assertIn('s-maxage=60', headers['Cache-Control'])
        self.headers.replace_header('User-Agent', 'Googlebot')
        counter.visit_response('POST', self.headers)
        self.assertFalse(storage.call_args.args[2])

    @patch.object(counter, 'storage_total')
    def test_foreign_origin_preview_and_missing_header_are_blocked(self, storage):
        self.headers.replace_header('Origin', 'https://other.example')
        self.assertEqual(counter.visit_response('POST', self.headers)[0], 403)
        self.headers.replace_header('Origin', counter.ORIGIN)
        with patch.dict('os.environ', {'VERCEL_ENV': 'preview'}):
            self.assertEqual(counter.visit_response('POST', self.headers)[0], 403)
        del self.headers['X-RCE-Visit']
        self.assertEqual(counter.visit_response('POST', self.headers)[0], 403)
        storage.assert_not_called()

    def test_forged_or_future_cookies_do_not_deduplicate(self):
        value = '10000.nonce'
        signed = value + '.' + counter.signature(value, 'test-secret')
        self.assertTrue(counter.recent_visit(counter.COOKIE + '=' + signed, 'test-secret', 10001))
        self.assertFalse(counter.recent_visit(counter.COOKIE + '=' + signed, 'wrong-secret', 10001))
        self.assertFalse(counter.recent_visit(counter.COOKIE + '=' + signed, 'test-secret', 9999))
        self.assertFalse(counter.recent_visit(counter.COOKIE + '=bad', 'test-secret', 10001))

    @patch.object(counter, 'urlopen', side_effect=TimeoutError('private provider details'))
    def test_failure_is_not_a_fake_zero_and_is_not_retried(self, request):
        status, payload, headers = counter.visit_response('POST', self.headers)
        self.assertEqual(status, 503)
        self.assertNotIn('visits', payload)
        self.assertNotIn('private', json.dumps(payload))
        self.assertNotIn('Set-Cookie', headers)
        self.assertEqual(request.call_count, 1)

    @patch.object(counter, 'urlopen')
    def test_atomic_storage_command_sends_no_visitor_information(self, request):
        request.return_value = io.BytesIO(b'{"result":["42","2026-09-24"]}')
        self.assertEqual(counter.storage_total('https://example.upstash.io', 'secret', True, 10000)['visits'], 42)
        command = json.loads(request.call_args.args[0].data)
        self.assertEqual(command[:4], ['EVAL', counter.SCRIPT, 1, counter.KEY])
        self.assertEqual(command[4], '1')
        self.assertEqual(len(command), 6)

    @patch.object(counter, 'storage_total')
    def test_unconfigured_counter_fails_without_storage_request(self, storage):
        with patch.dict('os.environ', {}, clear=True):
            self.assertEqual(counter.visit_response('GET', self.headers)[0], 503)
        storage.assert_not_called()


if __name__ == '__main__':
    unittest.main()
