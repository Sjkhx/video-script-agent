// 全站都用 h() 构造 DOM：文本一律走文本节点，模型和用户的内容不会被当成 HTML。

const SVG_NS = "http://www.w3.org/2000/svg";
const BOOLEAN_PROPS = new Set(["disabled", "checked", "selected", "hidden", "open", "readOnly"]);
const VALUE_PROPS = new Set(["value", "defaultValue"]);

function appendChildren(parent, children) {
  for (const child of children) {
    if (child === null || child === undefined || child === false) continue;
    if (Array.isArray(child)) {
      appendChildren(parent, child);
    } else if (child instanceof Node) {
      parent.append(child);
    } else {
      parent.append(document.createTextNode(String(child)));
    }
  }
}

export function h(tag, props, ...children) {
  const element = document.createElement(tag);
  for (const [name, value] of Object.entries(props ?? {})) {
    if (value === null || value === undefined) continue;
    if (name === "class") {
      if (value) element.className = value;
    } else if (name === "dataset") {
      Object.assign(element.dataset, value);
    } else if (name === "style") {
      for (const [key, item] of Object.entries(value)) element.style[key] = item;
    } else if (name.startsWith("on") && typeof value === "function") {
      element.addEventListener(name.slice(2).toLowerCase(), value);
    } else if (BOOLEAN_PROPS.has(name) || VALUE_PROPS.has(name)) {
      element[name] = value;
    } else {
      element.setAttribute(name, String(value));
    }
  }
  appendChildren(element, children);
  return element;
}

export function icon(name, className = "") {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("class", `icon ${className}`.trim());
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  const use = document.createElementNS(SVG_NS, "use");
  use.setAttribute("href", `#icon-${name}`);
  svg.append(use);
  return svg;
}

export function autoGrow(textarea) {
  textarea.style.height = "auto";
  textarea.style.height = `${textarea.scrollHeight + 2}px`;
}
