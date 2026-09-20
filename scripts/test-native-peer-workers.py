"""Exercise real native worker processes without touching live sessions."""
import json
import pathlib
import select
import subprocess
import sys
import tempfile


def receive(process):
    assert select.select([process.stdout], [], [], 5)[0], "worker response timed out"
    return json.loads(process.stdout.readline())


def send(process, **request):
    process.stdin.write(json.dumps(request) + "\n")
    process.stdin.flush()


with tempfile.TemporaryDirectory(prefix="peer-workers-") as home:
    workers = []
    try:
        for name in ("a", "b", "c"):
            process = subprocess.Popen(
                [sys.argv[1], name, home, home],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1,
            )
            workers.append(process)
            assert receive(process) == {"ready": True}
        a, b, c = workers
        send(a, id="list", op="list")
        listed = receive(a)
        assert {peer["name"] for peer in listed["result"]} == {"codex-b", "codex-c"}
        send(a, id="send", op="send", recipient="codex-b", content="request")
        assert receive(a) == {"id": "send", "result": "sent"}
        message = receive(b)
        assert message == {"event": "message", "sender": "codex-a", "session": "a", "content": "request"}
        send(b, id="reply", op="send", recipient=message["sender"], content="response")
        assert receive(b) == {"id": "reply", "result": "sent"}
        assert receive(a)["content"] == "response"
        assert not select.select([c.stdout], [], [], 0.1)[0], "message leaked to third task"
        send(b, op="shutdown")
        assert b.wait(timeout=5) == 0
        send(a, id="closed", op="send", recipient="codex-b", content="must fail")
        assert "error" in receive(a)
        for process in (a, c):
            process.stdin.close()
            assert process.wait(timeout=5) == 0
        assert not list((pathlib.Path(home) / ".claude/sessions").iterdir()), "registry was not cleaned"
        print("PASS: three workers, PID discovery, targeted delivery, reply, isolation, closed recipient, EOF cleanup")
    finally:
        for process in workers:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)

