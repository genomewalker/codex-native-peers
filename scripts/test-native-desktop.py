"""Smoke-test independent ephemeral app-server tasks without model requests."""
import json
import os
import pathlib
import select
import subprocess
import sys
import tempfile
import time

with tempfile.TemporaryDirectory(prefix="codex-native-smoke-") as home:
    process = subprocess.Popen([sys.argv[1], "app-server"],
        env={**os.environ, "CODEX_HOME": home, "CODEX_NATIVE_PEER_DIR": "/tmp"},
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    def rpc(identifier, method, params):
        process.stdin.write(json.dumps({"id": identifier, "method": method, "params": params}) + "\n")
        process.stdin.flush()
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            assert select.select([process.stdout], [], [], 30)[0], "RPC timeout"
            value = json.loads(process.stdout.readline())
            if value.get("id") == identifier:
                assert "error" not in value, value
                return value["result"]
        raise RuntimeError("RPC timeout")
    try:
        rpc(1, "initialize", {"clientInfo": {"name": "native-smoke", "version": "1"}})
        process.stdin.write('{"method":"initialized"}\n')
        process.stdin.flush()
        ids = [rpc(i, "thread/start", {"cwd": home, "ephemeral": True})["thread"]["id"] for i in (2, 3)]
        records = []
        for path in (pathlib.Path.home() / ".claude/sessions").glob("*.json"):
            try:
                value = json.loads(path.read_text())
                if value.get("sessionId") in ids:
                    records.append(value)
            except (OSError, ValueError):
                pass
        assert len(records) == 2, f"expected two workers, found {len(records)}"
        assert len({r["pid"] for r in records}) == 2, "tasks share a worker"
        print("PASS: app-server starts two tasks with separate native worker PIDs")
    finally:
        process.stdin.close()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.terminate()
            process.wait(timeout=5)

