#!/usr/bin/env python3
"""Version-gated desktop backend installation, dispatch, and rollback.

Run install with a release directory containing codex and codex-peer-worker.
The signed application is never modified. Re-run install after porting an update.
Unknown app versions automatically use the bundled backend.
"""
import argparse
import hashlib
import json
import os
import plistlib
from pathlib import Path
import shutil
import shlex
import subprocess
import sys
import tempfile
import platform
import tarfile
import time

APP = Path('/Applications/ChatGPT.app/Contents/Resources/codex')
ROOT = Path.home() / 'Library/Application Support/Relay/NativeCodex'
EXECUTABLES = ('codex', 'codex-peer-worker', 'codex-code-mode-host')

def version(binary):
    value = subprocess.check_output([str(binary), '--version'], text=True, timeout=10).strip()
    if not value.startswith('codex-cli ') or '/' in value:
        raise RuntimeError('Unrecognized backend version')
    return value.removeprefix('codex-cli ')

def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            result.update(block)
    return result.hexdigest()

def selected():
    current = version(APP)
    folder = ROOT / current
    try:
        manifest = json.loads((folder / 'manifest.json').read_text())
        if manifest.get('schema') == 2 and manifest['version'] == current and all(
            os.access(folder / name, os.X_OK) and digest(folder / name) == manifest['sha256'][name]
            for name in EXECUTABLES
        ):
            return folder / 'codex'
    except (OSError, KeyError, ValueError):
        pass
    return APP

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['install', 'enable', 'status', 'disable', 'exec', 'update'])
    parser.add_argument('arguments', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.action == 'update':
        current = version(APP)
        if selected() != APP:
            print('Matching verified backend already installed')
            return
        tag = 'codex-' + current + '-peer.1'
        asset = 'native-codex-' + platform.machine() + '.tar.gz'
        with tempfile.TemporaryDirectory(prefix='native-codex-download-') as temporary:
            folder = Path(temporary)
            subprocess.run(['gh', 'release', 'download', tag, '--repo',
                            'genomewalker/codex-native-peers', '--pattern', asset,
                            '--pattern', 'SHA256SUMS', '--dir', temporary], check=True, timeout=120)
            entries = [line.split() for line in (folder / 'SHA256SUMS').read_text().splitlines()]
            expected = [parts[0] for parts in entries if len(parts) == 2 and parts[1] == asset]
            if len(expected) != 1 or digest(folder / asset) != expected[0]:
                raise RuntimeError('Release checksum mismatch')
            with tarfile.open(folder / asset) as archive:
                members = archive.getmembers()
                names = [m.name for m in members]
                if len(names) != len(set(names)) or set(names) != set(EXECUTABLES) | {'LICENSE', 'NOTICE'}:
                    raise RuntimeError('Unexpected release contents')
                for member in members:
                    if not member.isfile() or member.size > 600_000_000:
                        raise RuntimeError('Unsafe release member')
                    with archive.extractfile(member) as source, (folder / member.name).open('wb') as dest:
                        shutil.copyfileobj(source, dest)
                for name in EXECUTABLES:
                    (folder / name).chmod(0o700)
            subprocess.run([sys.executable, __file__, 'install', temporary], check=True)
        return
    if args.action == 'exec':
        binary = selected()
        if binary == APP:
            os.environ.pop('CODEX_NATIVE_PEER_DIR', None)
            print('Native peer patch unavailable for this app version; using stock backend.', file=sys.stderr)
            ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
            attempt = ROOT / ('update-attempt-' + version(APP))
            try:
                with attempt.open('x') as marker:
                    marker.write('Automatic matching-release download requested\n')
                with (ROOT / 'update.log').open('ab') as log:
                    subprocess.Popen([sys.executable, __file__, 'update'],
                                     stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                     start_new_session=True)
            except OSError as error:
                if not isinstance(error, FileExistsError):
                    print('Update check unavailable; continuing with stock: ' + str(error), file=sys.stderr)
        else:
            os.environ['CODEX_NATIVE_PEER_DIR'] = '/tmp'
        os.execv(str(binary), [str(binary), *args.arguments])
    elif args.action == 'status':
        print(json.dumps({'appVersion': version(APP), 'backend': str(selected()),
                          'patched': selected() != APP}, indent=2))
    elif args.action == 'disable':
        subprocess.run(['launchctl', 'unsetenv', 'CODEX_CLI_PATH'], check=True)
        agent = Path.home() / 'Library/LaunchAgents/dev.vaklab.codex-native.plist'
        if agent.exists():
            agent.rename(agent.with_suffix('.disabled'))
        print('Override disabled for subsequent app launches. Restart the app to use stock.')
    elif args.action == 'enable':
        if selected() == APP:
            raise RuntimeError('Install a tested matching backend before activation')
        manager = ROOT / 'native-backend.py'
        shutil.copy2(Path(__file__).resolve(), manager)
        for name in ('test-native-peer-workers.py', 'test-native-desktop.py'):
            shutil.copy2(Path(__file__).resolve().with_name(name), ROOT / name)
        launcher = ROOT / 'codex'
        launcher.write_text('#!/bin/sh\nexec ' + shlex.quote(sys.executable) + ' ' +
                            shlex.quote(str(manager)) + ' exec "$@"\n')
        launcher.chmod(0o700)
        agent = Path.home() / 'Library/LaunchAgents/dev.vaklab.codex-native.plist'
        agent.parent.mkdir(parents=True, exist_ok=True)
        agent.write_bytes(plistlib.dumps({
            'Label': 'dev.vaklab.codex-native',
            'ProgramArguments': ['/bin/launchctl', 'setenv', 'CODEX_CLI_PATH', str(launcher)],
            'RunAtLoad': True,
        }))
        subprocess.run(['launchctl', 'setenv', 'CODEX_CLI_PATH', str(launcher)], check=True)
        print('Enabled for future launches and logins; signed app unchanged.')
    else:
        if len(args.arguments) != 1:
            parser.error('install requires a release build directory')
        source = Path(args.arguments[0]).resolve()
        current = version(APP)
        if version(source / 'codex') != current:
            raise RuntimeError('Refusing a backend that does not match the installed app')
        for name in EXECUTABLES:
            if not os.access(source / name, os.X_OK):
                raise RuntimeError('Missing or non-executable required companion: ' + name)
        subprocess.run([str(source / 'codex-code-mode-host'), '--help'],
                       check=True, timeout=15, stdout=subprocess.DEVNULL)
        scripts = Path(__file__).resolve().parent
        subprocess.run([sys.executable, str(scripts / 'test-native-peer-workers.py'),
                        str(source / 'codex-peer-worker')], check=True)
        subprocess.run([sys.executable, str(scripts / 'test-native-desktop.py'),
                        str(source / 'codex')], check=True)
        if version(APP) != current:
            raise RuntimeError('App updated during verification; refusing activation')
        ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
        target = ROOT / current
        if target.exists() and selected() != APP:
            raise RuntimeError('A valid matching version is already installed')
        with tempfile.TemporaryDirectory(dir=ROOT, prefix='staging-') as temporary:
            stage = Path(temporary) / current
            stage.mkdir(mode=0o700)
            hashes = {}
            for name in EXECUTABLES:
                shutil.copy2(source / name, stage / name)
                hashes[name] = digest(stage / name)
            (stage / 'manifest.json').write_text(json.dumps({'schema': 2, 'version': current, 'sha256': hashes}))
            backup = None
            if target.exists():
                backup = ROOT / (current + '.incomplete-' + str(time.time_ns()))
                target.rename(backup)
            try:
                stage.rename(target)
            except OSError:
                if backup is not None:
                    backup.rename(target)
                raise
        print(f'Installed tested backend at {target}. Activation is separate.')

if __name__ == '__main__':
    main()
