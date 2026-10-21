"""Validate launch configuration and smoke-test a clean packaged MCP plugin."""

import argparse
import json
import os
import selectors
import subprocess
import tempfile
import zipfile
from pathlib import Path


def validate(plugin: Path) -> dict:
    """Reject nonportable launch paths before a release can be produced."""
    manifest = json.loads((plugin / '.codex-plugin/plugin.json').read_text())
    if 'mcpServers' not in manifest:
        return {}
    config = json.loads((plugin / manifest['mcpServers']).read_text())
    servers = config['mcpServers']
    for name, server in servers.items():
        if 'command' not in server:
            continue
        if '${' in json.dumps(server):
            raise ValueError(f'{name}: unresolved variable in launch configuration')
        if server.get('cwd') != '.':
            raise ValueError(f'{name}: use plugin-relative cwd="."')
        args = server.get('args', [])
        if server['command'] != '/bin/sh' or not args:
            raise ValueError(f'{name}: expected packaged shell launcher')
        launcher = (plugin / args[0]).resolve()
        if Path(args[0]).is_absolute() or not launcher.is_relative_to(plugin.resolve()):
            raise ValueError(f'{name}: launcher escapes plugin')
        if not launcher.is_file():
            raise ValueError(f'{name}: launcher missing: {args[0]}')
    return servers


def smoke(plugin: Path, expected_tool: str) -> None:
    """Launch the extracted package exactly as declared, then discover its tool."""
    servers = validate(plugin)
    if not servers:
        raise ValueError('No MCP servers declared; cannot verify expected tool')
    for name, server in servers.items():
        if 'command' not in server:
            raise ValueError(f'{name}: local smoke test requires stdio')
        env = dict(os.environ)
        env.pop('CLAUDE_PLUGIN_ROOT', None)
        env.pop('CODEX_PLUGIN_ROOT', None)
        with tempfile.TemporaryFile(mode='w+') as errors:
            process = subprocess.Popen(
                [server['command'], *server['args']], cwd=plugin,
                env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=errors, text=True,
            )
            assert process.stdin is not None and process.stdout is not None
            try:
                def request(identifier, method, params):
                    process.stdin.write(json.dumps({
                        'jsonrpc': '2.0', 'id': identifier,
                        'method': method, 'params': params,
                    }) + '\n')
                    process.stdin.flush()
                    with selectors.DefaultSelector() as selector:
                        selector.register(process.stdout, selectors.EVENT_READ)
                        if not selector.select(30):
                            raise RuntimeError(f'{name}: handshake/discovery timed out')
                    line = process.stdout.readline()
                    if not line:
                        errors.seek(0)
                        raise RuntimeError(f'{name}: exited: {errors.read()}')
                    response = json.loads(line)
                    if response.get('id') != identifier or 'error' in response:
                        raise RuntimeError(f'{name}: unexpected response: {response}')
                    return response['result']

                request(1, 'initialize', {
                    'protocolVersion': '2024-11-05', 'capabilities': {},
                    'clientInfo': {'name': 'release-check', 'version': '1'},
                })
                process.stdin.write('{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
                process.stdin.flush()
                names = [tool['name'] for tool in request(2, 'tools/list', {})['tools']]
                if expected_tool not in names:
                    raise RuntimeError(f'{name}: missing {expected_tool}; got {names}')
            finally:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                process.stdin.close()
                process.stdout.close()


def package(plugin: Path, output: Path, expected_tool: str) -> None:
    """Publish the archive only after its extracted payload passes discovery."""
    validate(plugin)
    if not (plugin / 'mcp-server/dist/server.mjs').is_file():
        raise ValueError('Build the MCP server before packaging')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        staged = Path(temporary) / 'plugin.zip'
        with zipfile.ZipFile(staged, 'w', zipfile.ZIP_DEFLATED) as archive:
            for source in plugin.rglob('*'):
                relative = source.relative_to(plugin)
                if not source.is_file() or source.is_symlink():
                    continue
                if any(part in {'node_modules', '.git', '__pycache__', '.build.lock'} for part in relative.parts):
                    continue
                if source.name.startswith('.env') or source.suffix in {'.log', '.pdf', '.zip', '.plugin'}:
                    continue
                archive.write(source, relative)
        extracted = Path(temporary) / 'extracted'
        with zipfile.ZipFile(staged) as archive:
            archive.extractall(extracted)
        smoke(extracted, expected_tool)
        output.write_bytes(staged.read_bytes())
    print(f'PASS: extracted package exposes {expected_tool}: {output}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plugin', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--expected-tool', required=True)
    args = parser.parse_args()
    package(args.plugin.resolve(), args.output, args.expected_tool)
