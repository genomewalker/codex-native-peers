"""Reproducible candidate build; never modifies or restarts the installed app."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

def run(*args, cwd=ROOT):
    subprocess.run(args, cwd=cwd, check=True)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('version')
    parser.add_argument('--prepare-only', action='store_true')
    args = parser.parse_args()
    catalog = json.loads((ROOT / 'compatibility.json').read_text())
    entry = catalog['releases'].get(args.version)
    if not entry:
        parser.error('No reviewed patch exists for this exact version')
    checkout = ROOT / 'upstream'
    if checkout.exists():
        parser.error('upstream already exists; preserve it and use a fresh checkout directory')
    run('git', 'init', str(checkout))
    run('git', 'remote', 'add', 'origin', catalog['repository'], cwd=checkout)
    run('git', 'fetch', '--depth=1', 'origin', entry['commit'], cwd=checkout)
    run('git', 'checkout', '--detach', 'FETCH_HEAD', cwd=checkout)
    actual = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=checkout, text=True).strip()
    if actual != entry['commit']:
        raise RuntimeError('Upstream commit mismatch')
    patch = ROOT / entry['patch']
    run('git', 'apply', '--check', str(patch), cwd=checkout)
    run('git', 'apply', str(patch), cwd=checkout)
    if args.prepare_only:
        print('PASS: exact upstream commit and patch application')
        return
    rust = checkout / 'codex-rs'
    run('just', 'test', '-p', 'codex-peer-messaging', cwd=rust)
    run('cargo', 'build', '--release', '--locked', '-j', '4', '-p', 'codex-cli',
        '-p', 'codex-peer-messaging', '-p', 'codex-code-mode-host', '--bin', 'codex', '--bin', 'codex-peer-worker', '--bin', 'codex-code-mode-host', cwd=rust)
    run(str(rust / 'target/release/codex-code-mode-host'), '--help')
    binary = rust / 'target/release/codex'
    worker = binary.with_name('codex-peer-worker')
    observed = subprocess.check_output([str(binary), '--version'], text=True).strip()
    if observed != 'codex-cli ' + args.version:
        raise RuntimeError('Built version mismatch')
    for test, artifact in [('test-native-peer-workers.py', worker), ('test-native-desktop.py', binary)]:
        run(sys.executable, str(ROOT / 'scripts' / test), str(artifact))
    run(sys.executable, str(ROOT / 'scripts/test-native-backend.py'))
    print('PASS: candidate built and automated checks passed; not installed or published')

if __name__ == '__main__':
    main()
