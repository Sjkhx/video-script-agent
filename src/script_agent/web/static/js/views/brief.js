// 左栏“新建”：收集需求和运行设置。主题或时长为空也允许提交，缺信息时由模型决定追问。

import { getExample } from "../api.js";
import { startGeneration } from "../actions.js";
import { h, icon } from "../dom.js";
import { EXAMPLE_PRESETS, FAULT_TOOL_LABELS, PLATFORMS, STYLES } from "../labels.js";
import { setState, subscribe } from "../store.js";

const refs = {};
const TARGET_CHIPS = [15, 30, 60];
const OFFLINE_DEFAULTS = {
  topic: "剪刀鱼的字幕功能",
  target_duration_sec: 30,
  audience: "短视频新手",
  platform: "抖音",
  style: "轻松口语",
};

function field(label, control, hint) {
  return h("label", { class: "field" }, h("span", { class: "field-label" }, label), control, hint);
}

function options(items, selected) {
  return items.map(({ value, label }) => h("option", { value, selected: value === selected }, label));
}

function updateTargetHint() {
  const raw = refs.target.value.trim();
  const value = Number(raw);
  if (!raw) {
    refs.targetHint.textContent = "未填写时，Agent 会先向你确认";
  } else if (!Number.isFinite(value) || value <= 0) {
    refs.targetHint.textContent = "无法识别为秒数，Agent 会先向你确认";
  } else {
    const low = Number((value * 0.8).toFixed(1));
    refs.targetHint.textContent = `合格范围 ${low}–${Number(value.toFixed(1))} 秒`;
  }
}

function updateModeUi() {
  const mock = refs.modeMock.checked;
  refs.mockBlock.hidden = !mock;
  refs.timesBlock.hidden = !refs.faultTool.value;
}

function collectBody() {
  const request = {};
  for (const name of ["topic", "audience", "platform", "style"]) {
    const value = refs[name].value.trim();
    if (value) request[name] = value;
  }
  const target = refs.target.value.trim();
  if (target) {
    const number = Number(target);
    request.target_duration_sec = Number.isFinite(number) ? number : target;
  }
  const mock = refs.modeMock.checked;
  const steps = Math.min(20, Math.max(1, Math.trunc(Number(refs.maxSteps.value)) || 10));
  refs.maxSteps.value = String(steps);
  return {
    request,
    mode: mock ? "mock" : "real",
    mock_script: mock ? refs.mockScript.value : null,
    data_set: refs.dataSet.value,
    fault: refs.faultTool.value
      ? { tool: refs.faultTool.value, times: refs.timesAlways.checked ? -1 : 1 }
      : null,
    max_steps: steps,
  };
}

export function fillBrief(values, fault, dataSet) {
  for (const name of ["topic", "audience", "platform", "style"]) {
    refs[name].value = values?.[name] ?? "";
  }
  refs.target.value = values?.target_duration_sec ?? "";
  if (fault !== undefined) {
    refs.faultTool.value = fault?.tool ?? "";
    refs.timesAlways.checked = fault?.times === -1;
    refs.timesOnce.checked = fault?.times !== -1;
  }
  if (dataSet) refs.dataSet.value = dataSet;
  if (fault?.tool || (dataSet && dataSet !== "default")) refs.settings.open = true;
  updateTargetHint();
  updateModeUi();
}

export function focusField(name) {
  const map = { target_duration_sec: refs.target, topic: refs.topic, audience: refs.audience, platform: refs.platform, style: refs.style };
  (map[name] ?? refs.topic).focus();
}

async function applyPreset(name) {
  try {
    const detail = await getExample(name);
    fillBrief(detail.input, detail.fault ?? null, detail.data_set);
    setState({ formError: null });
  } catch (error) {
    setState({ formError: error.message });
  }
}

export function renderBrief(container, meta, covers) {
  refs.topic = h("textarea", { class: "input", id: "field-topic", rows: 2, maxlength: 200, placeholder: "例如：剪刀鱼的字幕功能" });
  refs.target = h("input", { class: "input", id: "field-target", type: "text", inputmode: "decimal", autocomplete: "off", onInput: updateTargetHint });
  refs.targetHint = h("span", { class: "field-hint" });
  refs.audience = h("input", { class: "input", id: "field-audience", maxlength: 200, autocomplete: "off", placeholder: "例如：短视频新手" });
  refs.platform = h("input", { class: "input", id: "field-platform", maxlength: 200, autocomplete: "off", list: "platform-options" });
  refs.style = h("input", { class: "input", id: "field-style", maxlength: 200, autocomplete: "off", list: "style-options" });

  refs.modeReal = h("input", { type: "radio", name: "mode", value: "real", checked: meta.real_available, disabled: !meta.real_available, onChange: updateModeUi });
  refs.modeMock = h("input", { type: "radio", name: "mode", value: "mock", checked: !meta.real_available, onChange: updateModeUi });
  refs.mockScript = h("select", { class: "input", id: "field-mock" }, options(meta.mock_scripts.map((m) => ({ value: m.id, label: m.label }))));
  refs.mockBlock = h(
    "div",
    { class: "field" },
    h("label", { class: "field-label", for: "field-mock" }, "演示脚本"),
    refs.mockScript,
    h("span", { class: "field-hint" }, "离线演示的决策来自预设脚本，只验证流程，不代表真实模型效果。"),
  );
  refs.dataSet = h("select", { class: "input", id: "field-data" }, options(meta.data_sets.map((d) => ({ value: d.id, label: d.label }))));
  refs.faultTool = h(
    "select",
    { class: "input", id: "field-fault", onChange: updateModeUi },
    options([{ value: "", label: "不注入" }, ...meta.fault_tools.map((tool) => ({ value: tool, label: FAULT_TOOL_LABELS[tool] ?? tool }))]),
  );
  refs.timesOnce = h("input", { type: "radio", name: "fault-times", checked: true });
  refs.timesAlways = h("input", { type: "radio", name: "fault-times" });
  refs.timesBlock = h(
    "div",
    { class: "radio-row" },
    h("label", null, refs.timesOnce, "失败一次"),
    h("label", null, refs.timesAlways, "一直失败"),
  );
  refs.maxSteps = h("input", { class: "input", id: "field-steps", type: "number", min: 1, max: 20, value: String(meta.max_steps_default) });

  refs.settings = h(
    "details",
    { class: "settings" },
    h("summary", null, icon("chevron"), "运行设置"),
    h(
      "div",
      { class: "settings-body" },
      h(
        "div",
        { class: "field" },
        h("span", { class: "field-label" }, "模型"),
        h(
          "div",
          { class: "radio-row" },
          h("label", { class: meta.real_available ? "" : "is-disabled" }, refs.modeReal, "真实模型"),
          h("label", null, refs.modeMock, "离线演示"),
        ),
        meta.real_available ? null : h("span", { class: "field-hint" }, "需要先在 .env 配置 LLM_API_KEY 和 LLM_MODEL"),
      ),
      refs.mockBlock,
      field("素材库", refs.dataSet),
      h(
        "div",
        { class: "field" },
        h("label", { class: "field-label", for: "field-fault" }, "注入故障"),
        refs.faultTool,
        refs.timesBlock,
      ),
      field("步数上限", refs.maxSteps),
    ),
  );

  refs.submit = h("button", { class: "btn btn-primary btn-block", type: "submit" }, "生成脚本");
  refs.error = h("p", { class: "form-error", role: "alert", hidden: true });

  const form = h(
    "form",
    {
      class: "brief-body",
      novalidate: "novalidate",
      onSubmit(event) {
        event.preventDefault();
        startGeneration(collectBody());
      },
    },
    h(
      "div",
      { class: "field" },
      h("span", { class: "field-label" }, "快速填入"),
      h(
        "div",
        { class: "chips" },
        EXAMPLE_PRESETS.map(({ label, name }) =>
          h("button", { class: "chip", type: "button", title: covers[name] ?? label, onClick: () => applyPreset(name) }, label),
        ),
      ),
    ),
    field("主题", refs.topic),
    h(
      "div",
      { class: "field" },
      h("label", { class: "field-label", for: "field-target" }, "目标时长"),
      h(
        "div",
        { class: "target-row" },
        h("div", { class: "input-suffix" }, refs.target, h("span", null, "秒")),
        TARGET_CHIPS.map((value) =>
          h(
            "button",
            {
              class: "chip mono",
              type: "button",
              "aria-label": `目标时长 ${value} 秒`,
              onClick() {
                refs.target.value = value;
                updateTargetHint();
              },
            },
            String(value),
          ),
        ),
      ),
      refs.targetHint,
    ),
    field("受众", refs.audience),
    field("平台", refs.platform),
    h("datalist", { id: "platform-options" }, PLATFORMS.map((value) => h("option", { value }))),
    field("风格", refs.style),
    h("datalist", { id: "style-options" }, STYLES.map((value) => h("option", { value }))),
    refs.settings,
    refs.submit,
    refs.error,
  );

  container.append(form);
  if (!meta.real_available) fillBrief(OFFLINE_DEFAULTS);
  updateTargetHint();
  updateModeUi();

  subscribe((state) => {
    const running = state.phase === "running";
    refs.submit.disabled = running;
    refs.submit.textContent = running ? "生成中…" : "生成脚本";
    refs.error.hidden = !state.formError;
    refs.error.textContent = state.formError ?? "";
  });
}

export function setLeftTab(tab) {
  setState({ leftTab: tab });
}
