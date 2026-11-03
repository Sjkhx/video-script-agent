// 应用流程：打开记录、发起运行、接收事件。视图只调用这里，不直接改流程状态。

import * as api from "./api.js";
import { retrievedIdsOf } from "./derive.js";
import { getState, setState } from "./store.js";

let closeEvents = null;
let lastRecordId = -1;
let shotKeySeq = 0;
let currentHash = "";

function setHash(hash) {
  currentHash = hash;
  if (window.location.hash !== hash) window.location.hash = hash;
}

function isNarrow() {
  return window.matchMedia("(max-width: 1099px)").matches;
}

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

// _key 是客户端内部标识，增删分镜后仍能对上时长；提交前会去掉。
function decorateDraft(draft) {
  return {
    title: draft.title ?? "",
    shots: draft.shots.map((shot) => {
      shotKeySeq += 1;
      return {
        id: shot.id,
        visual: shot.visual ?? "",
        narration: shot.narration ?? "",
        claims: clone(shot.claims ?? []),
        _key: shotKeySeq,
      };
    }),
  };
}

export function newShotKey() {
  shotKeySeq += 1;
  return shotKeySeq;
}

export function cloneDraft(draft) {
  return clone(draft);
}

function confirmDiscard() {
  return !getState().dirty || window.confirm("有未校验的修改，确定放弃吗？");
}

function stopEvents() {
  closeEvents?.();
  closeEvents = null;
}

async function loadMaterials(dataSet) {
  try {
    const { materials } = await api.getMaterials(dataSet);
    setState({ materials });
  } catch {
    setState({ materials: [] });
  }
}

function applyLoaded({ source, status, mode, request, records, result, markdown, error, dataSet }) {
  const base = result?.shots
    ? { title: result.title, shots: result.shots }
    : result?.unverified_draft ?? null;
  const draft = base ? decorateDraft(base) : null;
  const durations = new Map();
  if (draft) {
    const measured = result.shots ?? result.last_estimate?.shots ?? [];
    measured.forEach((item, index) => {
      if (draft.shots[index]) durations.set(draft.shots[index]._key, item.duration_sec);
    });
  }
  setState({
    source,
    status,
    phase: "done",
    mode,
    request,
    records,
    result,
    markdown,
    error,
    reconnecting: false,
    draft,
    originalDraft: draft ? clone(draft) : null,
    durations,
    originalDurations: new Map(durations),
    staleKeys: new Set(),
    dirty: false,
    verification: null,
    verifyError: null,
    verifying: false,
    retrievedIds: retrievedIdsOf(records),
    structureVersion: getState().structureVersion + 1,
  });
  loadMaterials(dataSet);
}

export async function refreshHistory() {
  try {
    const [{ examples }, { runs }] = await Promise.all([api.listExamples(), api.listRuns()]);
    setState({ examples, runs });
  } catch {
    // 记录列表读取失败不影响当前操作，下次刷新再试。
  }
}

export async function openExample(name) {
  if (!confirmDiscard()) return;
  stopEvents();
  let detail;
  try {
    detail = await api.getExample(name);
  } catch (error) {
    setState({ formError: error.message });
    return;
  }
  setHash(`#example=${encodeURIComponent(name)}`);
  applyLoaded({
    source: { kind: "example", id: name },
    status: detail.result?.status ?? null,
    mode: detail.result?.mode ?? "real",
    request: detail.input,
    records: detail.records,
    result: detail.result,
    markdown: detail.markdown,
    error: null,
    dataSet: detail.data_set,
  });
  if (isNarrow()) setState({ view: "script" });
}

function applyRun(data) {
  applyLoaded({
    source: { kind: "run", id: data.run_id },
    status: data.status,
    mode: data.result?.mode ?? data.meta?.mode ?? "real",
    request: data.meta?.request ?? null,
    records: data.records,
    result: data.result,
    markdown: data.markdown,
    error: data.error,
    dataSet: data.meta?.data_set ?? "default",
  });
}

async function finishRun(runId) {
  stopEvents();
  try {
    applyRun(await api.getRun(runId));
  } catch (error) {
    setState({ phase: "done", status: "crashed", error: error.message, reconnecting: false });
  }
  refreshHistory();
  if (isNarrow()) setState({ view: "script" });
}

function followRun(runId) {
  stopEvents();
  closeEvents = api.openEvents(runId, {
    onRecord(record, id) {
      if (id <= lastRecordId) return;
      lastRecordId = id;
      const { records } = getState();
      setState({ records: [...records, record], retrievedIds: retrievedIdsOf([...records, record]) });
    },
    onResult() {},
    onFatal() {},
    onEnd() {
      finishRun(runId);
    },
    onConnection(connected) {
      setState({ reconnecting: !connected });
    },
  });
}

function beginRunning(runId, { mode, request, records, dataSet }) {
  lastRecordId = records.length - 1;
  setHash(`#run=${encodeURIComponent(runId)}`);
  setState({
    source: { kind: "run", id: runId },
    status: "running",
    phase: "running",
    mode,
    request,
    records,
    result: null,
    markdown: null,
    error: null,
    formError: null,
    reconnecting: false,
    draft: null,
    originalDraft: null,
    durations: new Map(),
    originalDurations: new Map(),
    staleKeys: new Set(),
    dirty: false,
    verification: null,
    verifyError: null,
    retrievedIds: retrievedIdsOf(records),
    structureVersion: getState().structureVersion + 1,
  });
  loadMaterials(dataSet);
  followRun(runId);
}

export async function openRun(runId) {
  if (!confirmDiscard()) return;
  stopEvents();
  let data;
  try {
    data = await api.getRun(runId);
  } catch (error) {
    setState({ formError: error.message });
    return;
  }
  if (data.status === "running") {
    beginRunning(runId, {
      mode: data.meta?.mode ?? "real",
      request: data.meta?.request ?? null,
      records: data.records,
      dataSet: data.meta?.data_set ?? "default",
    });
  } else {
    setHash(`#run=${encodeURIComponent(runId)}`);
    applyRun(data);
  }
  if (isNarrow()) setState({ view: data.status === "running" ? "trace" : "script" });
}

export async function startGeneration(body) {
  if (!confirmDiscard()) return;
  setState({ formError: null });
  let started;
  try {
    started = await api.startRun(body);
  } catch (error) {
    setState({ formError: error.message });
    return;
  }
  beginRunning(started.run_id, {
    mode: body.mode,
    request: body.request,
    records: [],
    dataSet: body.data_set,
  });
  refreshHistory();
  if (isNarrow()) setState({ view: "trace" });
}

export async function routeFromHash() {
  const hash = window.location.hash;
  if (hash === currentHash) return;
  const example = hash.match(/^#example=(.+)$/);
  const run = hash.match(/^#run=(.+)$/);
  currentHash = hash;
  if (example) await openExample(decodeURIComponent(example[1]));
  else if (run) await openRun(decodeURIComponent(run[1]));
}
