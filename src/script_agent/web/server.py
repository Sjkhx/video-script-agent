"""HTTP 层：路由集中在不依赖 socket 的 dispatch()，Handler 只负责读写。"""

from __future__ import annotations

import json
import re
import traceback
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping
from urllib.parse import parse_qs, unquote, urlsplit

from dotenv import load_dotenv
from pydantic import ValidationError

from ..llm import LLMClient
from .service import ApiError, WebService

MAX_BODY_BYTES = 1024 * 1024

_ALLOWED_HOSTS = {"127.0.0.1", "localhost", "[::1]"}
_SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self' data:; base-uri 'none'; "
        "form-action 'none'; frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
}
_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
}
_NETWORK_ERRORS = (BrokenPipeError, ConnectionError, TimeoutError)


@dataclass
class Response:
    status: int
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes | Iterator[bytes] = b""


def _json_response(status: int, payload: Any) -> Response:
    return Response(
        status,
        {"Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store"},
        json.dumps(payload, ensure_ascii=False).encode("utf-8"),
    )


def _error_response(status: int, code: str, message: str, **extra: object) -> Response:
    return _json_response(
        status, {"detail": {"code": code, "message": message, **extra}}
    )


def _host_name(host: str) -> str:
    """去掉端口；IPv6 字面量保留方括号。"""
    value = host.strip().lower()
    if value.startswith("["):
        return value[: value.find("]") + 1]
    return value.rsplit(":", 1)[0]


def _validation_message(exc: ValidationError) -> str:
    details = []
    for error in exc.errors():
        location = ".".join(str(part) for part in error["loc"]) or "请求"
        details.append(f"{location}: {error['msg']}")
    return "请求不合法：" + "；".join(details)


def _last_event_id(value: str | None) -> int | None:
    try:
        number = int(value) if value is not None else None
    except ValueError:
        return None
    return number if number is not None and number >= 0 else None


class WebApp:
    def __init__(self, service: WebService, static_dir: Path) -> None:
        self._service = service
        # 只有这张表里的路径能被访问，绝不把 URL 拼成文件路径。
        self._static: dict[str, Path] = {}
        for path in sorted(static_dir.rglob("*")):
            if path.is_file() and path.suffix in _CONTENT_TYPES:
                self._static["/" + path.relative_to(static_dir).as_posix()] = path
        if "/index.html" in self._static:
            self._static["/"] = self._static["/index.html"]
        self._routes: list[tuple[str, re.Pattern[str], Callable[..., Response]]] = [
            ("GET", re.compile(r"/api/meta"), self._meta),
            ("GET", re.compile(r"/api/materials"), self._materials),
            ("GET", re.compile(r"/api/examples"), self._examples),
            ("GET", re.compile(r"/api/examples/([^/]+)"), self._example),
            ("GET", re.compile(r"/api/runs"), self._runs),
            ("POST", re.compile(r"/api/runs"), self._start_run),
            ("GET", re.compile(r"/api/runs/([^/]+)"), self._run),
            ("GET", re.compile(r"/api/runs/([^/]+)/events"), self._events),
            ("POST", re.compile(r"/api/verify"), self._verify),
        ]

    def dispatch(
        self,
        method: str,
        target: str,
        headers: Mapping[str, str] | None = None,
        body: bytes = b"",
    ) -> Response:
        lowered = {str(k).lower(): str(v) for k, v in (headers or {}).items()}
        try:
            response = self._handle(method, target, lowered, body)
        except ApiError as exc:
            response = _error_response(exc.status, exc.code, exc.message, **exc.extra)
        except ValidationError as exc:
            response = _error_response(422, "INVALID_REQUEST", _validation_message(exc))
        except Exception:
            traceback.print_exc()
            response = _error_response(500, "INTERNAL_ERROR", "服务内部错误。")
        response.headers.update(_SECURITY_HEADERS)
        return response

    def too_large(self) -> Response:
        response = _error_response(
            413, "BODY_TOO_LARGE", f"请求体不能超过 {MAX_BODY_BYTES} 字节。"
        )
        response.headers.update(_SECURITY_HEADERS)
        return response

    def bad_length(self) -> Response:
        response = _error_response(400, "INVALID_REQUEST", "Content-Length 不合法。")
        response.headers.update(_SECURITY_HEADERS)
        return response

    def _handle(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> Response:
        host = headers.get("host", "")
        if _host_name(host) not in _ALLOWED_HOSTS:
            raise ApiError(400, "BAD_HOST", "只接受来自本机地址的请求。")
        if method == "POST":
            self._check_post(host, headers, body)

        parts = urlsplit(target)
        path_exists = False
        for route_method, pattern, handler in self._routes:
            match = pattern.fullmatch(parts.path)
            if match is None:
                continue
            path_exists = True
            if route_method == method:
                params = [unquote(group) for group in match.groups()]
                return handler(*params, query=parts.query, headers=headers, body=body)
        if path_exists:
            return _error_response(405, "METHOD_NOT_ALLOWED", "不支持这个请求方法。")
        if method == "GET" and parts.path in self._static:
            return self._static_file(self._static[parts.path])
        raise ApiError(404, "NOT_FOUND", "没有这个地址。")

    @staticmethod
    def _check_post(host: str, headers: dict[str, str], body: bytes) -> None:
        if len(body) > MAX_BODY_BYTES:
            raise ApiError(413, "BODY_TOO_LARGE", f"请求体不能超过 {MAX_BODY_BYTES} 字节。")
        origin = headers.get("origin")
        if origin is not None and urlsplit(origin).netloc.lower() != host.strip().lower():
            raise ApiError(403, "BAD_ORIGIN", "不接受来自其他网站的请求。")
        content_type = headers.get("content-type", "").split(";")[0].strip().lower()
        if content_type != "application/json":
            raise ApiError(415, "UNSUPPORTED_MEDIA_TYPE", "请求必须是 application/json。")

    @staticmethod
    def _static_file(path: Path) -> Response:
        return Response(
            200,
            {"Content-Type": _CONTENT_TYPES[path.suffix], "Cache-Control": "no-store"},
            path.read_bytes(),
        )

    @staticmethod
    def _json_body(body: bytes) -> Any:
        try:
            return json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise ApiError(400, "INVALID_JSON", "请求体不是合法的 JSON。") from None

    # -- 路由处理 -----------------------------------------------------------

    def _meta(self, **_: object) -> Response:
        return _json_response(200, self._service.meta())

    def _materials(self, *, query: str, **_: object) -> Response:
        data_set = parse_qs(query).get("data_set", ["default"])[0]
        return _json_response(200, self._service.materials(data_set))

    def _examples(self, **_: object) -> Response:
        return _json_response(200, self._service.examples())

    def _example(self, name: str, **_: object) -> Response:
        return _json_response(200, self._service.example(name))

    def _runs(self, **_: object) -> Response:
        return _json_response(200, self._service.list_runs())

    def _start_run(self, *, body: bytes, **_: object) -> Response:
        return _json_response(202, self._service.start_run(self._json_body(body)))

    def _run(self, run_id: str, **_: object) -> Response:
        return _json_response(200, self._service.run(run_id))

    def _events(self, run_id: str, *, headers: dict[str, str], **_: object) -> Response:
        stream = self._service.run_events(
            run_id, _last_event_id(headers.get("last-event-id"))
        )
        return Response(
            200,
            {
                "Content-Type": "text/event-stream; charset=utf-8",
                "Cache-Control": "no-store",
            },
            stream,
        )

    def _verify(self, *, body: bytes, **_: object) -> Response:
        return _json_response(200, self._service.verify(self._json_body(body)))


def create_app(
    root: Path | None = None,
    runs_dir: Path | None = None,
    llm_factory: Callable[[], tuple[LLMClient, str]] | None = None,
) -> WebApp:
    root = Path(root) if root is not None else Path(__file__).resolve().parents[3]
    load_dotenv(root / ".env")
    service = WebService(
        root,
        Path(runs_dir) if runs_dir is not None else root / "runs" / "web",
        llm_factory,
    )
    return WebApp(service, Path(__file__).resolve().parent / "static")


def make_handler(app: WebApp) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "ScriptAgentWeb"
        sys_version = ""

        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            self._respond(
                app.dispatch(self.command, self.path, dict(self.headers.items()))
            )

        def do_POST(self) -> None:
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = -1
            if length > MAX_BODY_BYTES or length < 0:
                # 不读请求体，直接断开，避免超大或长度非法的请求占用内存。
                self.close_connection = True
                self._respond(
                    app.too_large() if length > 0 else app.bad_length(), close=True
                )
                return
            body = self.rfile.read(length) if length else b""
            self._respond(
                app.dispatch(self.command, self.path, dict(self.headers.items()), body)
            )

        def _respond(self, response: Response, *, close: bool = False) -> None:
            streaming = not isinstance(response.body, bytes)
            try:
                self.send_response(response.status)
                for name, value in response.headers.items():
                    self.send_header(name, value)
                if streaming or close:
                    self.send_header("Connection", "close")
                    self.close_connection = True
                if not streaming:
                    self.send_header("Content-Length", str(len(response.body)))
                self.end_headers()
                if streaming:
                    for chunk in response.body:
                        self.wfile.write(chunk)
                        self.wfile.flush()
                else:
                    self.wfile.write(response.body)
                    self.wfile.flush()
            except _NETWORK_ERRORS:
                # 客户端已断开：结束这个连接，不影响正在运行的 Agent。
                self.close_connection = True
            finally:
                if streaming:
                    response.body.close()

    return Handler
