// 左栏“记录”：已提交的真实运行和本地运行。

import { openExample, openRun } from "../actions.js";
import { formatTime } from "../derive.js";
import { h } from "../dom.js";
import { STATUS_LABELS, badgeClass } from "../labels.js";
import { subscribe } from "../store.js";

function statusBadge(status) {
  return h("span", { class: badgeClass(status) }, STATUS_LABELS[status] ?? status ?? "未知");
}

function isCurrent(source, kind, id) {
  return source?.kind === kind && source?.id === id;
}

function exampleItem(example, source) {
  return h(
    "button",
    {
      class: `history-item${isCurrent(source, "example", example.name) ? " is-current" : ""}`,
      type: "button",
      onClick: () => openExample(example.name),
    },
    h("span", { class: "history-title" }, `${example.name.slice(0, 2)} · ${example.covers ?? example.name}`),
    h(
      "span",
      { class: "history-meta" },
      statusBadge(example.status),
      example.total_tokens != null
        ? h("span", { class: "mono" }, `${example.total_tokens.toLocaleString("en-US")} tokens`)
        : null,
    ),
  );
}

function runItem(run, source) {
  return h(
    "button",
    {
      class: `history-item${isCurrent(source, "run", run.run_id) ? " is-current" : ""}`,
      type: "button",
      onClick: () => openRun(run.run_id),
    },
    h("span", { class: "history-title" }, run.topic || "未填写主题"),
    h(
      "span",
      { class: "history-meta" },
      statusBadge(run.status),
      run.mode === "mock" ? h("span", { class: "badge badge-warn" }, "演示") : null,
      h("span", { class: "mono" }, formatTime(run.created_at)),
    ),
  );
}

export function renderHistory(container) {
  let lastKey = null;
  subscribe((state) => {
    const key = JSON.stringify([state.examples, state.runs, state.source]);
    if (key === lastKey) return;
    lastKey = key;
    container.replaceChildren(
      h("h2", { class: "panel-title history-group" }, "已提交的真实运行"),
      ...state.examples.map((example) => exampleItem(example, state.source)),
      h("h2", { class: "panel-title history-group" }, "本地运行"),
      ...(state.runs.length
        ? state.runs.map((run) => runItem(run, state.source))
        : [h("p", { class: "history-empty" }, "还没有本地运行。")]),
    );
  });
}
