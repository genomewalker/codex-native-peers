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
        for name in backend.EXECUTABLES:
            (release / name).write_bytes(b'test artifact')
            (release / name).chmod(0o700)
            hashes[name] = backend.digest(release / name)
        (release / 'manifest.json').write_text(json.dumps({'schema': 2, 'version': 'test-1', 'sha256': hashes}))
        assert backend.selected() == release / 'codex'
        helper = release / 'codex-code-mode-host'
        helper.rename(release / 'helper.saved')
        assert backend.selected() == backend.APP
        (release / 'helper.saved').rename(helper)
        helper.chmod(0o600)
        assert backend.selected() == backend.APP
        helper.chmod(0o700)
        manifest = release / 'manifest.json'
        manifest.write_text(json.dumps({'version': 'test-1', 'sha256': hashes}))
        assert backend.selected() == backend.APP
        manifest.write_text(json.dumps({'schema': 2, 'version': 'test-1', 'sha256': hashes}))
        with patch.object(backend, 'version', return_value='test-2'):
            assert backend.selected() == backend.APP
        (release / 'codex-peer-worker').write_bytes(b'changed')
        assert backend.selected() == backend.APP
print('PASS: matching build; stock fallback for missing helper, non-executable helper, old manifest, app update, and corruption')
