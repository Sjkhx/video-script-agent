// 时间线：片段长度与秒数成正比，标出目标线和合格区，超时长部分用红色斜纹。

import { formatSeconds, scaleMaxOf, scaleTicks } from "../derive.js";
import { h } from "../dom.js";
import { DURATION_LABELS, toneOf } from "../labels.js";

const COMPACT_BELOW_PX = 44;
const narrowQuery = window.matchMedia("(max-width: 639px)");

function verdictText(model) {
  const { verdict, overflow, shortfall, target, total } = model;
  if (model.stale) return "待校验";
  if (verdict === "too_long") return `超出 ${formatSeconds(overflow ?? 0)}s`;
  if (verdict === "too_short") return `不足 ${formatSeconds(shortfall ?? 0)}s`;
  if (verdict === "pass") return "通过";
  if (total === null) return "未估算";
  if (target === null) return "缺少目标时长";
  return "未估算";
}

function versionsBar(versions) {
  if (!versions.length) return h("div", { class: "tl-versions" });
  const items = [];
  versions.forEach((version, index) => {
    if (index) items.push(h("span", { class: "tl-arrow" }, "→"));
    const estimate = version.estimate;
    const verdict = estimate?.ok ? estimate.verdict : estimate ? "error" : "not_run";
    const tone = toneOf(verdict);
    items.push(
      h(
        "span",
        { class: "tl-version mono" },
        `v${version.version}`,
        estimate?.ok ? ` ${formatSeconds(estimate.total_duration_sec)}s` : "",
        h("span", { class: tone ? `badge badge-${tone}` : "badge" }, DURATION_LABELS[verdict] ?? verdict),
      ),
    );
  });
  return h("div", { class: "tl-versions", "aria-label": "脚本版本的时长变化" }, items);
}

function percent(value, scaleMax) {
  return `${(value / scaleMax) * 100}%`;
}

function build(model, { onClipClick, onClipHover }) {
  const { target, total, clips, showReadout } = model;
  const scaleMax = scaleMaxOf(target, total);
  const ticks = scaleTicks(scaleMax, narrowQuery.matches);
  const flagSpan = (narrowQuery.matches ? 0.2 : 0.1) * scaleMax;
  const flagFlipped = Boolean(target) && target / scaleMax < 0.2;
  const hiddenByFlag = (value) => {
    if (!target) return false;
    return flagFlipped
      ? value >= target && value <= target + flagSpan
      : value >= target - flagSpan && value <= target + flagSpan * 0.1;
  };

  const track = h("div", { class: "tl-track" });
  if (target) {
    track.append(
      h("div", {
        class: "tl-window",
        style: {
          left: percent(target * 0.8, scaleMax),
          width: percent(target * 0.2, scaleMax),
        },
      }),
    );
  }

  let clock = 0;
  clips.forEach((clip) => {
    const element = h(
      "button",
      {
        class: `tl-clip${clip.position % 2 ? " is-even" : ""}${clip.cited ? " is-cited" : ""}`,
        type: "button",
        title: clip.title,
        "aria-label": clip.title,
        style: {
          left: percent(clock, scaleMax),
          width: `calc(${percent(clip.duration, scaleMax)} - 1px)`,
        },
        onClick: () => onClipClick(clip.index),
        onMouseenter: () => onClipHover(clip.index, true),
        onMouseleave: () => onClipHover(clip.index, false),
      },
      h("b", null, clip.label),
      h("span", null, `${formatSeconds(clip.duration)}s`),
    );
    track.append(element);
    clock += clip.duration;
  });

  if (target && total !== null && total > target) {
    track.append(
      h("div", {
        class: "tl-overflow",
        style: {
          left: percent(target, scaleMax),
          width: percent(total - target, scaleMax),
        },
      }),
    );
  }

  const plot = h(
    "div",
    { class: "tl-plot" },
    h(
      "div",
      { class: "tl-ruler", "aria-hidden": "true" },
      ticks.map((value) =>
        h(
          "div",
          { class: "tl-tick", style: { left: percent(value, scaleMax) } },
          // 目标旗标左侧的刻度数字会被挡住一半，干脆不画。
          hiddenByFlag(value) ? null : h("span", null, String(value)),
        ),
      ),
    ),
    track,
  );
  if (target) {
    plot.append(
      h(
        "div",
        { class: "tl-target", style: { left: percent(target, scaleMax) } },
        h("span", { class: `tl-flag${flagFlipped ? " is-flipped" : ""}` }, `目标 ${formatSeconds(target)}s`),
      ),
    );
  }

  const head = h(
    "div",
    { class: "tl-head" },
    versionsBar(model.versions),
    showReadout
      ? h(
          "div",
          { class: "tl-readout" },
          h("div", { class: "tl-total mono" }, total === null ? "—" : `${total.toFixed(2)}s`),
          h("div", { class: "tl-verdict" }, verdictText(model)),
        )
      : null,
  );

  const legend = h(
    "div",
    { class: "tl-legend", "aria-hidden": "true", hidden: !showReadout },
    h("span", null, h("i", { class: "swatch-window" }), "合格区"),
    h("span", null, h("i", { class: "swatch-cited" }), "有素材依据"),
    h("span", null, h("i", { class: "swatch-over" }), "超时长"),
  );

  return { root: h("section", { class: "tl", "aria-label": "时间线" }, head, plot, legend), track };
}

// 片段宽度只有布局后才知道；太窄时隐藏文字，只留色块。
function updateCompact(track) {
  for (const clip of track.querySelectorAll(".tl-clip")) {
    clip.classList.toggle("is-compact", clip.offsetWidth < COMPACT_BELOW_PX);
  }
}

export function createTimeline(handlers) {
  const container = h("div");
  let lastKey = null;
  let lastModel = null;
  let observer = null;

  function draw(model) {
    observer?.disconnect();
    const { root, track } = build(model, handlers);
    container.replaceChildren(root);
    observer = new ResizeObserver(() => updateCompact(track));
    observer.observe(track);
  }

  narrowQuery.addEventListener("change", () => {
    if (lastModel) draw(lastModel);
  });

  return {
    element: container,
    update(model) {
      const key = JSON.stringify([model.target, model.total, model.verdict, model.stale, model.clips, model.versions.map((v) => [v.version, v.estimate?.total_duration_sec, v.estimate?.verdict, v.estimate?.ok])]);
      if (key === lastKey) return;
      lastKey = key;
      lastModel = model;
      draw(model);
    },
  };
}
