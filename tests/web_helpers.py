"""Web 测试辅助：直接调 dispatch，不走 socket。"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_dumps = json.dumps
_loads = json.loads


class Reply:
    def __init__(self, response):
        self.status_code = response.status
        self.headers = {k.lower(): v for k, v in response.headers.items()}
        body = response.body
        self.content = body if isinstance(body, bytes) else b"".join(body)
        self.text = self.content.decode("utf-8")

    def json(self):
        return _loads(self.text)


class Client:
    HOST = {"Host": "127.0.0.1:8765"}

    def __init__(self, app):
        self.app = app

    def get(self, target, headers=None):
        return Reply(self.app.dispatch("GET", target, {**self.HOST, **(headers or {})}))

    def post(self, target, json=None, headers=None, raw=None):
        body = raw if raw is not None else _dumps(json, ensure_ascii=False).encode("utf-8")
        merged = {**self.HOST, "Content-Type": "application/json", **(headers or {})}
        return Reply(self.app.dispatch("POST", target, merged, body))


def parse_events(text):
    events = []
    for block in text.split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line and not line.startswith(":"))
        if "event" in fields:
            events.append(fields)
    return events
