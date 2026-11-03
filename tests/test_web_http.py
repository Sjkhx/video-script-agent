import io
import json
import socket
import threading
import time
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from script_agent.web.server import create_app, make_handler
from web_helpers import ROOT, Client


class FakeSocket:
    """给 BaseHTTPRequestHandler 用的内存 socket。"""

    def __init__(self, raw):
        self.reader = io.BytesIO(raw)
        self.sent = bytearray()

    def makefile(self, mode, *args, **kwargs):
        return self.reader

    def sendall(self, data):
        self.sent.extend(data)

    def shutdown(self, *args):
        pass

    def close(self):
        pass


def exchange(app, raw):
    fake = FakeSocket(raw)
    make_handler(app)(fake, ("127.0.0.1", 1), None)
    head, _, body = bytes(fake.sent).partition(b"\r\n\r\n")
    lines = head.decode("latin-1").split("\r\n")
    headers = {k.lower(): v.strip() for k, v in (line.split(":", 1) for line in lines[1:])}
    return int(lines[0].split()[1]), headers, body


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("LLM_MODEL", "")
    return create_app(root=ROOT, runs_dir=tmp_path)


def request(method, path, body=b"", headers=()):
    lines = [f"{method} {path} HTTP/1.1", "Host: 127.0.0.1:8765", "Connection: close", *headers]
    if body:
        lines += ["Content-Type: application/json", f"Content-Length: {len(body)}"]
    return ("\r\n".join(lines) + "\r\n\r\n").encode("utf-8") + body


def test_get_json_roundtrip(app):
    status, headers, body = exchange(app, request("GET", "/api/meta"))
    assert status == 200 and headers["content-type"].startswith("application/json")
    assert json.loads(body)["real_available"] is False
    assert "default-src 'self'" in headers["content-security-policy"]
    assert int(headers["content-length"]) == len(body)


def test_post_body_is_read(app):
    status, _, body = exchange(app, request("POST", "/api/verify", b"{bad"))
    assert status == 400 and json.loads(body)["detail"]["code"] == "INVALID_JSON"


def test_oversize_body_is_rejected_without_reading(app):
    raw = ("POST /api/verify HTTP/1.1\r\nHost: 127.0.0.1:8765\r\nConnection: close\r\nContent-Type: application/json\r\nContent-Length: 2000000\r\n\r\n").encode()
    status, _, body = exchange(app, raw)
    assert status == 413 and json.loads(body)["detail"]["code"] == "BODY_TOO_LARGE"


def test_invalid_content_length_is_rejected(app):
    raw = ("POST /api/verify HTTP/1.1\r\nHost: 127.0.0.1:8765\r\nConnection: close\r\nContent-Type: application/json\r\nContent-Length: abc\r\n\r\n").encode()
    status, _, body = exchange(app, raw)
    assert status == 400 and json.loads(body)["detail"]["code"] == "INVALID_REQUEST"


def test_static_file_types(app):
    status, headers, body = exchange(app, request("GET", "/"))
    assert status == 200 and headers["content-type"].startswith("text/html") and b"<title>" in body


def test_sse_response_has_no_content_length(app):
    client = Client(app)
    run_id = client.post("/api/runs", json={"request": {"topic": "字幕", "target_duration_sec": 30}, "mode": "mock", "mock_script": "01_normal", "data_set": "default"}).json()["run_id"]
    deadline = time.time() + 15
    while client.get(f"/api/runs/{run_id}").json()["status"] == "running" and time.time() < deadline:
        time.sleep(0.05)
    status, headers, body = exchange(app, request("GET", f"/api/runs/{run_id}/events"))
    assert status == 200 and headers["content-type"].startswith("text/event-stream")
    assert "content-length" not in headers
    assert b"event: end" in body


def test_client_disconnect_closes_stream(app):
    class Broken(FakeSocket):
        def sendall(self, data):
            raise BrokenPipeError()

    make_handler(app)(Broken(request("GET", "/api/meta")), ("127.0.0.1", 1), None)  # 不能抛异常


def loopback_available():
    server = socket.socket()
    try:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        probe = socket.socket()
        probe.settimeout(2)
        result = probe.connect_ex(server.getsockname())
        probe.close()
        return result == 0
    except OSError:
        return False
    finally:
        server.close()


@pytest.mark.skipif(not loopback_available(), reason="当前环境不允许本机回环连接")
def test_real_socket_roundtrip(app):
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(f"http://127.0.0.1:{server.server_address[1]}/api/meta", timeout=5) as response:
            assert response.status == 200 and json.load(response)["real_available"] is False
    finally:
        server.shutdown()
        server.server_close()
