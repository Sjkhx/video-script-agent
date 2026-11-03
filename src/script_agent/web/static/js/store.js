// 全局状态：视图只通过 setState 修改，再由订阅者重绘。

const state = {
  meta: null,
  view: "script",
  leftTab: "new",
  source: null, // {kind: "run"|"example", id}
  phase: "idle", // idle | running | done
  mode: null,
  request: null,
  records: [],
  result: null,
  markdown: null,
  status: null,
  error: null,
  reconnecting: false,
  formError: null,
  draft: null,
  originalDraft: null,
  dirty: false,
  durations: new Map(), // 分镜 _key -> 秒，只来自工具结果
  originalDurations: new Map(),
  staleKeys: new Set(),
  structureVersion: 0,
  verification: null,
  verifyError: null,
  verifying: false,
  materials: [],
  retrievedIds: [],
  examples: [],
  runs: [],
};

const subscribers = new Set();

export function getState() {
  return state;
}

export function setState(patch) {
  Object.assign(state, patch);
  for (const subscriber of subscribers) subscriber(state);
}

export function subscribe(subscriber) {
  subscribers.add(subscriber);
  subscriber(state);
  return () => subscribers.delete(subscriber);
}
