// 中栏：状态条、时间线、可编辑分镜、校验和导出。
// 分镜列表只在结构变化时重建；输入时只局部刷新，避免打断正在输入的文本框。

import { cloneDraft, newShotKey, openExample } from "../actions.js";
import { ApiError, verify } from "../api.js";
import { deriveVersions, formatClock, formatSeconds, timecodes } from "../derive.js";
import { autoGrow, h, icon } from "../dom.js";
import { FIELD_LABELS } from "../labels.js";
import { getState, setState, subscribe } from "../store.js";
import { fillBrief, focusField, setLeftTab } from "./brief.js";
import { createTimeline } from "./timeline.js";

const MAX_TITLE_CHARS = 20;
const MOCK_NOTICE = "[MOCK] 本次模型决策来自预设脚本，只验证流程，不证明真实模型效果。";
const UNSAFE_FILENAME = /[\\/:*?"<>|]/g;

function lastStep(records, action) {
  for (let index = records.length - 1; index >= 0; index -= 1) {
    const record = records[index];
    if (record.type === "step" && record.action === action) return record;
  }
  return null;
}

function targetOf(state) {
  if (state.verification) return state.verification.duration.target_duration_sec;
  if (state.result?.target_duration_sec != null) return state.result.target_duration_sec;
  const start = state.records.find((record) => record.type === "run_start");
  return start?.request?.target_duration_sec ?? null;
}

function sum(values) {
  return Math.round(values.reduce((total, value) => total + value, 0) * 100) / 100;
}

// 当前要展示的脚本和时长。时长只来自工具结果，不在前端估算。
function measure(state) {
  const versions = deriveVersions(state.records);
  const target = targetOf(state);
  const empty = { target, versions, shots: [], durations: [], total: null, verdict: null, overflow: null, shortfall: null, stale: false, readOnly: true, title: "" };

  if (state.phase === "running") {
    const latest = versions.at(-1);
    if (!latest) return empty;
    const estimate = latest.estimate?.ok ? latest.estimate : null;
    return {
      ...empty,
      shots: latest.draft.shots,
      title: latest.draft.title,
      durations: latest.draft.shots.map((_, index) => estimate?.shots?.[index]?.duration_sec ?? null),
      total: estimate?.total_duration_sec ?? null,
      verdict: estimate?.verdict ?? null,
      overflow: estimate?.overflow_sec ?? null,
      shortfall: estimate?.shortfall_sec ?? null,
    };
  }

  if (!state.draft) return empty;
  const durations = state.draft.shots.map((shot) => state.durations.get(shot._key) ?? null);
  const known = durations.filter((value) => value !== null);
  const base = {
    ...empty,
    shots: state.draft.shots,
    title: state.draft.title,
    durations,
    total: known.length ? sum(known) : null,
    readOnly: false,
  };
  if (state.dirty) return { ...base, stale: true };
  const estimate = state.verification?.duration ?? state.result?.last_estimate ?? null;
  if (estimate) {
    return {
      ...base,
      total: estimate.total_duration_sec,
      verdict: estimate.verdict,
      overflow: estimate.overflow_sec,
      shortfall: estimate.shortfall_sec,
    };
  }
  return { ...base, verdict: state.result?.checks?.duration ?? null };
}

function timelineModel(state, measured) {
  const clips = [];
  measured.shots.forEach((shot, index) => {
    const duration = measured.durations[index];
    if (duration === null) return;
    const label = String(index + 1).padStart(2, "0");
    const ids = [...new Set((shot.claims ?? []).map((claim) => claim.source_id))];
    clips.push({
      index,
      position: clips.length,
      label,
      duration,
      cited: ids.length > 0,
      title: `分镜 ${index + 1} · ${formatSeconds(duration)} 秒${ids.length ? ` · 引用 ${ids.join("、")}` : ""}`,
    });
  });
  return {
    target: measured.target,
    total: measured.total,
    verdict: measured.verdict,
    overflow: measured.overflow,
    shortfall: measured.shortfall,
    stale: measured.stale,
    versions: measured.versions,
    clips,
    showReadout: state.phase !== "idle",
  };
}

function violationsOf(state, measured) {
  if (state.verification) return state.verification.rules.violations ?? [];
  if (state.status === "completed") return [];
  const latest = measured.versions.at(-1);
  return latest?.rules?.ok ? latest.rules.violations ?? [] : [];
}

function violationLine(item) {
  return h("p", { class: "violation" }, item.detail, h("span", { class: "mono" }, item.code));
}

// ------- 状态条 -------

function statusBar(tone, iconName, title, ...body) {
  return h(
    "section",
    { class: "statusbar", "aria-label": "任务状态" },
    h("span", { class: `tone-${tone}` }, icon(iconName)),
    h("div", { class: "statusbar-body" }, h("h2", { class: `statusbar-title tone-${tone}` }, title), body),
  );
}

function statusSection(state, measured) {
  if (state.phase === "running") {
    const steps = state.records.filter((record) => record.type === "step");
    return statusBar("info", "info", "模型正在决策", h("p", { class: "statusbar-text" }, steps.at(-1)?.result_summary ?? "等待模型的第一步动作。"));
  }
  if (state.status === "crashed") {
    return statusBar("bad", "alert", "运行异常", h("p", { class: "statusbar-text" }, state.error ?? "运行异常结束。"));
  }
  const result = state.result;
  if (!result) return null;

  if (result.status === "completed") {
    const ids = result.source_ids ?? [];
    return statusBar(
      "ok",
      "check",
      "脚本已通过时长和规则检查",
      h(
        "p",
        { class: "statusbar-text" },
        `${formatSeconds(result.total_duration_sec)} 秒 / 目标 ${formatSeconds(result.target_duration_sec)} 秒 · ${result.shots.length} 个分镜 · 引用 ${ids.join("、") || "无"}`,
      ),
    );
  }
  if (result.status === "needs_input") {
    const ask = lastStep(state.records, "ask_user");
    const missing = result.missing_info ?? [];
    const fields = missing.filter((name) => name !== "materials");
    return statusBar(
      "info",
      "info",
      "Agent 需要你补充信息",
      ask?.args?.reason ? h("p", { class: "statusbar-text" }, ask.args.reason) : null,
      (ask?.args?.questions ?? []).length
        ? h("ul", { class: "statusbar-list" }, ask.args.questions.map((question) => h("li", null, question)))
        : null,
      missing.includes("materials")
        ? h("p", { class: "statusbar-text" }, "素材库不足，需要在 data/materials.json 补充后重试，或换一个主题。")
        : null,
      h(
        "div",
        { class: "statusbar-actions" },
        h(
          "button",
          {
            class: "btn",
            type: "button",
            onClick() {
              fillBrief(state.request ?? {});
              setLeftTab("new");
              setState({ view: "brief" });
              focusField(fields[0]);
            },
          },
          fields[0] ? `去补充${FIELD_LABELS[fields[0]] ?? ""}` : "去补充",
        ),
      ),
    );
  }
  if (result.status === "failed") {
    const report = lastStep(state.records, "report_failure");
    const unmet = report?.args?.unmet_requirements ?? [];
    return statusBar(
      "bad",
      "alert",
      "未能生成合格脚本",
      h("p", { class: "statusbar-text" }, report?.args?.reason ?? result.message),
      unmet.length ? h("ul", { class: "statusbar-list" }, unmet.map((item) => h("li", null, item))) : null,
      measured.shots.length ? h("p", { class: "statusbar-text" }, "下面是最后一版草稿，未通过检查，不可直接使用。") : null,
    );
  }
  return statusBar(
    "warn",
    "alert",
    "达到上限，任务未完成",
    h("p", { class: "statusbar-text" }, result.message),
    measured.shots.length ? h("p", { class: "statusbar-text" }, "下面是最后一版草稿，未通过检查，不可直接使用。") : null,
  );
}

// ------- 编辑操作 -------

function markEdited(shot) {
  const state = getState();
  if (shot) {
    state.staleKeys.add(shot._key);
    document.querySelector(`[data-shot-key="${shot._key}"]`)?.classList.add("is-stale");
  }
  setState({ dirty: true });
}

function renumber(draft) {
  draft.shots.forEach((shot, index) => {
    shot.id = index + 1;
  });
}

function changeStructure() {
  const state = getState();
  renumber(state.draft);
  setState({ dirty: true, structureVersion: state.structureVersion + 1 });
}

function undoEdits() {
  const state = getState();
  const draft = cloneDraft(state.originalDraft);
  setState({
    draft,
    durations: new Map(state.originalDurations),
    staleKeys: new Set(),
    dirty: false,
    verification: null,
    verifyError: null,
    structureVersion: state.structureVersion + 1,
  });
}

function focusBlankField(detail) {
  const state = getState();
  if (detail.field === "title") {
    document.getElementById("draft-title")?.focus();
    return;
  }
  const shot = state.draft.shots[detail.shot_id - 1];
  const box = document.querySelector(`[data-shot-key="${shot?._key}"] [data-field="${detail.field}"]`);
  box?.scrollIntoView({ block: "center" });
  box?.focus();
}

async function runVerification() {
  const state = getState();
  renumber(state.draft);
  const payload = {
    title: state.draft.title,
    shots: state.draft.shots.map(({ id, visual, narration, claims }) => ({ id, visual, narration, claims })),
  };
  setState({ verifying: true, verifyError: null });
  try {
    const response = await verify(state.source, payload);
    const durations = new Map();
    state.draft.shots.forEach((shot, index) => {
      durations.set(shot._key, response.duration.shots[index].duration_sec);
    });
    setState({
      verification: response,
      durations,
      staleKeys: new Set(),
      dirty: false,
      verifying: false,
      structureVersion: state.structureVersion + 1,
    });
  } catch (error) {
    setState({ verifying: false, verifyError: error instanceof ApiError || error instanceof Error ? error.message : "校验失败。" });
    if (error instanceof ApiError && error.code === "BLANK_FIELD") focusBlankField(error.detail);
  }
}

// ------- 导出 -------

function exportContent(state) {
  return {
    markdown: state.verification?.markdown ?? state.markdown ?? "",
    json: state.verification?.result ?? state.result,
  };
}

function exportName(state, extension) {
  const title = (state.draft?.title || "script").replace(UNSAFE_FILENAME, "").trim() || "script";
  return `${title}.${extension}`;
}

function downloadFile(name, text, type) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const link = h("a", { href: url, download: name });
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function exportButtons(state) {
  const disabled = state.dirty;
  const hint = disabled ? "请先重新校验" : null;
  const copy = h(
    "button",
    {
      class: "btn export-btn",
      type: "button",
      disabled,
      title: hint,
      async onClick(event) {
        const button = event.currentTarget;
        const label = button.querySelector("span");
        try {
          await navigator.clipboard.writeText(exportContent(getState()).markdown);
          label.textContent = "已复制";
        } catch {
          label.textContent = "复制失败，请用下载";
        }
        setTimeout(() => {
          label.textContent = "复制 Markdown";
        }, 1500);
      },
    },
    icon("copy"),
    h("span", null, "复制 Markdown"),
  );
  const markdown = h(
    "button",
    {
      class: "btn export-btn",
      type: "button",
      disabled,
      title: hint,
      onClick() {
        const current = getState();
        downloadFile(exportName(current, "md"), exportContent(current).markdown, "text/markdown;charset=utf-8");
      },
    },
    icon("download"),
    "下载 .md",
  );
  const json = h(
    "button",
    {
      class: "btn export-btn",
      type: "button",
      disabled,
      title: hint,
      onClick() {
        const current = getState();
        downloadFile(exportName(current, "json"), `${JSON.stringify(exportContent(current).json, null, 2)}\n`, "application/json;charset=utf-8");
      },
    },
    icon("download"),
    "下载 .json",
  );
  return [copy, markdown, json];
}

function failureSummary(verification) {
  const parts = [];
  const { duration, rules } = verification;
  if (duration.verdict === "too_long") parts.push(`时长超出 ${formatSeconds(duration.overflow_sec)} 秒`);
  if (duration.verdict === "too_short") parts.push(`时长不足 ${formatSeconds(duration.shortfall_sec)} 秒`);
  if (rules.violations?.length) parts.push(`规则 ${rules.violations.length} 项`);
  return `未通过：${parts.join("，")}`;
}

function actionBarContent(state) {
  if (state.phase !== "done" || !state.draft) return null;
  if (state.dirty) {
    return [
      h("p", { class: "actionbar-text" }, state.verifyError ? h("span", { class: "tone-bad" }, state.verifyError) : "有未校验的修改"),
      h("button", { class: "btn btn-primary", type: "button", disabled: state.verifying, onClick: runVerification }, state.verifying ? "校验中…" : "重新校验"),
      h("button", { class: "btn", type: "button", disabled: state.verifying, onClick: undoEdits }, "撤销修改"),
      exportButtons(state),
    ];
  }
  if (state.verification) {
    const passed = state.verification.passed;
    return [
      h(
        "p",
        { class: `actionbar-text ${passed ? "tone-ok" : "tone-bad"}` },
        passed ? "修改后的脚本已通过校验" : failureSummary(state.verification),
      ),
      h("button", { class: "btn", type: "button", onClick: undoEdits }, "撤销修改"),
      exportButtons(state),
    ];
  }
  return exportButtons(state);
}

// ------- 分镜 -------

function claimChips(cell, shot, readOnly) {
  const state = getState();
  const chips = (shot.claims ?? []).map((claim, index) =>
    h(
      "span",
      { class: `claim${readOnly ? " is-readonly" : ""}`, title: `素材 ${claim.source_id} 原文：${claim.quote}` },
      h("span", { class: "mono" }, claim.source_id),
      `· ${claim.quote}`,
      readOnly
        ? null
        : h(
            "button",
            {
              type: "button",
              "aria-label": `移除引用 ${claim.source_id}`,
              onClick() {
                shot.claims.splice(index, 1);
                claimChips(cell, shot, readOnly);
                markEdited(shot);
              },
            },
            icon("x"),
          ),
    ),
  );
  let adder = null;
  if (!readOnly) {
    const facts = state.materials
      .filter((material) => state.retrievedIds.includes(material.id))
      .flatMap((material) => material.facts.map((fact) => ({ id: material.id, fact })));
    const available = facts.filter(({ id, fact }) => !shot.claims.some((claim) => claim.source_id === id && claim.quote === fact));
    if (available.length) {
      adder = h(
        "select",
        {
          class: "input claim-select",
          "aria-label": "引用素材",
          onChange(event) {
            const chosen = available[Number(event.target.value)];
            if (!chosen) return;
            shot.claims.push({ source_id: chosen.id, quote: chosen.fact });
            claimChips(cell, shot, readOnly);
            markEdited(shot);
          },
        },
        h("option", { value: "" }, "+ 引用素材"),
        available.map(({ id, fact }, index) => h("option", { value: String(index) }, `${id} · ${fact}`)),
      );
    }
  }
  cell.replaceChildren(...chips, ...(adder ? [adder] : []));
}

function shotText(shot, field, label, readOnly) {
  const box = h("textarea", {
    class: `shot-text${field === "narration" ? " is-narration" : ""}`,
    rows: 2,
    maxlength: 2000,
    value: shot[field],
    readOnly,
    dataset: { field },
    "aria-label": `分镜 ${shot.id} ${label}`,
    onInput(event) {
      shot[field] = event.target.value;
      autoGrow(event.target);
      markEdited(shot);
    },
  });
  return box;
}

function shotRow(shot, index, measured, clocks, violations, state) {
  const duration = measured.durations[index];
  const clock = clocks[index];
  const readOnly = measured.readOnly;
  const claims = h("div", { class: "shot-claims" });
  claimChips(claims, shot, readOnly);
  const stale = shot._key !== undefined && state.staleKeys.has(shot._key);
  const own = violations.filter((item) => item.shot_id === shot.id);

  const row = h(
    "article",
    {
      class: `shot${stale ? " is-stale" : ""}`,
      id: `shot-${index}`,
      dataset: shot._key === undefined ? null : { shotKey: String(shot._key) },
    },
    h(
      "div",
      { class: "shot-meta" },
      h("span", { class: "shot-no" }, String(index + 1).padStart(2, "0")),
      duration === null
        ? h("span", { class: "shot-clock" }, "未估算")
        : [
            h("span", { class: "shot-clock" }, `${formatClock(clock.start)}–${formatClock(clock.end)}`),
            h("span", { class: "shot-duration" }, `${formatSeconds(duration)}s`),
          ],
      h("span", { class: "shot-stale" }, "待校验"),
      !readOnly && measured.shots.length > 1
        ? h(
            "button",
            {
              class: "iconbtn",
              type: "button",
              "aria-label": `删除分镜 ${index + 1}`,
              title: `删除分镜 ${index + 1}`,
              onClick() {
                getState().draft.shots.splice(index, 1);
                changeStructure();
              },
            },
            icon("trash"),
          )
        : null,
    ),
    h("div", { class: "shot-cell" }, h("span", { class: "shot-col-label" }, "画面"), shotText(shot, "visual", "画面", readOnly)),
    h("div", { class: "shot-cell" }, h("span", { class: "shot-col-label" }, "旁白"), shotText(shot, "narration", "旁白", readOnly), claims),
    own.length ? h("div", { class: "violations" }, own.map(violationLine)) : null,
  );
  return row;
}

function sourcesSection(state, measured) {
  const ids = [...new Set(measured.shots.flatMap((shot) => (shot.claims ?? []).map((claim) => claim.source_id)))].sort();
  if (!ids.length) return null;
  const rows = ids.flatMap((id) => {
    const material = state.materials.find((item) => item.id === id);
    const facts = material?.facts ?? ["素材库里没有这个 ID"];
    return facts.map((fact) => h("tr", null, h("td", { class: "mono" }, id), h("td", null, fact)));
  });
  return h(
    "section",
    { class: "section" },
    h("h2", { class: "panel-title" }, "素材来源"),
    h(
      "table",
      { class: "source-table" },
      h("thead", null, h("tr", null, h("th", null, "ID"), h("th", null, "事实"))),
      h("tbody", null, rows),
    ),
  );
}

function growAll(root) {
  for (const box of root.querySelectorAll("textarea.shot-text")) autoGrow(box);
}

function jumpToShot(index) {
  const row = document.getElementById(`shot-${index}`);
  if (!row) return;
  row.scrollIntoView({ block: "center", behavior: "smooth" });
  row.classList.add("is-flash");
  setTimeout(() => row.classList.remove("is-flash"), 900);
}

export function renderEditor(container) {
  const root = h("div", { class: "editor" });
  container.append(root);

  const timeline = createTimeline({
    onClipClick: jumpToShot,
    onClipHover(index, on) {
      document.getElementById(`shot-${index}`)?.classList.toggle("is-hover", on);
    },
  });
  let chrome = null;
  let lastKey = null;
  let lastMaterials = null;
  let lastView = null;

  function rebuild(state) {
    const measured = measure(state);
    const timelineBox = timeline.element;

    if (state.phase === "idle") {
      timeline.update(timelineModel(state, measured));
      root.replaceChildren(
        timelineBox,
        h(
          "div",
          { class: "empty" },
          h("h2", { class: "empty-title" }, "还没有脚本"),
          h("p", { class: "empty-text" }, "在左侧填写需求开始生成，或打开一条已提交的真实运行记录。"),
          h("button", { class: "btn", type: "button", onClick: () => openExample("01_normal") }, "打开 01 正常生成"),
        ),
      );
      chrome = null;
      return;
    }

    const hasShots = measured.shots.length > 0;
    const violations = violationsOf(state, measured);
    const titleViolations = violations.filter((item) => item.shot_id === null);
    const clocks = timecodes(measured.durations);
    const titleBox = hasShots
      ? h("input", {
          class: "title-input",
          id: "draft-title",
          type: "text",
          maxlength: 200,
          value: measured.title,
          readOnly: measured.readOnly,
          "aria-label": "脚本标题",
          onInput(event) {
            getState().draft.title = event.target.value;
            updateCount(event.target.value);
            markEdited(null);
          },
        })
      : null;
    const count = h("span", { class: "title-count" });
    function updateCount(value) {
      count.textContent = `${[...value].length} / ${MAX_TITLE_CHARS}`;
      count.classList.toggle("is-over", [...value].length > MAX_TITLE_CHARS);
    }
    if (hasShots) updateCount(measured.title);

    const actionbar = h("div", { class: "actionbar" });
    const sourcesBox = h("div");
    timeline.update(timelineModel(state, measured));
    const shotsSection = hasShots
      ? [
          h("div", { class: "titlebar" }, titleBox, count),
          titleViolations.length ? h("div", { class: "violations" }, titleViolations.map(violationLine)) : null,
          h(
            "section",
            { class: "shots", "aria-label": "分镜" },
            measured.shots.map((shot, index) => shotRow(shot, index, measured, clocks, violations, state)),
            measured.readOnly
              ? null
              : h(
                  "button",
                  {
                    class: "linkbtn add-shot",
                    type: "button",
                    onClick() {
                      const current = getState();
                      current.draft.shots.push({ id: current.draft.shots.length + 1, visual: "", narration: "", claims: [], _key: newShotKey() });
                      changeStructure();
                    },
                  },
                  icon("plus"),
                  "添加分镜",
                ),
          ),
        ]
      : null;
    const risks = state.result?.risks ?? [];

    root.replaceChildren(
      ...[
        state.mode === "mock" ? h("div", { class: "mockbar" }, MOCK_NOTICE) : null,
        statusSection(state, measured),
        hasShots || state.phase === "running" ? timelineBox : null,
        shotsSection,
        risks.length && hasShots
          ? h("section", { class: "section" }, h("h2", { class: "panel-title" }, "风险"), h("ul", { class: "risk-list" }, risks.map((risk) => h("li", null, risk))))
          : null,
        sourcesBox,
        actionbar,
      ]
        .flat()
        .filter(Boolean),
    );
    growAll(root);
    chrome = { actionbar, sourcesBox };
    refreshChrome(state);
    lastMaterials = null;
    refreshSources(state, measured);
  }

  function refreshSources(state, measured) {
    if (!chrome || lastMaterials === state.materials) return;
    lastMaterials = state.materials;
    const section = sourcesSection(state, measured);
    chrome.sourcesBox.replaceChildren(...(section ? [section] : []));
    // 素材到达后重画引用区，“+ 引用素材”才有选项。
    for (const row of root.querySelectorAll(".shot")) {
      const index = Number(row.id.replace("shot-", ""));
      const shot = measured.shots[index];
      const cell = row.querySelector(".shot-claims");
      if (shot && cell) claimChips(cell, shot, measured.readOnly);
    }
  }

  function refreshChrome(state) {
    if (!chrome) return;
    const content = actionBarContent(state);
    chrome.actionbar.hidden = !content;
    chrome.actionbar.classList.toggle("is-dirty", state.dirty);
    chrome.actionbar.replaceChildren(...(content ?? []).flat().filter(Boolean));
  }

  window.addEventListener("resize", () => growAll(root));

  subscribe((state) => {
    const key = [state.source?.kind, state.source?.id, state.phase, state.structureVersion, state.phase === "running" ? state.records.length : ""].join("|");
    if (key !== lastKey) {
      lastKey = key;
      rebuild(state);
    } else if (chrome) {
      const measured = measure(state);
      timeline.update(timelineModel(state, measured));
      refreshChrome(state);
      refreshSources(state, measured);
    }
    if (state.view !== lastView) {
      lastView = state.view;
      growAll(root);
    }
  });
}
