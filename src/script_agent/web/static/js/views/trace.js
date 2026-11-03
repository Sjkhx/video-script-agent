// 右栏：决策轨迹。每一步的动作、观察结果和模型给出的依据。

import { statsOf } from "../derive.js";
import { h, icon } from "../dom.js";
import { ACTION_LABELS, DURATION_LABELS, RULES_LABELS, badgeClass } from "../labels.js";
import { subscribe } from "../store.js";

const MAX_VIOLATIONS_SHOWN = 3;
const TERMINAL_ACTIONS = new Set(["submit_script", "ask_user", "report_failure"]);
const expanded = new Set();

function seconds(value) {
  return `${Math.round((value ?? 0) * 100) / 100}s`;
}

function dotClass(step) {
  const { result, action } = step;
  if (result?.ok === false) {
    return result.error?.code === "GATE_REJECTED" ? "dot-warn" : "dot-bad";
  }
  if (TERMINAL_ACTIONS.has(action)) return "dot-end";
  if (action === "estimate_duration" && result?.verdict !== "pass") return "dot-warn";
  if (action === "check_rules" && result?.verdict !== "pass") return "dot-warn";
  if (action === "search_materials" && !result?.count) return "dot-warn";
  return "dot-ok";
}

function resultBadge(step) {
  const { result, action } = step;
  if (result?.ok === false) {
    const rejected = result.error?.code === "GATE_REJECTED";
    return h("span", { class: rejected ? "badge badge-warn" : "badge badge-bad" }, rejected ? "被把关拒绝" : "工具报错");
  }
  if (action === "estimate_duration") {
    return h("span", { class: badgeClass(result?.verdict) }, DURATION_LABELS[result?.verdict] ?? "未知");
  }
  if (action === "check_rules") {
    return h("span", { class: badgeClass(result?.verdict) }, RULES_LABELS[result?.verdict] ?? "未知");
  }
  return null;
}

function errorBody(error) {
  const retry = error?.retries_left;
  return h(
    "div",
    { class: "step-body" },
    h("span", { class: "mono" }, error?.code ?? "错误"),
    ` ${error?.message ?? ""}`,
    retry !== undefined ? `（可重试 ${retry} 次）` : "",
    (error?.reasons ?? []).length
      ? h("ul", { class: "step-list" }, error.reasons.map((reason) => h("li", null, reason)))
      : null,
  );
}

function stepBody(step) {
  const { result, action, args } = step;
  if (result?.ok === false) return errorBody(result.error);
  if (action === "search_materials") {
    const materials = result?.materials ?? [];
    return h(
      "div",
      { class: "step-body" },
      `查询：${args?.query ?? ""}`,
      materials.length
        ? h("span", { class: "step-chips" }, materials.map((m) => h("span", { class: "badge mono" }, m.id)))
        : h("span", { class: "step-chips" }, h("span", { class: "badge badge-warn" }, "没有命中")),
    );
  }
  if (action === "estimate_duration") {
    return h("div", { class: "step-body mono" }, `总时长 ${seconds(result?.total_duration_sec)} / 目标 ${seconds(result?.target_duration_sec)}`);
  }
  if (action === "check_rules") {
    const violations = result?.violations ?? [];
    if (!violations.length) return null;
    const shown = violations.slice(0, MAX_VIOLATIONS_SHOWN);
    return h(
      "div",
      { class: "step-body" },
      `未通过 · ${violations.length} 项`,
      h(
        "ul",
        { class: "step-list" },
        shown.map((item) => h("li", null, item.detail)),
        violations.length > shown.length ? h("li", null, `还有 ${violations.length - shown.length} 项`) : null,
      ),
    );
  }
  if (action === "submit_script") return h("div", { class: "step-body" }, "提交通过");
  if (action === "ask_user") {
    return h("ul", { class: "step-list" }, (args?.questions ?? []).map((question) => h("li", null, question)));
  }
  if (action === "report_failure") return h("div", { class: "step-body" }, args?.reason ?? "");
  return h("div", { class: "step-body" }, step.result_summary ?? "");
}

function stepDetail(step, key, rebuild) {
  const open = expanded.has(key);
  return [
    h(
      "button",
      {
        class: "linkbtn step-toggle",
        type: "button",
        "aria-expanded": String(open),
        onClick() {
          if (expanded.has(key)) expanded.delete(key);
          else expanded.add(key);
          rebuild();
        },
      },
      icon("chevron"),
      "查看参数和返回",
    ),
    open
      ? h(
          "div",
          { class: "step-detail" },
          h("h4", null, "工具参数"),
          h("pre", null, JSON.stringify(step.args ?? {}, null, 2)),
          h("h4", null, "返回结果"),
          h("pre", null, JSON.stringify(step.result ?? {}, null, 2)),
        )
      : null,
  ];
}

function stepItem(step, key, rebuild, isNew) {
  return h(
    "div",
    { class: isNew ? "step is-new" : "step" },
    h("span", { class: `step-dot ${dotClass(step)}` }),
    h(
      "div",
      { class: "step-title" },
      h("span", { class: "step-name" }, ACTION_LABELS[step.action] ?? step.action),
      h("span", { class: "step-tool" }, step.action),
      resultBadge(step),
      step.injected_fault ? h("span", { class: "badge badge-bad badge-outline" }, "故障注入") : null,
    ),
    stepBody(step),
    step.decision_note ? h("p", { class: "step-note" }, h("b", null, "依据"), step.decision_note) : null,
    stepDetail(step, key, rebuild),
  );
}

function noteItem(note) {
  return h(
    "div",
    { class: "step" },
    h("span", { class: "step-dot dot-warn" }),
    h("div", { class: "step-title" }, h("span", { class: "step-name" }, "模型没有调用工具")),
    h("p", { class: "step-note" }, note.detail ?? ""),
  );
}

function statsText(state) {
  const { rounds, calls, tokens } = statsOf(state.records, state.result);
  const start = state.records.find((record) => record.type === "run_start");
  const limit = start?.max_steps;
  return `${rounds}${limit ? ` / ${limit}` : ""} 轮 · ${calls} 次调用 · ${tokens.toLocaleString("en-US")} tokens`;
}

export function renderTrace(container) {
  const stats = h("span", { class: "trace-stats" });
  const list = h("div", { class: "trace-list" });
  const empty = h("p", { class: "trace-empty" }, "运行后，这里会显示模型每一步的动作、观察结果和决策依据。");
  container.append(h("div", { class: "trace-head" }, h("h2", { class: "panel-title" }, "决策轨迹"), stats), empty, list);

  let pinned = true;
  let lastKey = null;
  let current = null;
  let shownSeq = 0;
  container.addEventListener("scroll", () => {
    pinned = container.scrollHeight - container.scrollTop - container.clientHeight < 60;
  });

  function rebuild() {
    const state = current;
    const sourceKey = `${state.source?.kind}:${state.source?.id}`;
    const items = [];
    let round = null;
    for (const record of state.records) {
      if (record.type !== "step" && record.type !== "note") continue;
      if (record.round !== round) {
        round = record.round;
        items.push(h("div", { class: "round-head" }, `第 ${round} 轮`));
      }
      items.push(
        record.type === "step"
          ? stepItem(record, `${sourceKey}:${record.seq}`, rebuild, state.phase === "running" && record.seq > shownSeq)
          : noteItem(record),
      );
    }
    if (state.phase === "running") {
      items.push(
        h(
          "div",
          { class: "step-waiting" },
          h("span", { class: "pulse" }),
          state.reconnecting ? "连接中断，正在重连…" : "模型决策中…",
        ),
      );
    }
    shownSeq = Math.max(0, ...state.records.map((record) => record.seq ?? 0));
    const scrollTop = container.scrollTop;
    list.replaceChildren(...items);
    container.scrollTop = scrollTop;
  }

  subscribe((state) => {
    current = state;
    const key = `${state.source?.kind}:${state.source?.id}|${state.records.length}|${state.phase}|${state.reconnecting}`;
    if (key === lastKey) return;
    const sourceChanged = lastKey?.split("|")[0] !== key.split("|")[0];
    lastKey = key;
    const hasRecords = state.records.length > 0 || state.phase === "running";
    empty.hidden = hasRecords;
    stats.textContent = hasRecords ? statsText(state) : "";
    rebuild();
    if (sourceChanged) {
      pinned = true;
      container.scrollTop = 0;
    } else if (state.phase === "running" && pinned) {
      container.scrollTop = container.scrollHeight;
    }
  });
}
