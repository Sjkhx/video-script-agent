// 启动：读取配置，挂载三个面板，处理顶栏、视图切换和地址栏路由。

import { refreshHistory, routeFromHash } from "./actions.js";
import { getMeta, listExamples } from "./api.js";
import { formatSeconds } from "./derive.js";
import { h } from "./dom.js";
import { STATUS_LABELS, badgeClass } from "./labels.js";
import { setState, subscribe } from "./store.js";
import { renderBrief } from "./views/brief.js";
import { renderEditor } from "./views/editor.js";
import { renderHistory } from "./views/history.js";
import { renderTrace } from "./views/trace.js";

function renderLeftPanel(container, meta, covers) {
  const tabs = [
    { id: "new", label: "新建" },
    { id: "history", label: "记录" },
  ];
  const buttons = tabs.map(({ id, label }) =>
    h("button", { type: "button", role: "tab", onClick: () => setState({ leftTab: id }) }, label),
  );
  const newPane = h("div", { role: "tabpanel" });
  const historyPane = h("div", { role: "tabpanel", class: "history" });
  container.append(h("div", { class: "segmented", role: "tablist", "aria-label": "新建或记录" }, buttons), newPane, historyPane);
  renderBrief(newPane, meta, covers);
  renderHistory(historyPane);
  subscribe((state) => {
    buttons.forEach((button, index) => {
      button.setAttribute("aria-selected", String(tabs[index].id === state.leftTab));
    });
    newPane.hidden = state.leftTab !== "new";
    historyPane.hidden = state.leftTab !== "history";
  });
}

function runStateContent(state) {
  if (state.phase === "idle") return [h("span", { class: "runstate-text" }, "待开始")];
  if (state.phase === "running") {
    const start = state.records.find((record) => record.type === "run_start");
    const round = state.records.reduce((max, record) => Math.max(max, record.round ?? 0), 0);
    const text = state.reconnecting
      ? "连接中断，正在重连…"
      : `第 ${Math.max(round, 1)} / ${start?.max_steps ?? "—"} 轮 · 模型决策中`;
    return [h("span", { class: "pulse" }), h("span", { class: "runstate-text" }, text)];
  }
  const result = state.result;
  const summary = result?.total_duration_sec != null
    ? `${result.title ?? ""} · ${formatSeconds(result.total_duration_sec)} 秒`
    : result?.message ?? state.error ?? "";
  return [
    h("span", { class: badgeClass(state.status) }, STATUS_LABELS[state.status] ?? state.status ?? "—"),
    h("span", { class: "runstate-text", title: summary }, summary),
  ];
}

function renderTopbar(meta) {
  const runState = document.getElementById("run-state");
  const modelState = document.getElementById("model-state");
  modelState.replaceChildren(
    ...(meta.real_available
      ? [h("span", null, "真实模型"), ...(meta.model ? [h("span", { class: "mono" }, meta.model)] : [])]
      : [h("span", null, "未配置模型，可用离线演示")]),
  );
  let lastKey = null;
  subscribe((state) => {
    const key = [state.phase, state.status, state.records.length, state.reconnecting, state.result?.title, state.source?.id].join("|");
    if (key === lastKey) return;
    lastKey = key;
    runState.replaceChildren(...runStateContent(state));
  });
}

function renderViewSwitch() {
  const nav = document.getElementById("view-switch");
  const buttons = [...nav.querySelectorAll("button")];
  for (const button of buttons) {
    button.addEventListener("click", () => setState({ view: button.dataset.viewTarget }));
  }
  subscribe((state) => {
    document.body.dataset.view = state.view;
    for (const button of buttons) {
      button.setAttribute("aria-current", String(button.dataset.viewTarget === state.view));
    }
  });
}

async function boot() {
  const panelBrief = document.getElementById("panel-brief");
  renderViewSwitch();
  renderEditor(document.getElementById("panel-script"));
  renderTrace(document.getElementById("panel-trace"));

  let meta;
  try {
    meta = await getMeta();
  } catch (error) {
    panelBrief.append(h("p", { class: "form-error brief-body" }, error.message));
    return;
  }
  setState({ meta });

  let covers = {};
  try {
    const { examples } = await listExamples();
    covers = Object.fromEntries(examples.map((example) => [example.name, example.covers]));
  } catch {
    // 标签的提示文字取不到也不影响使用。
  }
  renderLeftPanel(panelBrief, meta, covers);
  renderTopbar(meta);
  refreshHistory();

  if (window.location.hash) {
    await routeFromHash();
  } else if (window.matchMedia("(max-width: 1099px)").matches) {
    setState({ view: "brief" });
  }
  window.addEventListener("hashchange", routeFromHash);
}

boot();
