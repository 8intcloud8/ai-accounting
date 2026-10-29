"""Local Xero OAuth and MCP launcher. Never log credentials or token responses."""
import argparse
import base64
import contextlib
import getpass
import hashlib
import http.server
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

ROOT = Path.home() / '.xero_mcp'
REDIRECT = 'http://localhost:8000/callback'
SCOPES = 'offline_access accounting.invoices.read accounting.payments.read accounting.banktransactions.read accounting.contacts.read accounting.settings.read accounting.manualjournals.read accounting.reports.profitandloss.read accounting.reports.balancesheet.read accounting.reports.aged.read accounting.reports.trialbalance.read'


def private_dir():
    if ROOT.is_symlink():
        raise RuntimeError('Credential directory must not be a symlink.')
    ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name != 'nt':
        ROOT.chmod(0o700)


@contextlib.contextmanager
def locked():
    """OS lock released automatically on process exit, including crashes."""
    private_dir()
    path = ROOT / 'auth.lock'
    if path.is_symlink():
        raise RuntimeError('Lock must not be a symlink.')
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(fd, 'r+b') as stream:
        if os.name == 'nt':
            import msvcrt
            stream.write(b'0')
            stream.flush()
            stream.seek(0)
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                raise RuntimeError('Another Xero authorization or refresh is running.') from None
        else:
            import fcntl
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise RuntimeError('Another Xero authorization or refresh is running.') from None
        yield


def save(data):
    private_dir()
    fd, name = tempfile.mkstemp(dir=ROOT, prefix='.state-')
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(data, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, ROOT / 'state.json')
    finally:
        if os.path.exists(name):
            os.unlink(name)


def load():
    path = ROOT / 'state.json'
    if path.is_symlink():
        raise RuntimeError('Credential file must not be a symlink.')
    if path.exists():
        if os.name != 'nt':
            path.chmod(0o600)
        return json.loads(path.read_text())
    # Read previous config as data; never execute it as shell code.
    cfg = {}
    old = ROOT / 'config'
    if old.exists():
        for line in old.read_text().splitlines():
            key, sep, value = line.partition('=')
            if sep and key.strip() in ('XERO_CLIENT_ID', 'XERO_CLIENT_SECRET'):
                cfg[key.strip()] = value.strip().strip('"')
    token = ROOT / 'refresh_token'
    if token.exists():
        cfg['refresh_token'] = token.read_text().strip()
    return cfg


def request(url, form=None, headers=None):
    data = urllib.parse.urlencode(form).encode() if form is not None else None
    req = urllib.request.Request(url, data=data, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f'Xero request failed (HTTP {exc.code}); check app configuration or reauthorize.') from None
    except (urllib.error.URLError, TimeoutError, ValueError):
        raise RuntimeError('Xero network request failed or returned invalid JSON. Retry; no token response logged.') from None


def exchange(cfg, form):
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    secret = cfg.get('XERO_CLIENT_SECRET')
    if secret:
        basic = base64.b64encode(f"{cfg['XERO_CLIENT_ID']}:{secret}".encode()).decode()
        headers['Authorization'] = 'Basic ' + basic
    else:
        form['client_id'] = cfg['XERO_CLIENT_ID']
    result = request('https://identity.xero.com/connect/token', form, headers)
    if not all(isinstance(result.get(k), str) and result[k] for k in ('access_token', 'refresh_token')):
        raise RuntimeError('Incomplete token response; saved credentials unchanged.')
    expires_in = result.get('expires_in', 1800)
    if not isinstance(expires_in, (int, float)) or isinstance(expires_in, bool) or not 0 < expires_in <= 86400:
        raise RuntimeError('Invalid token lifetime; saved credentials unchanged.')
    cfg.update(refresh_token=result['refresh_token'], expires_in=expires_in)
    save(cfg)  # Persist rotation before attempting any other operation.
    return result['access_token']


def setup(args):
    with locked():
        previous = load()
        cid = input('Xero Client ID (local input): ').strip()
        if not cid:
            cid = previous.get('XERO_CLIENT_ID', '')
        if not cid:
            raise RuntimeError('Client ID required.')
        cfg = {'XERO_CLIENT_ID': cid}
        if args.web_app:
            cfg['XERO_CLIENT_SECRET'] = getpass.getpass('Xero Web App secret (hidden): ').strip()
            if not cfg['XERO_CLIENT_SECRET']:
                raise RuntimeError('Web App secret required.')
        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
        params = dict(response_type='code', client_id=cid, redirect_uri=REDIRECT,
                      scope=args.scopes, state=state)
        if not args.web_app:
            params.update(code_challenge=challenge, code_challenge_method='S256')
        outcome = {}

        class Callback(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                parsed = urllib.parse.urlparse(self.path)
                query = urllib.parse.parse_qs(parsed.query)
                valid = (parsed.path == '/callback' and len(query.get('state', [])) == 1
                         and secrets.compare_digest(query['state'][0], state))
                if not valid:
                    self.send_error(400, 'Invalid callback')
                    return
                if query.get('error'):
                    outcome['error'] = True
                elif len(query.get('code', [])) == 1:
                    outcome['code'] = query['code'][0]
                else:
                    self.send_error(400, 'Missing authorization code')
                    return
                self.send_response(200)
                self.send_header('Content-Type', 'text/plain; charset=utf-8')
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write(b'Authorization received. Check the setup window for the final result.')

            def log_message(self, *_):
                pass

        with http.server.HTTPServer(('127.0.0.1', 8000), Callback) as server:
            server.timeout = 1
            url = 'https://login.xero.com/identity/connect/authorize?' + urllib.parse.urlencode(params)
            print('Opening Xero. Authorize the required organisation. Waiting up to 5 minutes.')
            if not webbrowser.open(url):
                raise RuntimeError('Browser did not open. Run setup in your desktop session.')
            deadline = time.monotonic() + 300
            while not outcome and time.monotonic() < deadline:
                server.handle_request()
        if outcome.get('error'):
            raise RuntimeError('Authorization declined or failed; saved credentials unchanged.')
        if not outcome.get('code'):
            raise RuntimeError('Authorization timed out; saved credentials unchanged.')
        form = dict(grant_type='authorization_code', code=outcome['code'], redirect_uri=REDIRECT)
        if not args.web_app:
            form['code_verifier'] = verifier
        access = exchange(cfg, form)
    tenants = request('https://api.xero.com/connections', headers={'Authorization': 'Bearer ' + access})
    print('Authorization saved to ~/.xero_mcp/state.json.')
    print('Connected organisations:')
    for tenant in tenants:
        print(' -', tenant.get('tenantName', '(unnamed)'), tenant.get('tenantId', ''))
    print('Choose the intended organisation before accessing records. MCP registration is a separate step.')


def refresh_access():
    with locked():
        cfg = load()
        if not cfg.get('XERO_CLIENT_ID') or not cfg.get('refresh_token'):
            raise RuntimeError('Run oauth-setup.py first.')
        access = exchange(cfg, dict(grant_type='refresh_token', refresh_token=cfg['refresh_token']))
        return {'access_token': access, 'expires_in': cfg['expires_in']}


def run_server(args):
    npm = shutil.which('npm.cmd' if os.name == 'nt' else 'npm')
    node = shutil.which('node')
    if not npm or not node:
        raise RuntimeError('Node.js/npm required.')
    # A private pinned runtime avoids patching upstream package sources or relying
    # on npx cache layout. npm emits diagnostics on stderr, never MCP stdout.
    private_dir()
    runtime = ROOT / 'runtime'
    package = runtime / 'node_modules/@xeroapi/xero-mcp-server'
    manifest = package / 'package.json'
    if not manifest.exists() or json.loads(manifest.read_text()).get('version') != '0.0.17':
        subprocess.run([npm, 'install', '--prefix', str(runtime), '--ignore-scripts',
                        '--no-audit', '--no-fund', '@xeroapi/xero-mcp-server@0.0.17'],
                       stdout=sys.stderr, check=True)
    env = {k: v for k, v in os.environ.items() if k not in
           ('XERO_CLIENT_ID', 'XERO_CLIENT_SECRET', 'XERO_CLIENT_BEARER_TOKEN')}
    env['XERO_CLIENT_BEARER_TOKEN'] = 'managed-by-local-token-manager'
    script = Path(__file__).resolve()
    return subprocess.call([node, str(script.with_name('managed-server.mjs')),
                            str(package), sys.executable, str(script)],
                           env=env, cwd=runtime)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Xero OAuth setup and MCP launcher')
    parser.add_argument('mode', choices=['setup', 'serve', 'token'])
    parser.add_argument('--web-app', action='store_true', help='Use an existing confidential Web App instead of PKCE')
    parser.add_argument('--scopes', default=SCOPES, help='Explicit space-separated scopes; defaults to read-only accounting')
    args = parser.parse_args(argv)
    try:
        if args.mode == 'token':
            print(json.dumps(refresh_access()))
            return 0
        return run_server(args) if args.mode == 'serve' else setup(args)
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError) as exc:
        # Never stringify low-level exceptions: they may contain sensitive request data.
        message = str(exc) if isinstance(exc, RuntimeError) else 'Local setup failed; check file permissions, port 8000 and configuration.'
        print('ERROR: ' + message, file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print('Cancelled.', file=sys.stderr)
        return 130


if __name__ == '__main__':
    sys.exit(main())
