"""命令行入口：读需求、选模型（真实或离线脚本）、跑一次并写产物。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from .app import run_once
from .llm import LLMError, OpenAICompatibleLLM, ScriptedLLM
from .models import AgentResult, normalize_request
from .registry import FaultPlan

_FAULT_TOOLS = ("search_materials", "estimate_duration", "check_rules")
_OVERRIDE_FIELDS = {
    "topic": "topic",
    "audience": "audience",
    "platform": "platform",
    "target": "target_duration_sec",
    "style": "style",
}
_EXIT_OK = 0
_EXIT_NOT_DONE = 1
_EXIT_USAGE = 2
_DEFAULT_MAX_TOOL_CALLS = 20
_MOCK_MODEL_NAME = "scripted"
_REQUIRED_ENV = ("LLM_API_KEY", "LLM_MODEL")
_OUTPUT_FILES = ("result.json", "script.md", "trace.jsonl", "trace.md")


def _positive_int(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"必须是整数：{text}") from None
    if value < 1:
        raise argparse.ArgumentTypeError(f"必须大于等于 1：{text}")
    return value


def _times_value(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"必须是整数：{text}") from None
    if value < -1:
        raise argparse.ArgumentTypeError(f"只能是 -1 或非负整数：{text}")
    return value


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="script_agent",
        description="短视频脚本 Agent：模型决策，工具把关，输出可编辑脚本和运行记录。",
    )
    parser.add_argument("--input", metavar="PATH", help="需求 JSON 文件")
    parser.add_argument("--topic", help="覆盖需求里的主题")
    parser.add_argument("--audience", help="覆盖需求里的受众")
    parser.add_argument("--platform", help="覆盖需求里的平台")
    parser.add_argument(
        "--target", metavar="SEC", help="覆盖需求里的目标时长（秒）"
    )
    parser.add_argument("--style", help="覆盖需求里的风格")
    parser.add_argument(
        "--data-dir",
        metavar="PATH",
        default="data",
        help="素材与规则目录，默认 data",
    )
    parser.add_argument(
        "--fail-tool",
        choices=_FAULT_TOOLS,
        help="给指定业务工具注入故障",
    )
    parser.add_argument(
        "--fail-times",
        metavar="N",
        type=_times_value,
        default=1,
        help="故障注入次数，默认 1；-1 表示一直失败",
    )
    parser.add_argument(
        "--max-steps",
        metavar="N",
        type=_positive_int,
        default=10,
        help="模型决策轮数上限，默认 10",
    )
    parser.add_argument(
        "--out-dir",
        metavar="PATH",
        help="产物目录，默认 runs/<YYYYmmdd-HHMMSS>",
    )
    parser.add_argument(
        "--mock-script",
        metavar="PATH",
        help="用预设脚本离线运行，不调用真实模型",
    )
    return parser


def _reconfigure(stream: object) -> None:
    """控制台编码可能容不下一部分字符；改用替换模式，绝不因此崩溃。"""
    reconfigure = getattr(stream, "reconfigure", None)
    if not callable(reconfigure):
        return
    try:
        reconfigure(errors="replace")
    except (ValueError, OSError):
        pass


def _fail(message: str) -> int:
    print(message, file=sys.stderr)
    return _EXIT_USAGE


class _UsageError(Exception):
    """配置或用法错误；main 统一转成退出码 2。"""


def _read_request(args: argparse.Namespace) -> dict:
    """读输入文件并叠加命令行覆盖项；任何问题都抛 _UsageError。"""
    raw: dict = {}
    if args.input:
        path = Path(args.input)
        if not path.is_file():
            raise _UsageError(f"输入文件不存在：{path}")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except UnicodeDecodeError:
            raise _UsageError(f"输入文件不是 UTF-8 编码：{path}") from None
        except OSError as exc:
            raise _UsageError(f"无法读取输入文件：{path}（{exc}）") from None
        except json.JSONDecodeError as exc:
            raise _UsageError(f"输入文件 JSON 错误：{path}（{exc}）") from None
        if not isinstance(payload, dict):
            raise _UsageError(f"输入文件必须是 JSON 对象：{path}")
        raw = dict(payload)

    for name, field in _OVERRIDE_FIELDS.items():
        value = getattr(args, name)
        if value is not None:
            raw[field] = value

    # 输入字段类型不合规时 normalize_request 会抛异常；在这一层转成用法错误。
    try:
        normalize_request(raw)
    except (TypeError, ValueError, OverflowError) as exc:
        raise _UsageError(f"需求字段不合法：{' '.join(str(exc).split())}") from None
    return raw


def _check_model_config() -> None:
    """真实模型模式必须先有配置；不写任何产物，也不静默回退到 Mock。"""
    missing = [name for name in _REQUIRED_ENV if not os.environ.get(name, "").strip()]
    if missing:
        raise _UsageError(
            f"缺少模型配置：{'、'.join(missing)}。"
            "请在 .env 或环境变量中设置后重试；"
            "离线跑流程可用 --mock-script examples/mock_scripts/01_normal.json。"
        )


def _build_llm(args: argparse.Namespace) -> tuple[object, str]:
    """返回 (llm, model_name)；预设脚本或模型配置有问题时抛 _UsageError。"""
    if args.mock_script:
        try:
            return ScriptedLLM.from_file(Path(args.mock_script)), _MOCK_MODEL_NAME
        except LLMError as exc:
            raise _UsageError(f"无法使用预设脚本：{args.mock_script}（{exc}）") from None

    _check_model_config()
    model_name = os.environ["LLM_MODEL"].strip()
    # 与 app._secrets_from_env 用同一个去空白后的值，脱敏才能精确匹配实际使用的密钥。
    api_key = os.environ["LLM_API_KEY"].strip()
    try:
        llm = OpenAICompatibleLLM(
            model_name,
            base_url=os.environ.get("LLM_BASE_URL", "").strip() or None,
            api_key=api_key,
        )
    except LLMError as exc:
        raise _UsageError(str(exc)) from None
    return llm, model_name


def _exit_code(result: AgentResult) -> int:
    return _EXIT_OK if result.status in ("completed", "needs_input") else _EXIT_NOT_DONE


def _default_out_dir() -> Path:
    return Path("runs") / datetime.now().strftime("%Y%m%d-%H%M%S")


def _print_artifacts(out_dir: Path) -> None:
    print("产物路径：")
    for name in _OUTPUT_FILES:
        print(f"- {name}: {(out_dir / name).resolve()}")


def main(argv: list[str] | None = None) -> int:
    _reconfigure(sys.stdout)
    _reconfigure(sys.stderr)
    load_dotenv()

    args = _build_parser().parse_args(argv)

    # 先做完全部用法与配置校验，失败时不创建任何产物目录。
    try:
        raw_request = _read_request(args)
        llm, model_name = _build_llm(args)
    except _UsageError as exc:
        return _fail(str(exc))

    out_dir = Path(args.out_dir) if args.out_dir else _default_out_dir()
    if out_dir.exists() and not out_dir.is_dir():
        return _fail(f"--out-dir 指向的不是目录：{out_dir}")
    fault = (
        FaultPlan(tool=args.fail_tool, times=args.fail_times)
        if args.fail_tool
        else None
    )

    result = run_once(
        raw_request,
        llm,
        mode="mock" if args.mock_script else "real",
        model_name=model_name,
        data_dir=Path(args.data_dir),
        fault=fault,
        max_steps=args.max_steps,
        max_tool_calls=_DEFAULT_MAX_TOOL_CALLS,
        out_dir=out_dir,
    )

    print((out_dir / "script.md").read_text(encoding="utf-8"))
    _print_artifacts(out_dir)
    return _exit_code(result)
