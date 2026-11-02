"""批量运行 examples/cases.json 里的真实模型用例，写产物并汇总。

每个用例写到 examples/real/<name>/，包含 result.json、script.md、trace.jsonl、trace.md。
单个用例出错不会中断其他用例；全部跑完后合并 summary.json 与 summary.md。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
# 即使没有 pip install -e .，也优先使用仓库里的源码。
_SRC = ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from script_agent.app import run_once  # noqa: E402
from script_agent.llm import LLMError, OpenAICompatibleLLM  # noqa: E402
from script_agent.registry import FaultPlan  # noqa: E402

CASES_PATH = ROOT / "examples/cases.json"
REAL_DIR = ROOT / "examples/real"
SUMMARY_JSON = REAL_DIR / "summary.json"
SUMMARY_MD = REAL_DIR / "summary.md"

_REQUIRED_ENV = ("LLM_API_KEY", "LLM_MODEL")
_DEFAULT_MAX_STEPS = 10
_DEFAULT_MAX_TOOL_CALLS = 20
_EXIT_OK = 0
_EXIT_NOT_OK = 1
_EXIT_USAGE = 2


class _UsageError(Exception):
    """配置、用例文件或命令行用法有误；main 统一转成退出码 2。"""


def _reconfigure(stream: object) -> None:
    """控制台编码可能容不下一部分字符；改用替换模式，绝不因此崩溃。"""
    reconfigure = getattr(stream, "reconfigure", None)
    if not callable(reconfigure):
        return
    try:
        reconfigure(errors="replace")
    except (ValueError, OSError):
        pass


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_examples",
        description=(
            "按 examples/cases.json 批量运行真实模型用例，"
            "产物写到 examples/real/<name>/ 并生成汇总。"
        ),
    )
    parser.add_argument(
        "--case",
        metavar="NAME",
        help="只运行指定用例（默认运行全部用例）",
    )
    return parser


def _resolve(path_text: str) -> Path:
    path = Path(path_text)
    return path if path.is_absolute() else ROOT / path


def _load_cases(path: Path) -> list[dict]:
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise _UsageError(f"无法读取用例文件：{path}（{exc}）") from None
    except UnicodeDecodeError:
        raise _UsageError(f"用例文件不是 UTF-8 编码：{path}") from None
    except json.JSONDecodeError as exc:
        raise _UsageError(f"用例文件 JSON 错误：{path}（{exc}）") from None
    if not isinstance(payload, list) or not payload:
        raise _UsageError(f"用例文件必须是非空列表：{path}")

    names: set[str] = set()
    for index, case in enumerate(payload, start=1):
        _validate_case(case, index, path)
        name = case["name"]
        if name in names:
            raise _UsageError(f"用例 name 重复：{name}")
        names.add(name)
    return payload


def _validate_case(case: Any, index: int, path: Path) -> None:
    label = f"用例文件第 {index} 项（{path}）"
    if not isinstance(case, dict):
        raise _UsageError(f"{label}必须是 JSON 对象")
    for field in ("name", "input", "data_dir", "covers"):
        if not isinstance(case.get(field), str) or not case[field].strip():
            raise _UsageError(f"{label}缺少有效的 {field}")
    fault = case.get("fault")
    if fault is not None:
        if not isinstance(fault, dict):
            raise _UsageError(f"{label}的 fault 必须是对象或 null")
        if not isinstance(fault.get("tool"), str) or not fault["tool"].strip():
            raise _UsageError(f"{label}的 fault.tool 必须是字符串")
        times = fault.get("times")
        if not isinstance(times, int) or isinstance(times, bool) or times < -1:
            raise _UsageError(f"{label}的 fault.times 必须是 -1 或非负整数")
    expect = case.get("expect")
    if not isinstance(expect, dict):
        raise _UsageError(f"{label}的 expect 必须是对象")
    statuses = expect.get("status")
    if (
        not isinstance(statuses, list)
        or not statuses
        or not all(isinstance(item, str) and item.strip() for item in statuses)
    ):
        raise _UsageError(f"{label}的 expect.status 必须是非空字符串列表")
    must_cite = expect.get("must_cite")
    if not isinstance(must_cite, list) or not all(
        isinstance(item, str) and item.strip() for item in must_cite
    ):
        raise _UsageError(f"{label}的 expect.must_cite 必须是字符串列表")
    forbid_text = expect.get("forbid_text")
    if not isinstance(forbid_text, list) or not all(
        isinstance(item, str) and item.strip() for item in forbid_text
    ):
        raise _UsageError(f"{label}的 expect.forbid_text 必须是字符串列表")


def _select_cases(cases: list[dict], name: str | None) -> list[dict]:
    if name is None:
        return cases
    for case in cases:
        if case["name"] == name:
            return [case]
    available = "、".join(case["name"] for case in cases)
    raise _UsageError(f"没有名为 {name} 的用例；可用用例：{available}")


def _require_model_config() -> str:
    missing = [
        name for name in _REQUIRED_ENV if not os.environ.get(name, "").strip()
    ]
    if missing:
        raise _UsageError(
            f"缺少模型配置：{'、'.join(missing)}。"
            "请在 .env 或环境变量中设置后重试。"
        )
    return os.environ["LLM_MODEL"].strip()


def _build_llm(model_name: str) -> OpenAICompatibleLLM:
    try:
        return OpenAICompatibleLLM(
            model_name,
            base_url=os.environ.get("LLM_BASE_URL", "").strip() or None,
            api_key=os.environ["LLM_API_KEY"].strip(),
        )
    except LLMError as exc:
        raise _UsageError(str(exc)) from None


def _read_trace(out_dir: Path) -> list[dict]:
    """读 trace.jsonl；文件缺失或个别行损坏时返回已读到的记录，绝不抛异常。"""
    try:
        text = (out_dir / "trace.jsonl").read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    records: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            records.append(record)
    return records


def _path_of(records: list[dict]) -> list[str]:
    return [
        str(record["action"])
        for record in records
        if record.get("type") == "step" and record.get("action")
    ]


def _total_tokens(records: list[dict]) -> int:
    """优先取 run_end 的统计；缺失时按 step 的 usage 求和。"""
    for record in reversed(records):
        if record.get("type") == "run_end":
            value = record.get("total_tokens")
            if isinstance(value, int) and not isinstance(value, bool):
                return value
            return 0
    total = 0
    for record in records:
        if record.get("type") != "step":
            continue
        usage = record.get("usage")
        if not isinstance(usage, dict):
            continue
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            value = usage.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                total += value
                break
    return total


def _summary_item(case: dict, result: Any, model_name: str) -> dict:
    records = _read_trace(REAL_DIR / case["name"])
    return {
        "name": case["name"],
        "status": result.status,
        "status_ok": result.status in case["expect"]["status"],
        "path": _path_of(records),
        "covers": case["covers"],
        "model": model_name,
        "total_tokens": _total_tokens(records),
    }


def _error_item(case: dict, model_name: str, exc: Exception) -> dict:
    """用例抛异常时也留一条汇总，便于定位；不伪造任何产物。"""
    records = _read_trace(REAL_DIR / case["name"])
    return {
        "name": case["name"],
        "status": "error",
        "status_ok": False,
        "path": _path_of(records),
        "covers": case["covers"],
        "model": model_name,
        "total_tokens": _total_tokens(records),
        "error": f"{type(exc).__name__}: {exc}",
    }


def _run_case(case: dict, llm: OpenAICompatibleLLM, model_name: str) -> dict:
    name = case["name"]
    input_path = _resolve(case["input"])
    if not input_path.is_file():
        raise FileNotFoundError(f"输入文件不存在：{input_path}")
    raw_request = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(raw_request, dict):
        raise ValueError(f"输入文件必须是 JSON 对象：{input_path}")

    fault_spec = case.get("fault")
    fault = FaultPlan(tool=fault_spec["tool"], times=fault_spec["times"]) if fault_spec else None

    result = run_once(
        raw_request,
        llm,
        mode="real",
        model_name=model_name,
        data_dir=_resolve(case["data_dir"]),
        fault=fault,
        max_steps=_DEFAULT_MAX_STEPS,
        max_tool_calls=_DEFAULT_MAX_TOOL_CALLS,
        out_dir=REAL_DIR / name,
    )
    return _summary_item(case, result, model_name)


def _merge_summary(cases: list[dict], new_items: list[dict]) -> list[dict]:
    """按用例文件顺序合并旧汇总；只跑 --case 时保留其他用例的旧记录。"""
    merged: dict[str, dict] = {}
    if SUMMARY_JSON.exists():
        try:
            previous = json.loads(SUMMARY_JSON.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            previous = []
        if isinstance(previous, list):
            for item in previous:
                if isinstance(item, dict) and isinstance(item.get("name"), str):
                    merged[item["name"]] = item
    for item in new_items:
        merged[item["name"]] = item

    order = {case["name"]: index for index, case in enumerate(cases)}
    return sorted(
        merged.values(),
        key=lambda item: order.get(str(item.get("name")), len(order)),
    )


def _cell(value: Any) -> str:
    flat = " ".join(str(value).split())
    return flat.replace("|", "\\|") or "—"


def _summary_rows(items: list[dict]) -> list[str]:
    rows = [
        "| 用例 | 状态 | 符合预期 | 动作路径 | 模型 | tokens | 覆盖 | 备注 |",
        "|---|---|---|---|---|---:|---|---|",
    ]
    for item in items:
        rows.append(
            "| "
            + " | ".join(
                [
                    _cell(item.get("name")),
                    _cell(item.get("status")),
                    "是" if item.get("status_ok") else "否",
                    _cell(" -> ".join(item.get("path") or []) or "—"),
                    _cell(item.get("model")),
                    _cell(item.get("total_tokens")),
                    _cell(item.get("covers")),
                    _cell(item.get("error") or "—"),
                ]
            )
            + " |"
        )
    return rows


def _write_summary(cases: list[dict], items: list[dict]) -> None:
    REAL_DIR.mkdir(parents=True, exist_ok=True)
    SUMMARY_JSON.write_text(
        json.dumps(items, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# 真实运行汇总",
        "",
        f"共 {len(items)} 个用例；本文件由 `scripts/run_examples.py` 生成。",
        "",
        *_summary_rows(items),
    ]
    SUMMARY_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _print_case_result(index: int, total: int, item: dict) -> None:
    mark = "符合预期" if item["status_ok"] else "不符合预期"
    path = " -> ".join(item["path"]) or "（无动作）"
    print(
        f"[{index}/{total}] {item['name']} 结束：status={item['status']}，"
        f"{mark}，tokens={item['total_tokens']}，路径={path}",
        flush=True,
    )


def _print_final_table(items: list[dict]) -> None:
    print("", flush=True)
    print("运行结果：", flush=True)
    for row in _summary_rows(items):
        print(row, flush=True)


def main(argv: list[str] | None = None) -> int:
    _reconfigure(sys.stdout)
    _reconfigure(sys.stderr)
    args = _build_parser().parse_args(argv)

    try:
        load_dotenv(ROOT / ".env")
        model_name = _require_model_config()
        cases = _load_cases(CASES_PATH)
        selected = _select_cases(cases, args.case)
        llm = _build_llm(model_name)
    except _UsageError as exc:
        print(str(exc), file=sys.stderr)
        return _EXIT_USAGE

    total = len(selected)
    print(f"准备运行 {total} 个用例，模型：{model_name}", flush=True)

    items: list[dict] = []
    for index, case in enumerate(selected, start=1):
        print(f"[{index}/{total}] {case['name']} 开始…", flush=True)
        try:
            item = _run_case(case, llm, model_name)
        except Exception as exc:  # 单个用例失败不能中断其他用例
            item = _error_item(case, model_name, exc)
            print(
                f"[{index}/{total}] {case['name']} 异常："
                f"{type(exc).__name__}: {exc}",
                file=sys.stderr,
                flush=True,
            )
        items.append(item)
        _print_case_result(index, total, item)

    merged = _merge_summary(cases, items)
    _write_summary(cases, merged)
    _print_final_table(merged)
    print(
        f"\n已写入：{SUMMARY_JSON.resolve()}\n"
        f"已写入：{SUMMARY_MD.resolve()}",
        flush=True,
    )

    if any(not item.get("status_ok") for item in items):
        return _EXIT_NOT_OK
    return _EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
