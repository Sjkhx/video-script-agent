"""运行管理：后台线程跑 Agent，记录供 SSE 读取；结束后一律以磁盘产物为准。"""

from __future__ import annotations

import json
import os
import re
import secrets
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterator

from ..app import run_once
from ..llm import LLMClient
from ..registry import FaultPlan
from ..trace import _redact_text

RUN_ID_PATTERN = re.compile(r"\d{8}-\d{6}-[0-9a-f]{6}")

_POLL_SEC = 0.15
_PING_SEC = 15.0
_LIST_LIMIT = 50
_INTERRUPTED_MESSAGE = "运行被中断（服务在运行结束前退出）。"


class RunBusy(Exception):
    """已有运行在进行；单用户工具同一时间只跑一个。"""


@dataclass
class RunSpec:
    raw_request: dict
    llm: LLMClient
    mode: str
    model_name: str
    data_set: str
    data_dir: Path
    fault: FaultPlan | None
    max_steps: int
    max_tool_calls: int


@dataclass
class _ActiveRun:
    run_id: str
    records: list[dict] = field(default_factory=list)


def _read_json(path: Path) -> dict | None:
    """读 JSON 对象；文件缺失或损坏时返回 None，不向上抛。"""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def read_trace(folder: Path) -> list[dict]:
    """读 trace.jsonl；个别行损坏时跳过，保留其余记录。"""
    records: list[dict] = []
    for line in (_read_text(folder / "trace.jsonl") or "").splitlines():
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if isinstance(record, dict):
            records.append(record)
    return records


def _sse(event: str, data: dict, event_id: int | None = None) -> bytes:
    lines = [] if event_id is None else [f"id: {event_id}"]
    lines += [f"event: {event}", f"data: {json.dumps(data, ensure_ascii=False)}", "", ""]
    return "\n".join(lines).encode("utf-8")


def _redacted_error(exc: Exception) -> str:
    """异常文字可能带出密钥，写盘和返回前都要脱敏。"""
    key = os.environ.get("LLM_API_KEY", "").strip()
    return _redact_text(f"{type(exc).__name__}: {exc}", (key,))


class RunManager:
    """持有唯一的活动运行；活动结束后状态全部从 runs_dir 读取，重启服务也不丢。"""

    def __init__(self, runs_dir: Path) -> None:
        self._runs_dir = Path(runs_dir)
        self._lock = threading.Lock()
        self._active: _ActiveRun | None = None

    def start(self, spec: RunSpec) -> str:
        with self._lock:
            if self._active is not None:
                raise RunBusy()
            now = datetime.now().astimezone()
            run_id = f"{now.strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(3)}"
            folder = self._runs_dir / run_id
            folder.mkdir(parents=True)
            meta = {
                "run_id": run_id,
                "created_at": now.isoformat(timespec="seconds"),
                "request": spec.raw_request,
                "mode": spec.mode,
                "model": spec.model_name,
                "data_set": spec.data_set,
                "fault": (
                    {"tool": spec.fault.tool, "times": spec.fault.times}
                    if spec.fault
                    else None
                ),
                "max_steps": spec.max_steps,
            }
            (folder / "meta.json").write_text(
                json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            active = _ActiveRun(run_id)
            self._active = active
        threading.Thread(target=self._work, args=(active, spec), daemon=True).start()
        return run_id

    def _work(self, active: _ActiveRun, spec: RunSpec) -> None:
        folder = self._runs_dir / active.run_id
        try:
            run_once(
                spec.raw_request,
                spec.llm,
                mode=spec.mode,
                model_name=spec.model_name,
                data_dir=spec.data_dir,
                fault=spec.fault,
                max_steps=spec.max_steps,
                max_tool_calls=spec.max_tool_calls,
                out_dir=folder,
                listener=active.records.append,
            )
        except Exception as exc:
            # 崩溃也要留下记录，否则这次运行会一直被判成“中断”。
            try:
                (folder / "error.txt").write_text(
                    _redacted_error(exc), encoding="utf-8"
                )
            except OSError:
                pass
        finally:
            with self._lock:
                self._active = None

    def _folder(self, run_id: str) -> Path | None:
        """运行 ID 先过正则，绝不把未校验的字符串拼进路径。"""
        if not RUN_ID_PATTERN.fullmatch(run_id):
            return None
        folder = self._runs_dir / run_id
        return folder if (folder / "meta.json").is_file() else None

    def exists(self, run_id: str) -> bool:
        return self._folder(run_id) is not None

    def _active_records(self, run_id: str) -> list[dict] | None:
        with self._lock:
            if self._active is None or self._active.run_id != run_id:
                return None
            return list(self._active.records)

    @staticmethod
    def _final_state(folder: Path) -> tuple[str, dict | None, str | None]:
        result = _read_json(folder / "result.json")
        if result is not None:
            return str(result.get("status")), result, None
        error = _read_text(folder / "error.txt")
        return "crashed", None, error or _INTERRUPTED_MESSAGE

    def snapshot(self, run_id: str) -> dict | None:
        folder = self._folder(run_id)
        if folder is None:
            return None
        meta = _read_json(folder / "meta.json") or {}
        records = self._active_records(run_id)
        if records is not None:
            return {
                "run_id": run_id,
                "status": "running",
                "meta": meta,
                "result": None,
                "records": records,
                "markdown": None,
                "error": None,
            }
        status, result, error = self._final_state(folder)
        return {
            "run_id": run_id,
            "status": status,
            "meta": meta,
            "result": result,
            "records": read_trace(folder),
            "markdown": _read_text(folder / "script.md"),
            "error": error,
        }

    def list_runs(self) -> list[dict]:
        if not self._runs_dir.is_dir():
            return []
        names = [
            path.name
            for path in self._runs_dir.iterdir()
            if RUN_ID_PATTERN.fullmatch(path.name)
        ]
        items: list[dict] = []
        for name in sorted(names, reverse=True)[:_LIST_LIMIT]:
            folder = self._folder(name)
            if folder is None:
                continue
            meta = _read_json(folder / "meta.json") or {}
            if self._active_records(name) is not None:
                status, result = "running", None
            else:
                status, result, _ = self._final_state(folder)
            request = meta.get("request") if isinstance(meta.get("request"), dict) else {}
            items.append(
                {
                    "run_id": name,
                    "created_at": meta.get("created_at"),
                    "topic": request.get("topic"),
                    "status": status,
                    "mode": meta.get("mode"),
                    "model": meta.get("model"),
                    "total_duration_sec": (result or {}).get("total_duration_sec"),
                }
            )
        return items

    def events(self, run_id: str, last_event_id: int | None = None) -> Iterator[bytes]:
        """先跟随活动运行，结束后从磁盘补发剩余记录和最终结果。"""
        index = 0 if last_event_id is None else last_event_id + 1
        last_sent = time.monotonic()
        while True:
            records = self._active_records(run_id)
            if records is None:
                break
            batch = records[index:]
            for record in batch:
                yield _sse("record", record, index)
                index += 1
            if batch:
                last_sent = time.monotonic()
                continue
            if time.monotonic() - last_sent >= _PING_SEC:
                yield b": ping\n\n"
                last_sent = time.monotonic()
            time.sleep(_POLL_SEC)

        folder = self._runs_dir / run_id
        for position, record in enumerate(read_trace(folder)):
            if position >= index:
                yield _sse("record", record, position)
        _, result, error = self._final_state(folder)
        if result is not None:
            yield _sse("result", result)
        else:
            yield _sse("fatal", {"message": error})
        yield _sse("end", {})
