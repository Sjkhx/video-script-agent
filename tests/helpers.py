import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
SLOGAN = "剪刀鱼，剪出属于你的故事"
CLAIM_P01 = {"source_id": "P01", "quote": "支持字幕"}


def fit_draft(n_shots=4, chars=28, title="静音也能看懂"):
    """每个分镜 chars 个计时字符，首镜引用 P01，末镜以品牌语结尾。n_shots 至少为 2。"""
    shots = []
    for i in range(1, n_shots + 1):
        if i == 1:
            narration, claims = "支持字幕" + "嗯" * (chars - 4), [dict(CLAIM_P01)]
        elif i == n_shots:
            narration, claims = "嗯" * (chars - 11) + SLOGAN, []
        else:
            narration, claims = "嗯" * chars, []
        shots.append({"id": i, "visual": "画面", "narration": narration, "claims": claims})
    return {"title": title, "shots": shots}


def with_narration(index, text, claims=None):
    draft = fit_draft()
    draft["shots"][index]["narration"] = text
    if claims is not None:
        draft["shots"][index]["claims"] = claims
    return draft


def args(**kwargs):
    kwargs.setdefault("decision_note", "测试")
    return json.dumps(kwargs, ensure_ascii=False)


def call(name, **kwargs):
    kwargs.setdefault("decision_note", "测试")
    return {"name": name, "arguments": kwargs}


def round_of(*calls):
    return {"tool_calls": list(calls)}
