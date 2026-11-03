// 文案与状态映射集中在这里，全站复用。

export const ACTION_LABELS = {
  search_materials: "检索素材",
  estimate_duration: "估算时长",
  check_rules: "检查规则",
  submit_script: "提交脚本",
  ask_user: "请求补充",
  report_failure: "报告失败",
};

export const STATUS_LABELS = {
  completed: "已完成",
  needs_input: "需要补充",
  failed: "失败",
  incomplete: "未完成",
  running: "生成中",
  crashed: "运行异常",
};

export const DURATION_LABELS = {
  pass: "通过",
  too_long: "超时长",
  too_short: "时长不足",
  error: "工具不可用",
  not_run: "未运行",
};

export const RULES_LABELS = {
  pass: "通过",
  fail: "未通过",
  error: "工具不可用",
  not_run: "未运行",
};

export const FIELD_LABELS = {
  topic: "主题",
  audience: "受众",
  platform: "平台",
  target_duration_sec: "目标时长",
  style: "风格",
  materials: "素材",
  other: "其他信息",
};

export const FAULT_TOOL_LABELS = {
  search_materials: "素材检索",
  estimate_duration: "时长估算",
  check_rules: "规则检查",
};

export const EXAMPLE_PRESETS = [
  { label: "正常生成", name: "01_normal" },
  { label: "缺时长", name: "02_missing_target" },
  { label: "无素材", name: "03_no_material" },
  { label: "工具恢复", name: "04_tool_fail_transient" },
  { label: "工具失败", name: "05_tool_fail_permanent" },
  { label: "超时长修正", name: "06_over_duration_fixed" },
  { label: "无法满足", name: "07_over_duration_infeasible" },
  { label: "规则冲突", name: "08_rule_conflict" },
];

export const PLATFORMS = ["抖音", "快手", "小红书", "视频号", "B 站"];
export const STYLES = ["轻松口语", "干货直给", "故事感"];

const TONES = {
  completed: "ok",
  pass: "ok",
  failed: "bad",
  fail: "bad",
  too_long: "bad",
  crashed: "bad",
  needs_input: "info",
  incomplete: "warn",
  too_short: "warn",
  error: "warn",
};

export function toneOf(value) {
  return TONES[value] ?? "";
}

export function badgeClass(value) {
  const tone = toneOf(value);
  return tone ? `badge badge-${tone}` : "badge";
}
