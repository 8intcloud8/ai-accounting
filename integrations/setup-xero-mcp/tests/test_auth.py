import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.parse

spec = importlib.util.spec_from_file_location('auth', Path(__file__).parents[1] / 'scripts/xero_auth.py')
auth = importlib.util.module_from_spec(spec)
spec.loader.exec_module(auth)


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'credentials'
        self.patch = patch.object(auth, 'ROOT', self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_atomic_failure_preserves_previous_credentials(self):
        auth.save({'refresh_token': 'old'})
        with patch.object(auth.os, 'replace', side_effect=OSError('disk failure')):
            with self.assertRaises(OSError):
                auth.save({'refresh_token': 'new'})
        self.assertEqual(auth.load()['refresh_token'], 'old')
        self.assertEqual(list(self.root.glob('.state-*')), [])
        if auth.os.name != 'nt':
            self.assertEqual((self.root / 'state.json').stat().st_mode & 0o777, 0o600)
            self.assertEqual(self.root.stat().st_mode & 0o777, 0o700)

    def test_incomplete_rotation_does_not_overwrite_token(self):
        cfg = {'XERO_CLIENT_ID': 'client', 'refresh_token': 'old'}
        auth.save(cfg)
        with patch.object(auth, 'request', return_value={'access_token': 'access'}):
            with self.assertRaises(RuntimeError):
                auth.exchange(cfg, {'grant_type': 'refresh_token'})
        self.assertEqual(auth.load()['refresh_token'], 'old')

    def test_rotation_persisted_before_access_returned(self):
        cfg = {'XERO_CLIENT_ID': 'client', 'refresh_token': 'old'}
        with patch.object(auth, 'request', return_value={'access_token': 'access', 'refresh_token': 'new'}):
            self.assertEqual(auth.exchange(cfg, {}), 'access')
        self.assertEqual(auth.load()['refresh_token'], 'new')

    def test_callback_rejects_wrong_state_and_path_then_accepts_pkce(self):
        opened = {}
        errors = []
        handler_checks = []
        class Server:
            timeout = 0
            def __init__(self, address, handler):
                self.handler = handler
            def __enter__(self):
                return self
            def __exit__(self, *_):
                pass
            def handle_request(self):
                query = urllib.parse.parse_qs(urllib.parse.urlparse(opened['url']).query)
                for path in ['/callback?code=bad&state=wrong', '/other?code=bad&state=' + query['state'][0], '/callback?code=good&state=' + query['state'][0]]:
                    h = self.handler.__new__(self.handler)
                    h.path = path
                    h.wfile = io.BytesIO()
                    h.send_error = lambda code, message: errors.append(code)
                    h.send_response = lambda *_: None
                    h.send_header = lambda *_: None
                    h.end_headers = lambda: None
                    h.do_GET()
                handler_checks.append(query)
        def browser(url):
            opened['url'] = url
            return True
        with patch.object(auth.http.server, 'HTTPServer', Server), patch.object(auth.webbrowser, 'open', browser), patch('builtins.input', return_value='client'), patch.object(auth, 'exchange', return_value='access') as exchange, patch.object(auth, 'request', return_value=[]):
            auth.setup(type('Args', (), {'web_app': False, 'scopes': auth.SCOPES})())
        self.assertEqual(errors, [400, 400])
        form = exchange.call_args.args[1]
        self.assertEqual(form['code'], 'good')
        self.assertGreaterEqual(len(form['code_verifier']), 43)
        self.assertEqual(handler_checks[0]['code_challenge_method'], ['S256'])
        self.assertNotEqual(handler_checks[0]['state'], ['123'])

    def test_network_failure_preserves_saved_token(self):
        import urllib.error
        auth.save({'XERO_CLIENT_ID': 'client', 'refresh_token': 'old'})
        with patch.object(auth.urllib.request, 'urlopen', side_effect=urllib.error.URLError('private details')):
            with self.assertRaisesRegex(RuntimeError, 'network request failed'):
                auth.exchange(auth.load(), {'grant_type': 'refresh_token', 'refresh_token': 'old'})
        self.assertEqual(auth.load()['refresh_token'], 'old')

    def test_nested_lock_rejects_concurrent_rotation(self):
        with auth.locked():
            with self.assertRaises(RuntimeError):
                with auth.locked():
                    self.fail('Lock acquired twice')


if __name__ == '__main__':
    unittest.main()
