"""启动脚本剪辑台：python -m script_agent.web --port 8765。只监听本机。"""

from __future__ import annotations

import argparse
import sys
from http.server import ThreadingHTTPServer

from .server import create_app, make_handler

_HOST = "127.0.0.1"
_DEFAULT_PORT = 8765


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m script_agent.web",
        description="脚本剪辑台：短视频脚本 Agent 的本地 Web 工作台。",
    )
    parser.add_argument("--port", type=int, default=_DEFAULT_PORT, help="端口，默认 8765")
    args = parser.parse_args(argv)

    try:
        server = ThreadingHTTPServer((_HOST, args.port), make_handler(create_app()))
    except OSError as exc:
        print(f"无法监听端口 {args.port}：{exc}。可以用 --port 换一个端口。", file=sys.stderr)
        return 1

    print(f"脚本剪辑台已启动：http://{_HOST}:{args.port}（按 Ctrl+C 退出）", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
