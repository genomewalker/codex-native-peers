"""Test safe update dispatch without changing the app or login environment."""
import importlib.util
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('backend', Path(__file__).with_name('native-backend.py'))
backend = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backend)
with tempfile.TemporaryDirectory() as temporary:
    backend.ROOT = Path(temporary)
    with patch.object(backend, 'version', return_value='test-1'):
        assert backend.selected() == backend.APP
        release = backend.ROOT / 'test-1'
        release.mkdir()
        hashes = {}
        for name in ('codex', 'codex-peer-worker'):
            (release / name).write_bytes(b'test artifact')
            hashes[name] = backend.digest(release / name)
        (release / 'manifest.json').write_text(json.dumps({'version': 'test-1', 'sha256': hashes}))
        assert backend.selected() == release / 'codex'
        with patch.object(backend, 'version', return_value='test-2'):
            assert backend.selected() == backend.APP
        (release / 'codex-peer-worker').write_bytes(b'changed')
        assert backend.selected() == backend.APP
print('PASS: missing build, matching build, app update, and modified artifact dispatch')
