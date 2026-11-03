// 接口封装：错误统一成 ApiError，SSE 由浏览器负责断线重连。

export class ApiError extends Error {
  constructor(status, detail) {
    super(detail?.message ?? `请求失败（${status}）`);
    this.status = status;
    this.code = detail?.code ?? "UNKNOWN";
    this.detail = detail ?? {};
  }
}

async function request(path, options) {
  let response;
  try {
    response = await fetch(path, options);
  } catch {
    throw new ApiError(0, { code: "NETWORK", message: "连接不上服务，请确认它还在运行。" });
  }
  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  if (!response.ok) throw new ApiError(response.status, payload?.detail);
  return payload;
}

function post(path, body) {
  return request(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export const getMeta = () => request("/api/meta");
export const getMaterials = (dataSet) => request(`/api/materials?data_set=${encodeURIComponent(dataSet)}`);
export const listExamples = () => request("/api/examples");
export const getExample = (name) => request(`/api/examples/${encodeURIComponent(name)}`);
export const listRuns = () => request("/api/runs");
export const getRun = (id) => request(`/api/runs/${encodeURIComponent(id)}`);
export const startRun = (body) => post("/api/runs", body);
export const verify = (source, draft) => post("/api/verify", { source, draft });

export function openEvents(runId, { onRecord, onResult, onFatal, onEnd, onConnection }) {
  const source = new EventSource(`/api/runs/${encodeURIComponent(runId)}/events`);
  source.addEventListener("record", (event) => {
    onRecord(JSON.parse(event.data), Number(event.lastEventId));
  });
  source.addEventListener("result", (event) => onResult(JSON.parse(event.data)));
  source.addEventListener("fatal", (event) => onFatal(JSON.parse(event.data)));
  source.addEventListener("end", () => {
    source.close();
    onEnd();
  });
  source.addEventListener("open", () => onConnection?.(true));
  source.addEventListener("error", () => {
    if (source.readyState === EventSource.CONNECTING) {
      onConnection?.(false);
    } else if (source.readyState === EventSource.CLOSED) {
      onFatal({ message: "和服务的连接已断开。" });
      onEnd();
    }
  });
  return () => source.close();
}
