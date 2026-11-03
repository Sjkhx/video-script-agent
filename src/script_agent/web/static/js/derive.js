// 纯函数：从轨迹记录推导版本、时间码、统计和比例尺，不访问 DOM。

const DRAFT_ACTIONS = new Set(["estimate_duration", "check_rules", "submit_script"]);

export function draftOf(step) {
  if (!DRAFT_ACTIONS.has(step?.action)) return null;
  const args = step.args;
  if (!args || typeof args.title !== "string" || !Array.isArray(args.shots)) return null;
  return { title: args.title, shots: args.shots };
}

export function deriveVersions(records) {
  const versions = [];
  const byKey = new Map();
  for (const record of records) {
    if (record.type !== "step") continue;
    const draft = draftOf(record);
    if (!draft) continue;
    const key = JSON.stringify(draft);
    let version = byKey.get(key);
    if (!version) {
      version = { version: versions.length + 1, key, draft, estimate: null, rules: null };
      byKey.set(key, version);
      versions.push(version);
    }
    if (record.action === "estimate_duration") version.estimate = record.result;
    if (record.action === "check_rules") version.rules = record.result;
  }
  return versions;
}

export function retrievedIdsOf(records) {
  const ids = new Set();
  for (const record of records) {
    if (record.type !== "step" || record.action !== "search_materials") continue;
    if (!record.result?.ok) continue;
    for (const material of record.result.materials ?? []) ids.add(material.id);
  }
  return [...ids].sort();
}

function round2(value) {
  return Math.round(value * 100) / 100;
}

export function timecodes(durations) {
  let clock = 0;
  return durations.map((duration) => {
    const start = round2(clock);
    clock += duration ?? 0;
    return { start, end: round2(clock) };
  });
}

export function formatClock(seconds) {
  const minutes = Math.floor(seconds / 60);
  const rest = (seconds - minutes * 60).toFixed(2).padStart(5, "0");
  return `${String(minutes).padStart(2, "0")}:${rest}`;
}

export function formatSeconds(seconds) {
  return String(round2(seconds));
}

export function scaleMaxOf(target, total) {
  const candidates = [5, (total ?? 0) * 1.02];
  if (target) candidates.push(target * 1.15);
  return Math.max(...candidates);
}

export function scaleTicks(scaleMax, narrow) {
  let step = 30;
  if (scaleMax <= 12) step = 1;
  else if (scaleMax <= 40) step = 5;
  else if (scaleMax <= 120) step = 10;
  if (narrow) step *= 2;
  const ticks = [];
  for (let value = 0; value <= scaleMax + 1e-9; value += step) ticks.push(value);
  return ticks;
}

export function statsOf(records, result) {
  let rounds = 0;
  let calls = 0;
  let tokens = 0;
  const usageByRound = new Map();
  let endTokens = null;
  for (const record of records) {
    if (record.type === "run_end") endTokens = record.total_tokens ?? null;
    if (record.type !== "step" && record.type !== "note") continue;
    rounds = Math.max(rounds, record.round ?? 0);
    if (record.type === "step") {
      calls += 1;
      if (record.usage && !usageByRound.has(record.round)) usageByRound.set(record.round, record.usage);
    }
  }
  for (const usage of usageByRound.values()) {
    tokens += (usage.prompt_tokens ?? 0) + (usage.completion_tokens ?? 0);
  }
  return {
    rounds: result?.steps_used ?? rounds,
    calls: result?.tool_calls_used ?? calls,
    tokens: endTokens ?? tokens,
  };
}

export function formatTime(iso) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const pad = (value) => String(value).padStart(2, "0");
  return `${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}
