import json
import re
import threading
import time

import pytest

from script_agent.llm import LLMError
from script_agent.web.server import create_app
from web_helpers import ROOT, Client, parse_events

RUN_REQUEST = {"request": {"topic": "剪刀鱼的字幕功能", "target_duration_sec": 30}, "mode": "mock", "mock_script": "01_normal", "data_set": "default"}
REAL_BODY = {"request": {"topic": "字幕", "target_duration_sec": 30}, "mode": "real", "data_set": "default"}


class BlockingLLM:
    def __init__(self):
        self.release = threading.Event()

    def complete(self, messages, tools):
        self.release.wait(10)
        raise LLMError("结束")


class CrashingLLM:
    def complete(self, messages, tools):
        raise RuntimeError("boom sk-should-not-leak")


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("LLM_MODEL", "")
    return Client(create_app(root=ROOT, runs_dir=tmp_path / "runs"))


def start(client, body=RUN_REQUEST):
    response = client.post("/api/runs", json=body)
    assert response.status_code == 202, response.text
    return response.json()["run_id"]


def wait(client, run_id, timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        data = client.get(f"/api/runs/{run_id}").json()
        if data["status"] != "running":
            return data
        time.sleep(0.05)
    raise AssertionError("运行没有结束")


def sse(client, run_id, headers=None):
    response = client.get(f"/api/runs/{run_id}/events", headers=headers)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    return parse_events(response.text)


def test_meta_without_config(client):
    data = client.get("/api/meta").json()
    assert data["real_available"] is False and data["model"] is None
    assert [d["id"] for d in data["data_sets"]] == [
        "default",
        "no_subtitle",
        "entertainment",
    ]
    assert {m["id"] for m in data["mock_scripts"]} == {"01_normal", "06_over_duration_fixed"}


def test_meta_never_exposes_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "sk-should-not-leak")
    monkeypatch.setenv("LLM_MODEL", "demo-model")
    monkeypatch.setenv("LLM_BASE_URL", "https://relay.should-not-leak.example/v1")
    text = Client(create_app(root=ROOT, runs_dir=tmp_path)).get("/api/meta").text
    assert "demo-model" in text
    assert "should-not-leak" not in text


def test_examples_list_follows_cases(client):
    examples = client.get("/api/examples").json()["examples"]
    assert len(examples) == 10 and examples[0]["name"] == "01_normal"
    assert examples[0]["status"] == "completed" and examples[0]["title"]
    assert examples[1]["title"] is None


def test_example_detail(client):
    first = client.get("/api/examples/01_normal").json()
    assert first["data_set"] == "default" and first["result"]["status"] == "completed"
    assert first["result"]["target_duration_sec"] == 30.0
    assert first["records"][0]["type"] == "run_start" and first["markdown"].startswith("#")
    assert client.get("/api/examples/04_tool_fail_transient").json()["fault"] == {"tool": "estimate_duration", "times": 1}
    assert client.get("/api/examples/10_materials_changed").json()["data_set"] == "no_subtitle"


@pytest.mark.parametrize("name", ["nope", "..%2F..%2Fdata", "01_normal%2F..%2F..%2F..%2F.env"])
def test_unknown_example_is_404(client, name):
    assert client.get(f"/api/examples/{name}").status_code == 404


def test_materials_by_data_set(client):
    ids = lambda s: {m["id"] for m in client.get(f"/api/materials?data_set={s}").json()["materials"]}
    assert "P01" in ids("default") and "P01" not in ids("no_subtitle")
    assert client.get("/api/materials?data_set=../../etc").status_code == 400


def test_real_without_config_is_409(client):
    response = client.post("/api/runs", json={**RUN_REQUEST, "mode": "real", "mock_script": None})
    assert response.status_code == 409 and response.json()["detail"]["code"] == "MODEL_NOT_CONFIGURED"


@pytest.mark.parametrize("patch,code", [
    ({"mock_script": "../../secret"}, 400),
    ({"mock_script": None}, 400),
    ({"data_set": "../../etc"}, 400),
    ({"mode": "other"}, 422),
    ({"max_steps": 0}, 422),
    ({"max_steps": 21}, 422),
    ({"fault": {"tool": "delete_all", "times": 1}}, 422),
    ({"fault": {"tool": "check_rules", "times": 0}}, 422),
    ({"request": {"topic": "字" * 201}}, 422),
])
def test_invalid_run_requests(client, patch, code):
    assert client.post("/api/runs", json={**RUN_REQUEST, **patch}).status_code == code


def test_invalid_json_body(client):
    response = client.post("/api/runs", raw=b"{bad")
    assert response.status_code == 400 and response.json()["detail"]["code"] == "INVALID_JSON"


def test_post_requires_json_content_type(client):
    assert client.post("/api/runs", json=RUN_REQUEST, headers={"Content-Type": "text/plain"}).status_code == 415


def test_cross_origin_post_is_rejected(client):
    assert client.post("/api/runs", json=RUN_REQUEST, headers={"Origin": "http://evil.example"}).status_code == 403
    assert client.post("/api/runs", json=RUN_REQUEST, headers={"Origin": "http://127.0.0.1:8765"}).status_code == 202


def test_foreign_host_is_rejected(client):
    response = client.get("/api/meta", headers={"Host": "evil.example"})
    assert response.status_code == 400 and response.json()["detail"]["code"] == "BAD_HOST"


def test_unknown_path_and_method(client):
    assert client.get("/api/nope").status_code == 404
    assert client.post("/api/meta", json={}).status_code == 405
    assert client.get("/../../.env").status_code == 404
    assert client.get("/js/../../../.env").status_code == 404


def test_mock_run_completes_and_writes_artifacts(client, tmp_path):
    run_id = start(client)
    data = wait(client, run_id)
    assert data["status"] == "completed" and data["result"]["mode"] == "mock"
    assert data["markdown"].startswith("[MOCK]")
    assert data["meta"]["request"]["topic"] == "剪刀鱼的字幕功能"
    for name in ["meta.json", "result.json", "script.md", "trace.jsonl", "trace.md"]:
        assert (tmp_path / "runs" / run_id / name).exists()
    listed = client.get("/api/runs").json()["runs"]
    assert listed[0]["run_id"] == run_id and listed[0]["status"] == "completed" and listed[0]["topic"] == "剪刀鱼的字幕功能"


def test_events_replay_and_resume(client):
    run_id = start(client)
    wait(client, run_id)
    events = sse(client, run_id)
    kinds = [e["event"] for e in events]
    assert kinds[0] == "record" and kinds[-2:] == ["result", "end"]
    assert json.loads(events[0]["data"])["type"] == "run_start"
    assert any(json.loads(e["data"]).get("type") == "run_end" for e in events if e["event"] == "record")
    ids = [int(e["id"]) for e in events if e["event"] == "record"]
    assert ids == list(range(len(ids)))
    resumed = sse(client, run_id, {"Last-Event-ID": str(ids[-2])})
    assert [int(e["id"]) for e in resumed if e["event"] == "record"] == [ids[-1]]


def test_active_run_streams_until_done(tmp_path):
    llm = BlockingLLM()
    client = Client(create_app(root=ROOT, runs_dir=tmp_path, llm_factory=lambda: (llm, "stub")))
    run_id = client.post("/api/runs", json=REAL_BODY).json()["run_id"]
    threading.Timer(0.4, llm.release.set).start()
    kinds = [e["event"] for e in sse(client, run_id)]
    assert kinds[0] == "record" and kinds[-2:] == ["result", "end"]


def test_finished_run_survives_restart(client, tmp_path):
    run_id = start(client)
    wait(client, run_id)
    fresh = Client(create_app(root=ROOT, runs_dir=tmp_path / "runs"))
    assert fresh.get(f"/api/runs/{run_id}").json()["status"] == "completed"
    assert sse(fresh, run_id)[-1]["event"] == "end"


def test_interrupted_run_is_reported(client, tmp_path):
    run_id = "20261103-101530-a1b2c3"
    folder = tmp_path / "runs" / run_id
    folder.mkdir(parents=True)
    (folder / "meta.json").write_text(json.dumps({"run_id": run_id, "created_at": "2026-11-03T10:15:30Z", "request": {}, "mode": "real", "model": "m", "data_set": "default", "fault": None, "max_steps": 10}), encoding="utf-8")
    data = client.get(f"/api/runs/{run_id}").json()
    assert data["status"] == "crashed" and "中断" in data["error"]


def test_fault_reaches_the_tool(client):
    run_id = start(client, {**RUN_REQUEST, "fault": {"tool": "estimate_duration", "times": -1}})
    data = wait(client, run_id)
    assert data["status"] != "completed"
    assert any(r.get("injected_fault") for r in data["records"] if r["type"] == "step")


def test_only_one_active_run(tmp_path):
    llm = BlockingLLM()
    client = Client(create_app(root=ROOT, runs_dir=tmp_path, llm_factory=lambda: (llm, "stub")))
    run_id = client.post("/api/runs", json=REAL_BODY).json()["run_id"]
    assert client.get(f"/api/runs/{run_id}").json()["status"] == "running"
    second = client.post("/api/runs", json=REAL_BODY)
    assert second.status_code == 429 and second.json()["detail"]["code"] == "RUN_IN_PROGRESS"
    llm.release.set()
    assert wait(client, run_id)["status"] == "failed"
    assert client.post("/api/runs", json=REAL_BODY).status_code == 202


def test_crash_is_reported_and_redacted(tmp_path):
    client = Client(create_app(root=ROOT, runs_dir=tmp_path, llm_factory=lambda: (CrashingLLM(), "stub")))
    run_id = client.post("/api/runs", json=REAL_BODY).json()["run_id"]
    data = wait(client, run_id)
    assert data["status"] == "crashed" and data["error"]
    assert "should-not-leak" not in json.dumps(data, ensure_ascii=False)
    assert sse(client, run_id)[-2]["event"] == "fatal"
    assert client.post("/api/runs", json=REAL_BODY).status_code == 202


@pytest.mark.parametrize("run_id", ["nope", "20261103-101530-zzzzzz", "..%2F..%2F.env", "20261103-101530-000000"])
def test_unknown_run_is_404(client, run_id):
    assert client.get(f"/api/runs/{run_id}").status_code == 404
    assert client.get(f"/api/runs/{run_id}/events").status_code == 404


def draft_of(client, name="01_normal"):
    result = client.get(f"/api/examples/{name}").json()["result"]
    return {"title": result["title"], "shots": [{k: s[k] for k in ("id", "visual", "narration", "claims")} for s in result["shots"]]}


def verify(client, draft, source=None):
    return client.post("/api/verify", json={"source": source or {"kind": "example", "id": "01_normal"}, "draft": draft})


def test_verify_unedited_example_passes(client):
    original = client.get("/api/examples/01_normal").json()["result"]
    data = verify(client, draft_of(client)).json()
    assert data["passed"] is True
    assert data["duration"]["total_duration_sec"] == original["total_duration_sec"]
    assert data["result"]["status"] == "completed" and data["result"]["mode"] == "real"
    assert [s["duration_sec"] for s in data["result"]["shots"]] == [s["duration_sec"] for s in original["shots"]]


def test_verify_detects_invented_fact(client):
    draft = draft_of(client)
    draft["shots"][0]["narration"] = "效率提升80%"
    data = verify(client, draft).json()
    assert data["passed"] is False and data["result"]["status"] == "failed"
    assert {"UNSUPPORTED_NUMBER", "UNSUPPORTED_TERM"} <= {v["code"] for v in data["rules"]["violations"]}
    assert "未通过检查" in data["markdown"]


def test_verify_uses_server_side_target(client):
    draft = draft_of(client)
    response = client.post("/api/verify", json={"source": {"kind": "example", "id": "01_normal"}, "draft": draft, "target_duration_sec": 999, "retrieved_ids": ["P06"]})
    assert response.json()["duration"]["target_duration_sec"] == 30.0


def test_verify_retrieved_ids_come_from_trace(client):
    detail = client.get("/api/examples/01_normal").json()
    retrieved = {
        material["id"]
        for record in detail["records"]
        if record["type"] == "step" and record["action"] == "search_materials" and record["result"].get("ok")
        for material in record["result"]["materials"]
    }
    materials = client.get("/api/materials?data_set=default").json()["materials"]
    other = next(m for m in materials if m["id"] not in retrieved)
    draft = draft_of(client)
    draft["shots"][0]["claims"] = [{"source_id": other["id"], "quote": other["facts"][0]}]
    codes = {v["code"] for v in verify(client, draft).json()["rules"]["violations"]}
    assert "SOURCE_NOT_RETRIEVED" in codes


def test_verify_keeps_mock_mode(client):
    run_id = start(client)
    wait(client, run_id)
    result = client.get(f"/api/runs/{run_id}").json()["result"]
    draft = {"title": result["title"], "shots": [{k: s[k] for k in ("id", "visual", "narration", "claims")} for s in result["shots"]]}
    data = verify(client, draft, {"kind": "run", "id": run_id}).json()
    assert data["passed"] is True and data["markdown"].startswith("[MOCK]")


@pytest.mark.parametrize("field,message", [("narration", "旁白"), ("visual", "画面")])
def test_verify_rejects_blank_fields(client, field, message):
    draft = draft_of(client)
    draft["shots"][1][field] = "   "
    response = verify(client, draft)
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "BLANK_FIELD" and detail["shot_id"] == 2 and detail["field"] == field and message in detail["message"]


def test_verify_rejects_blank_title_and_oversize(client):
    draft = draft_of(client)
    assert verify(client, {**draft, "title": " "}).json()["detail"]["code"] == "BLANK_FIELD"
    assert verify(client, {**draft, "shots": []}).status_code == 422
    long_shot = json.loads(json.dumps(draft))
    long_shot["shots"][0]["narration"] = "字" * 2001
    assert verify(client, long_shot).status_code == 422


def test_verify_source_errors(client):
    draft = draft_of(client)
    assert verify(client, draft, {"kind": "example", "id": "nope"}).status_code == 404
    assert verify(client, draft, {"kind": "run", "id": "20261103-101530-a1b2c3"}).status_code == 404
    no_target = verify(client, draft, {"kind": "example", "id": "02_missing_target"})
    assert no_target.status_code == 409 and no_target.json()["detail"]["code"] == "NO_TARGET"


def test_index_is_served_with_csp(client):
    response = client.get("/")
    assert response.status_code == 200 and "text/html" in response.headers["content-type"]
    assert "default-src 'self'" in response.headers["content-security-policy"]
    assert "unsafe-inline" not in response.headers["content-security-policy"]
    assert response.headers["x-content-type-options"] == "nosniff"


def test_static_files_have_no_unsafe_dom_or_external_urls():
    static = ROOT / "src/script_agent/web/static"
    banned = re.compile(r"innerHTML|outerHTML|insertAdjacentHTML|document\.write|\beval\(|https?://(?!www\.w3\.org/)")
    offenders = [str(p) for p in static.rglob("*") if p.is_file() and banned.search(p.read_text(encoding="utf-8"))]
    assert offenders == []


def test_server_binds_loopback_only():
    source = (ROOT / "src/script_agent/web/__main__.py").read_text(encoding="utf-8")
    assert '"127.0.0.1"' in source and "--host" not in source
