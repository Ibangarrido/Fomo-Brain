import io
import json
import unittest
from urllib.error import HTTPError
from unittest.mock import Mock
import gmgn_readonly as gmgn


class GMGNReadOnlyTests(unittest.TestCase):
    def test_no_key_makes_no_requests_and_cannot_enable_entries(self):
        fetch = Mock()
        report = gmgn.preflight('', fetch=fetch)
        fetch.assert_not_called()
        self.assertEqual(report['status'], 'MISSING_API_KEY')
        self.assertFalse(report['execution_enabled'])
        self.assertFalse(report['paper_entries_enabled'])

    def test_success_is_schema_evidence_not_a_fill_or_connected_trading(self):
        report = gmgn.preflight('SECRET', fetch=lambda *args: {'price': 1, 'echo': 'SECRET'}, pause=lambda s: None)
        self.assertEqual(report['status'], 'AWAITING_SCHEMA_VALIDATION')
        self.assertNotIn('SECRET', json.dumps(report))
        self.assertIsNone(report['net_exit_value'])

    def test_http_block_stops_without_retries_or_echoing_error(self):
        for status in (401, 403, 429):
            fetch = Mock(side_effect=HTTPError('https://example.invalid', status, 'SECRET', {}, None))
            report = gmgn.preflight('SECRET', fetch=fetch)
            self.assertEqual(fetch.call_count, 1)
            self.assertNotIn('SECRET', json.dumps(report))

    def test_only_fixed_get_market_endpoints_auth_header_not_url(self):
        class Response(io.BytesIO):
            status = 200
        calls = []
        def open_request(request, timeout):
            calls.append(request)
            return Response(b'{"code":0,"data":{"price":1}}')
        for kind in gmgn.ENDPOINTS:
            gmgn.query(kind, 'SECRET', opener=open_request)
        for request in calls:
            self.assertEqual(request.get_method(), 'GET')
            self.assertTrue(request.full_url.startswith(gmgn.HOST + '/v1/'))
            self.assertNotIn('SECRET', request.full_url)
            self.assertNotIn('/trade/', request.full_url)
        with self.assertRaises(KeyError):
            gmgn.query('swap', 'SECRET', opener=open_request)

    def test_bad_envelope_and_missing_data_are_rejected(self):
        class Response(io.BytesIO):
            status = 200
        for payload in ({'code':False,'data':{'price':1}}, {'code':0,'data':None}, {'code':0,'data':[]}, {'code':1,'data':{'price':1}}):
            with self.assertRaises(ValueError):
                gmgn.query('info', 'SECRET', opener=lambda *a, **k: Response(json.dumps(payload).encode()))


if __name__ == '__main__':
    unittest.main()
