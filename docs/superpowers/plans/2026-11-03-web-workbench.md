# 脚本剪辑台（Web 工作台）施工方案

> **给执行方：** 按 Task 顺序逐个完成，步骤用 checkbox（`- [ ]`）跟踪。本文已经定好接口、字段、样式和文案，照做即可；未定义又影响验收的问题，停下来报告，不要自行改需求。

**Goal：** 为现有短视频脚本 Agent 加一个本地 Web 工作台：填写需求、实时看模型决策、编辑脚本并重新校验、导出结果、回放已提交的真实运行记录。

**Architecture：** 用 Python 标准库 `http.server.ThreadingHTTPServer` 做一层很薄的外壳，复用 `run_once`、`estimate_duration`、`check_rules`、`render_script_markdown`，不改 Agent 的决策逻辑。所有路由集中在一个不依赖 socket 的 `dispatch()` 函数里，HTTP Handler 只做读写。Agent 在后台线程运行，步骤通过 SSE 推给前端。前端是原生 ES Modules，没有构建步骤，也不依赖外部资源。

**Tech Stack：** Python 3.12 标准库 + 现有的 pydantic（请求校验）；前端 HTML + CSS + 原生 JS。**不新增任何依赖，`requirements.txt` 不变。**

**为什么不用 FastAPI：** 这是只监听本机的单用户工具，标准库够用；不增加安装依赖；也不依赖 asyncio。当前开发环境限制了回环 socket，`asyncio` 建事件循环会卡死，所以 FastAPI、uvicorn 和 `TestClient` 在这里都无法运行。请不要改用它们，也不要在测试里使用 `asyncio`。

**Spec：** 本文“设计规范”和“接口规范”两节。

## 全局约束

- **不改决策：** 不修改 `agent.py`、`registry.py`、`tools.py`、`prompts.py`、`models.py`、`llm.py`、`render.py`、`cli.py`。核心代码只允许改 `trace.py` 和 `app.py`，改动范围见 Task 1。
- **不碰真实记录：** 不修改 `examples/real/`、`examples/cases.json`、`examples/inputs/`、`data/`。
- **不调用真实模型：** 实现和测试全程离线，不读取、不打印 `.env` 的内容。
- **不提交：** 不执行 `git commit`、`git push`、`git add`。所有改动留在工作区，由本人审查后决定。
- **不引入：** 不用 npm、构建工具、CDN、外部字体或外部图片，不加任何新依赖。
- **测试不走网络：** 当前环境里本机回环连接会被拒绝，测试通过 `dispatch()` 或内存假 socket 进行。唯一需要真实 socket 的测试，在回环不可用时跳过。
- **安全：**
  - 只监听 `127.0.0.1`，提供 `--port`，不提供 `--host`。
  - 任何接口都不返回密钥和 `LLM_BASE_URL`。
  - 客户端只传白名单 ID，不传文件路径。
  - 模型和用户文本一律通过 `textContent` 或 `value` 显示，全部静态文件禁止出现 `innerHTML`、`outerHTML`、`insertAdjacentHTML`、`document.write`、`eval(`。
- **兼容：** 现有 240 个测试必须继续通过。新代码的注释和文案都用中文，标识符用英文，风格贴近现有代码。
- **诚实：** 只有 Agent 或校验接口真正返回了结果，界面才能显示对应状态。不写假数据；Mock 必须明确标记。

## Review Focus

下面五类情况最容易在真实使用中出问题，每条都已加入对应 Task 的测试或验收项：

1. **模型文本里含 HTML 或脚本：** 只能显示为普通文字（Task 2 静态扫描、Task 3 的 `h()` 约定）。
2. **运行中刷新页面或 SSE 断线：** 用 `#run=<id>` 和 `Last-Event-ID` 接回同一个运行（Task 2、Task 4）。
3. **路径穿越和非法 ID：** 运行 ID、示例名、素材库都走白名单或正则（Task 2）。
4. **用户把内容清空或写得很长：** 校验接口返回 422 和可读的中文原因，前端定位到对应分镜（Task 2、Task 5）。
5. **窄屏和超长无空格文本：** 不出现横向滚动（Task 3、Task 5）。

---

## 设计规范

### 产品概念

产品名“脚本剪辑台”。界面像一张剪辑台：脚本是一条可以量长度的时间线，模型的决策是旁边的场记。**标志性元素是时间线**：每个分镜是一段长度与秒数成正比的片段，轨道上标出目标线和合格区，超时长的部分用红色斜纹显示。它把这个 Agent 最核心的约束直接画了出来。

明确不要：渐变背景、毛玻璃、紫色系、大圆角卡片、彩色左边框卡片、阴影堆叠、emoji、插画、营销式文案、感叹号、“AI 智能”字样。

### Design Tokens

`app.css` 开头原样写入（只有深色主题，这是有意的选择）：

```css
:root {
  color-scheme: dark;

  --bg-0: #101114;
  --bg-1: #17181C;
  --bg-2: #1F2126;
  --bg-3: #2A2C33;
  --line: #2E3038;
  --line-strong: #6A6D78;

  --text-1: #ECEDEF;
  --text-2: #AEB1B9;
  --text-3: #8C8F99;

  --accent: #F4B740;
  --accent-hover: #FFC95E;
  --accent-ink: #1B1405;
  --accent-soft: rgba(244, 183, 64, 0.14);

  --ok: #5CC98A;
  --ok-bg: #15291F;
  --bad: #F4806F;
  --bad-bg: #321A17;
  --warn: #F4B740;
  --warn-bg: #2E2410;
  --info: #86BBF5;
  --info-bg: #17263A;

  --clip-a: #34404E;
  --clip-b: #453F4F;

  --font-ui: "PingFang SC", "Microsoft YaHei UI", "Microsoft YaHei", "Noto Sans SC", "Source Han Sans SC", system-ui, sans-serif;
  --font-mono: "JetBrains Mono", "Cascadia Mono", "SF Mono", Consolas, "Liberation Mono", monospace;

  --radius-s: 4px;
  --radius-m: 6px;
  --gutter: 16px;
  --topbar-h: 48px;
  --ease: 120ms ease-out;
}
```

- **字号：** 只用 12、13、14、15、16、20、28px。正文 14px，行高 1.6。
- **面板标题：** 12px、字重 600、`letter-spacing: 0.04em`、`--text-2`。
- **数字、时间码、工具名、素材 ID：** `--font-mono`，并设 `font-variant-numeric: tabular-nums`。
- **边框和层次：** 面板之间只用 1px `--line` 分隔。不用卡片阴影；弹层才可用 `box-shadow: 0 8px 24px rgba(0,0,0,.4)`。
- **圆角：** 输入框、徽章、按钮用 `--radius-s`；片段和面板内区块用 `--radius-m`。
- **动效：** 只有 120ms 的颜色和边框过渡、新轨迹项 160ms 淡入、运行中圆点呼吸。`prefers-reduced-motion: reduce` 时全部关闭。
- **焦点：** 所有可交互元素 `:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }`。
- **文本溢出：** 全局 `overflow-wrap: anywhere`；`body` 不出现横向滚动。

### 页面布局

全屏应用：`body` 高 `100dvh`，顶栏固定，下方三栏各自滚动。

```text
┌─────────────────────────────────────────────────────────────┐
│ 顶栏 48px：字标 ｜ 运行状态 ｜ 模型状态                      │
├───────────┬──────────────────────────────┬──────────────────┤
│ 左栏 320px│ 中栏 minmax(0, 1fr)           │ 右栏 380px       │
│ 新建/记录 │ 状态条、时间线、分镜编辑      │ 决策轨迹         │
└───────────┴──────────────────────────────┴──────────────────┘
```

- **宽度 ≥ 1100px：** 三栏同时显示，隐藏视图切换。
- **宽度 < 1100px：** 顶栏下方显示三段切换“需求 / 脚本 / 轨迹”，一次只显示一个面板，内容最大宽度 860px 并居中，左右留 `--gutter`。实现方式：`body[data-view="brief|script|trace"]` 配合媒体查询。
- **宽度 < 640px：** 顶栏只留字标和状态；按钮和输入框最小高度 44px；分镜里的画面和旁白改为上下堆叠。
- 开始运行后，窄屏自动切到“轨迹”；运行结束切到“脚本”。

### 文案与映射

`js/labels.js` 里集中定义，全站复用：

| 键 | 文案 |
|---|---|
| `search_materials` | 检索素材 |
| `estimate_duration` | 估算时长 |
| `check_rules` | 检查规则 |
| `submit_script` | 提交脚本 |
| `ask_user` | 请求补充 |
| `report_failure` | 报告失败 |
| `completed` | 已完成 |
| `needs_input` | 需要补充 |
| `failed` | 失败 |
| `incomplete` | 未完成 |
| `running` | 生成中 |
| `crashed` | 运行异常 |
| duration `pass` / `too_long` / `too_short` / `error` / `not_run` | 通过 / 超时长 / 时长不足 / 工具不可用 / 未运行 |
| rules `pass` / `fail` / `error` / `not_run` | 通过 / 未通过 / 工具不可用 / 未运行 |

徽章颜色：`completed`、`pass` 用 ok；`failed`、`fail`、`too_long`、`crashed` 用 bad；`needs_input` 用 info；`incomplete`、`too_short`、`error` 用 warn；其余用 `--bg-3` 配 `--text-2`。徽章永远带文字，不能只靠颜色。

### 顶栏

- **左：** 字标。14×14 的内联 SVG（场记板上的两道平行斜线，`--accent`）加“脚本剪辑台”（14px，字重 600）。
- **中：** 运行状态，`aria-live="polite"`。
  - 空闲：`待开始`
  - 运行中：呼吸圆点 + `第 3 / 10 轮 · 模型决策中`
  - 结束：状态徽章 + 一句结论
- **右：** 模型状态。已配置时显示 `真实模型` + 模型名（等宽）；未配置时显示 `未配置模型，可用离线演示`（`--text-3`）。

### 左栏

顶部切换“新建 / 记录”。

**新建**（`<form>`）：

1. **快速填入：** 一行可换行的小标签，点击后调用 `GET /api/examples/{name}`，把 `input`、`fault`、`data_set` 填进表单，但不自动运行。标签与示例对应：`正常生成`=01、`缺时长`=02、`无素材`=03、`工具恢复`=04、`工具失败`=05、`超时长修正`=06、`无法满足`=07、`规则冲突`=08。标签的 `title` 用 `covers`。
2. **主题**：两行 `textarea`，占位 `例如：剪刀鱼的字幕功能`，最长 200 字。
3. **目标时长**：数字输入加后缀“秒”；旁边三个快捷标签 `15`、`30`、`60`。下方提示随输入变化：`合格范围 24–30 秒`（目标 × 80% 到目标，最多一位小数）；为空时显示 `未填写时，Agent 会先向你确认`。
4. **受众**：输入框，占位 `例如：短视频新手`。
5. **平台**：输入框加 `datalist`（抖音、快手、小红书、视频号、B 站）。
6. **风格**：输入框加 `datalist`（轻松口语、干货直给、故事感）。
7. **运行设置**（`<details>`，默认收起）：
   - **模型：** 单选“真实模型 / 离线演示”。未配置模型时默认离线演示，“真实模型”禁用并显示 `需要先在 .env 配置 LLM_API_KEY 和 LLM_MODEL`。
   - **演示脚本：** 选离线演示时显示，下拉来自 `meta.mock_scripts`，下方固定提示 `离线演示的决策来自预设脚本，只验证流程，不代表真实模型效果。`
   - **素材库：** 下拉来自 `meta.data_sets`。
   - **注入故障：** 下拉“不注入 / 素材检索 / 时长估算 / 规则检查”；选中后再选“失败一次 / 一直失败”。
   - **步数上限：** 数字输入，1–20，默认 10。
8. **主按钮**（全宽，`--accent` 底，`--accent-ink` 字，高 40px）：`生成脚本`；运行中禁用并显示 `生成中…`。

**前端不拦截主题或时长为空的提交。** 缺信息时由模型决定追问，这是题目的验收路径。字段为空时只显示上面的提示。

**记录**：

- **已提交的真实运行：** 来自 `GET /api/examples`。每行显示编号和 `covers`、状态徽章、tokens（等宽，千分位）。
- **本地运行：** 来自 `GET /api/runs`。每行显示主题（无主题显示 `未填写主题`）、时间（`MM-DD HH:mm`）、状态徽章，Mock 运行加 `演示` 小徽章。
- 点击后加载到中栏和右栏，并更新地址栏 hash：`#example=01_normal` 或 `#run=<id>`。当前项用 `--bg-3` 背景标出。

### 中栏

从上到下依次是：

**1. Mock 横条**（`mode === "mock"` 时一直显示）：`--warn-bg` 底，`--warn` 字：`[MOCK] 本次模型决策来自预设脚本，只验证流程，不证明真实模型效果。`

**2. 状态条**（`--bg-2` 底，1px 边框，图标 + 文字，**不用左侧彩色边框**）：

| 状态 | 主文案 | 内容 |
|---|---|---|
| `completed` | `脚本已通过时长和规则检查` | `25.5 秒 / 目标 30 秒 · 6 个分镜 · 引用 P01、P02、P03` |
| `needs_input` | `Agent 需要你补充信息` | `ask_user` 参数里的 `reason` 和 `questions` 列表；按钮 `去补充`（切回新建并聚焦缺失字段）。缺 `materials` 时加一句 `素材库不足，需要在 data/materials.json 补充后重试，或换一个主题。` |
| `failed` | `未能生成合格脚本` | `result.message`，并用列表显示 `report_failure` 的 `unmet_requirements`；有草稿时加 `下面是最后一版草稿，未通过检查，不可直接使用。` |
| `incomplete` | `达到上限，任务未完成` | `result.message` |
| `crashed` | `运行异常` | 后端返回的错误文字 |
| 运行中 | `模型正在决策` | 最新一步的摘要 |

**3. 时间线**（规范见下）。

**4. 标题**：单行输入框，20px，字重 600，无边框（聚焦时显示边框）；右侧等宽计数 `12 / 20`，超过 20 变 `--bad`。

**5. 分镜列表**：每个分镜一行，网格 `96px minmax(0,1fr) minmax(0,1fr)`，行与行之间 1px `--line`。

- **第 1 列：** 序号（等宽 16px，`01`）；时间码 `00:04.25–00:08.75`（等宽 12px，`--text-3`）；时长 `4.5s`；最下面是删除按钮（图标，`aria-label="删除分镜 1"`）。
- **第 2 列“画面”、第 3 列“旁白”：** 列标题 12px；`textarea` 根据内容自动增高（`input` 事件里把 `height` 设为 `scrollHeight`）。旁白字号 15px，行高 1.7。
- **第 3 列下方：引用区：** 每条 claim 一个标签 `P01 · 支持字幕`（ID 等宽），带移除按钮 ×；最后是 `+ 引用素材`，点开后是一个 `select`，选项为本次运行已检索到的素材事实（`P01 · 支持字幕`），选中后加入 claims。
- **违规提示：** 校验或最后一次 `check_rules` 的 `violations` 中，`shot_id` 等于这一镜的显示在该行下方：`--bad` 文字，先写 `detail`，后面跟等宽小字 `code`。`shot_id` 为 null 的显示在标题下方。
- **修改后：** 这一镜的时长和时间码变成 `--text-3`，并显示 `待校验`。
- **列表底部：** 文字按钮 `+ 添加分镜`。

分镜增删后，提交前按顺序重排 `id` 为 1…n。

**6. 风险**：有 `risks` 时显示列表，标题“风险”。

**7. 素材来源**：表格，列为 `ID`、`事实`。内容来自 `GET /api/materials`，只显示 `result.source_ids` 或校验结果涉及的素材。

**8. 底部操作条**（中栏内 `position: sticky; bottom: 0`，`--bg-1` 底，上边框）：

- **有未校验修改：** `有未校验的修改` + 主按钮 `重新校验` + 次按钮 `撤销修改`。
- **校验通过：** `修改后的脚本已通过校验`（`--ok`）+ 导出按钮。
- **校验未通过：** `未通过：时长超出 3.5 秒，规则 2 项`（`--bad`，只列实际存在的问题）+ 导出按钮，导出内容带未通过标记。
- **未修改：** 导出按钮 `复制 Markdown`、`下载 .md`、`下载 .json`。
- 没有任何脚本时不显示。

导出内容规则：
- `.md`：未修改时用接口返回的 `markdown`；校验后用校验接口返回的 `markdown`；有未校验修改时禁用导出，`title` 写 `请先重新校验`。
- `.json`：未修改时是原始 `result`，校验后是校验接口返回的 `result`。
- 文件名：`<title 或 script>.md`，并去掉文件名非法字符 `\/:*?"<>|`。

**空状态**（没有加载任何内容）：一条空的时间线轨道（只有刻度，目标线不显示），下面一行 `还没有脚本`（16px）和一行 `在左侧填写需求开始生成，或打开一条已提交的真实运行记录。`（`--text-2`），再加次按钮 `打开 01 正常生成`。

### 时间线规范

容器内容：

- **上方一行：** 左边是版本条，右边是总时长读数。
- **读数：** 等宽 28px `25.50s`，下方 12px 判定文字：`通过` / `超出 10.25s` / `不足 2s` / `待校验` / `未估算`。
- **版本条：** 每一版脚本一个小标签，用 `→` 连接：`v1 40.25s 超时长 → v2 25.5s 通过`。颜色按判定。版本来自轨迹记录（见 `derive.js`）。没有版本时不显示。
- **轨道：** 高 56px，`--bg-2` 底，`--radius-m`。

比例尺：`scaleMax = max(target × 1.15, total × 1.02, 5)`；位置 = `秒 / scaleMax × 100%`。

依次绘制：

1. **刻度尺**（轨道上方 18px）：步长按 `scaleMax` 选：≤12 用 1 秒，≤40 用 5 秒，≤120 用 10 秒，否则用 30 秒。每个刻度一条 4px 短线和等宽 11px 秒数；窄屏（<640px）步长加倍。
2. **合格区：** `[target × 0.8, target]`，背景 `--accent-soft`，贯穿轨道高度。
3. **片段：** 每个分镜一段，绝对定位，段间留 1px。奇偶交替 `--clip-a`、`--clip-b`。有 claims 的片段顶部有 3px `--accent` 条（表示有素材依据）。宽度大于 44px 时显示 `01` 和 `4.25s`（等宽 12px），否则不显示文字。`title` 写 `分镜 1 · 4.25 秒 · 引用 P01`。片段是 `<button>`：点击后中栏滚动到该分镜并短暂高亮；悬停时同步高亮对应分镜行。
4. **超出部分：** 超过目标线的片段部分叠加红色斜纹：`repeating-linear-gradient(135deg, var(--bad) 0 6px, transparent 6px 12px)`，透明度 0.55。
5. **目标线：** 位于 `target`，2px `--accent`，贯穿轨道和刻度尺；顶部小旗 `目标 30s`（`--accent` 底，`--accent-ink` 字，等宽 11px）。

轨道下方图例（12px，`--text-3`）：`合格区` 色块、`有素材依据` 色块、`超时长` 色块。

没有目标时长时：不画合格区和目标线，读数下方写 `缺少目标时长`。

时长数据来源优先级：最近一次校验结果 > 最终 `result.shots` > 该版草稿对应的 `estimate_duration` 结果 > 无数据（片段不画，只显示 `未估算`）。

### 右栏：决策轨迹

**头部：** `决策轨迹`（面板标题）+ 右侧等宽 `7 / 10 轮 · 11 次调用 · 37,210 tokens`。

**列表：** 按 `round` 分组，组头 `第 3 轮`（12px，`--text-3`）。每步一个条目，左侧 8px 圆点加贯穿的 1px 竖线（`--line`），圆点颜色按结果：成功 `--ok`，业务未通过 `--warn`，工具报错 `--bad`，终止动作 `--accent`。

条目内容：

- **第一行：** 动作中文名（14px，字重 600）+ 工具名（等宽 12px，`--text-3`）+ 结果徽章。
- **第二行：** 关键信息：
  - `search_materials`：`查询：字幕` + 命中素材 ID 标签；0 条时 `没有命中`。
  - `estimate_duration`：`总时长 40.25s / 目标 30s` + 判定徽章。
  - `check_rules`：`通过`，或 `未通过 · 5 项`，并列出前 3 条 `detail`，超出部分写 `还有 2 项`。
  - `submit_script`：`提交通过`，或被拒时列出 `error.reasons`。
  - `ask_user`：`questions` 列表。
  - `report_failure`：`reason`。
  - 工具报错：`错误码` + `message` + `可重试 N 次`（`retries_left`）。
- **第三行：** `依据` 小标签 + `decision_note`（`--text-2`）。
- **标记：** `injected_fault` 为真时加 `故障注入` 徽章（bad 描边）；`GATE_REJECTED` 时加 `被把关拒绝` 徽章。
- **折叠区：** `查看参数和返回` 文字按钮，展开后是两块 `<pre>`（等宽 12px，`max-height: 280px`，可滚动，`JSON.stringify(x, null, 2)`，用 `textContent`）。

`note` 记录显示为警告条目：`模型没有调用工具`，后面跟 `detail`。

运行中列表末尾有一个占位条目：呼吸圆点 + `模型决策中…`；新记录出现时滚动到底部，但用户向上滚动过就不再自动滚动。

列表为空且未运行时显示：`运行后，这里会显示模型每一步的动作、观察结果和决策依据。`

### 前端代码结构

```text
src/script_agent/web/static/
  index.html        # 三栏骨架、SVG sprite
  app.css
  js/
    main.js         # 启动、hash 路由、连接各视图
    api.js          # fetch 封装与 SSE
    dom.js          # h() 元素构造
    labels.js       # 文案映射
    derive.js       # 纯函数：版本、时间码、统计、比例尺
    store.js        # 全局状态与订阅
    views/brief.js  # 左栏新建
    views/history.js# 左栏记录
    views/editor.js # 中栏
    views/timeline.js
    views/trace.js  # 右栏
```

- **`dom.js`：** `h(tag, props, ...children)`。字符串子节点用 `document.createTextNode`；`props` 支持 `class`、`dataset`、`on*`、`aria-*`、属性和 `style` 对象（通过 `element.style[k] = v`）。全站都用它构造 DOM。
- **`store.js`：**

```js
// 只有这些字段；视图只通过 setState 修改，再由订阅者重绘。
{
  meta: null,
  view: "script",           // 窄屏当前面板
  source: null,             // {kind: "run"|"example", id}
  phase: "idle",            // idle | running | done
  mode: null,               // "real" | "mock"
  request: null,
  records: [],              // 轨迹记录，含 run_start/step/note/run_end
  result: null,             // AgentResult
  markdown: null,
  error: null,              // crashed 文案
  draft: null,              // 正在编辑的 {title, shots}
  originalDraft: null,      // 用于撤销
  dirty: false,
  verification: null,       // 最近一次校验响应
  materials: [],            // 当前素材库
  retrievedIds: [],         // 本次运行检索到的素材 ID
}
```

- **保留焦点：** `editor.js` 只在分镜结构变化（加载、增删分镜、校验结果返回）时重建列表。`textarea` 的 `input` 事件只更新 `state.draft` 和 `dirty`，并局部刷新底部操作条和时间线读数，不能重建正在输入的 `textarea`。
- **`derive.js` 的纯函数（导出，供 Task 5 验证）：**

```js
draftOf(step)                // 从 estimate/check/submit 步骤的 args 取 {title, shots}；其他动作返回 null
deriveVersions(records)      // [{version, key, draft, estimate, rules}]；key = JSON.stringify(draft)，同内容归一版
retrievedIdsOf(records)      // 所有 ok 的 search_materials 结果里的素材 ID，去重升序
timecodes(durations)         // [{start, end}]，累加，保留两位
formatClock(seconds)         // 4.25 → "00:04.25"；65 → "01:05.00"
scaleTicks(scaleMax, narrow) // 刻度秒数数组
statsOf(records, result)     // {rounds, calls, tokens}，tokens 取 run_end；运行中按轮去重累加 usage
```

- **加载规则：**
  - 运行结束或打开记录时：`result.shots` 优先作为编辑草稿；没有 shots 但有 `unverified_draft` 时用草稿（`failed`、`incomplete`）；都没有时不显示编辑器。
  - 运行中：只读显示最新版本草稿，不可编辑。
  - 启动时读 hash：`#run=<id>` 请求 `GET /api/runs/{id}`，如果 `status === "running"` 就接 SSE 继续；`#example=<name>` 打开示例。
  - 从记录加载到新内容前，如有未校验修改，用 `window.confirm("有未校验的修改，确定放弃吗？")`。

---

## 接口规范

错误统一为 `{"detail": {"code": "...", "message": "中文说明"}}`。请求体校验失败返回 422 `INVALID_REQUEST`，`message` 写明字段和原因；JSON 解析失败返回 400 `INVALID_JSON`；未知路径 404 `NOT_FOUND`；方法不对 405 `METHOD_NOT_ALLOWED`。所有 JSON 响应都是 UTF-8。

所有请求都要通过这些检查：

- `Host` 的主机名必须是 `127.0.0.1`、`localhost` 或 `[::1]`，否则 400 `BAD_HOST`（防 DNS 重绑定）。
- POST 的 `Content-Type` 必须是 `application/json`（允许带 charset），否则 415 `UNSUPPORTED_MEDIA_TYPE`；如果带 `Origin`，其主机和端口必须等于 `Host`，否则 403 `BAD_ORIGIN`（防其他网站跨站触发运行）。
- 请求体最大 1 MiB，超出返回 413 `BODY_TOO_LARGE`。

所有响应都带 `Content-Security-Policy: default-src 'self'; img-src 'self' data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'` 和 `X-Content-Type-Options: nosniff`。动态元素的样式通过 `element.style` 设置，这不受 CSP 限制，因此不需要 `unsafe-inline`。

```text
GET  /api/meta
GET  /api/materials?data_set=default
GET  /api/examples
GET  /api/examples/{name}
GET  /api/runs
POST /api/runs
GET  /api/runs/{run_id}
GET  /api/runs/{run_id}/events
POST /api/verify
GET  /                       → 静态文件
```

**`GET /api/meta`**

```json
{
  "real_available": true,
  "model": "deepseek-v4.1-flash",
  "max_steps_default": 10,
  "max_tool_calls": 20,
  "max_target_sec": 600,
  "fault_tools": ["search_materials", "estimate_duration", "check_rules"],
  "data_sets": [{"id": "default", "label": "默认素材"}, {"id": "no_subtitle", "label": "缺字幕素材（无 P01）"}],
  "mock_scripts": [{"id": "01_normal", "label": "正常路径"}, {"id": "06_over_duration_fixed", "label": "先超时长再修正"}]
}
```

`real_available` 为真的条件：注入了 `llm_factory`，或 `LLM_API_KEY`、`LLM_MODEL` 都非空。不可用时 `model` 为 `null`。

**`GET /api/materials?data_set=`**：`{"data_set": "default", "materials": [{"id", "topic", "tags", "facts"}]}`。未知 `data_set` 返回 400 `UNKNOWN_DATA_SET`。

**`GET /api/examples`**：按 `cases.json` 顺序返回 `{"examples": [{"name", "covers", "status", "status_ok", "path", "model", "total_tokens", "title"}]}`。`title` 取 `result.json` 的 `title`，可能为 null。

**`GET /api/examples/{name}`**：

```json
{
  "name": "04_tool_fail_transient",
  "covers": "工具失败后恢复",
  "input": {},
  "fault": {"tool": "estimate_duration", "times": 1},
  "data_set": "default",
  "result": {},
  "records": [],
  "markdown": "..."
}
```

`name` 必须在 `cases.json` 里，否则 404 `NOT_FOUND`。`data_set` 由 `data_dir` 反查：`data` → `default`，`examples/data_variants/no_subtitle` → `no_subtitle`。

**`POST /api/runs`** 请求体：

```json
{
  "request": {"topic": "...", "audience": "...", "platform": "...", "target_duration_sec": 30, "style": "..."},
  "mode": "real",
  "mock_script": null,
  "data_set": "default",
  "fault": null,
  "max_steps": 10
}
```

- `request` 的四个文本字段最长 200 字，超出返回 422；`target_duration_sec` 接受数字、字符串或 null，原样交给 `normalize_request`，无效值由模型处理。
- `mode` 只能是 `real`、`mock`。
- `max_steps` 为 1–20，默认 10。
- `fault`：`tool` 在三个业务工具内；`times` 为 -1 或 ≥ 1。
- 错误：
  - `real` 但未配置：409 `MODEL_NOT_CONFIGURED`
  - `mock` 且 `mock_script` 不在白名单：400 `UNKNOWN_MOCK_SCRIPT`
  - 未知 `data_set`：400 `UNKNOWN_DATA_SET`
  - 已有运行在进行：429 `RUN_IN_PROGRESS`
- 成功：202 `{"run_id": "20261103-101530-a1b2c3"}`。

**`GET /api/runs`**：最新在前，最多 50 条：`{"runs": [{"run_id", "created_at", "topic", "status", "mode", "model", "total_duration_sec"}]}`。`status` 取值：`running`、四种 Agent 状态、`crashed`。

**`GET /api/runs/{run_id}`**：`{"run_id", "status", "meta", "result", "records", "markdown", "error"}`。运行中 `result`、`markdown` 为 null。`run_id` 必须匹配 `^\d{8}-\d{6}-[0-9a-f]{6}$`，且目录存在，否则 404。

**`GET /api/runs/{run_id}/events`**：SSE，`Content-Type: text/event-stream`。

```text
id: 0
event: record
data: {"type":"run_start",...}

id: 1
event: record
data: {"type":"step",...}

event: result
data: {"status":"completed",...}

event: end
data: {}
```

- 运行崩溃时用 `event: fatal`、`data: {"message": "..."}` 代替 `result`，后面同样跟 `end`。
- 支持 `Last-Event-ID`：只发送序号更大的记录。
- 已结束的运行（包括重启服务后）从 `trace.jsonl`、`result.json` 重放，发完后结束。
- 活动运行时每 15 秒发送 `: ping\n\n`。
- 响应体是一个生成器，轮询内部事件列表的间隔 150ms，用 `time.sleep`。客户端断开时 Handler 关闭生成器。

**`POST /api/verify`** 请求体：

```json
{
  "source": {"kind": "run", "id": "20261103-101530-a1b2c3"},
  "draft": {"title": "...", "shots": [{"id": 1, "visual": "...", "narration": "...", "claims": [{"source_id": "P01", "quote": "..."}]}]}
}
```

- `source.kind` 为 `run` 或 `example`。目标时长、素材库、已检索素材 ID、模式全部由服务端从该来源的记录里取，**忽略客户端传来的任何其他字段**。
- `draft` 限制：分镜 1–50 个；`title` ≤ 200 字；`visual`、`narration` 各 ≤ 2000 字。
- `title`、`visual`、`narration` 去空白后为空：422，`detail` 为 `{"code": "BLANK_FIELD", "message": "第 2 个分镜的旁白不能为空。", "shot_id": 2, "field": "narration"}`。
- 来源不存在：404。来源没有目标时长：409 `NO_TARGET`。

响应：

```json
{
  "passed": false,
  "duration": {},
  "rules": {},
  "markdown": "...",
  "result": {}
}
```

- `duration`、`rules` 分别是 `estimate_duration`、`check_rules` 的原始返回。
- `passed` 为两者都 `pass`。
- `result`：
  - 通过时：`AgentResult(status="completed", message="修改后的脚本已通过时长与规则检查。", mode=来源模式, title, shots=FinalShot 列表, total_duration_sec, target_duration_sec, source_ids, checks, risks=来源结果的 risks, steps_used=来源, tool_calls_used=来源)`。
  - 未通过时：`AgentResult(status="failed", message="修改后的脚本未通过检查。", mode=来源模式, target_duration_sec, checks, unverified_draft=draft, last_estimate=duration, risks=来源结果的 risks)`。
- `markdown` 是 `render_script_markdown(result)`。

---

### Task 1：打包配置与 Trace 监听

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/script_agent/trace.py`、`src/script_agent/app.py`
- Test: `tests/test_web_listener.py`

**Interfaces:**
- Consumes: 现有 `TraceRecorder`、`run_once`
- Produces:
```python
TraceRecorder(..., listener: Callable[[dict], None] | None = None)
run_once(..., listener: Callable[[dict], None] | None = None) -> AgentResult
```

`listener` 在每条记录产生时被调用，收到的是该记录的副本（`run_start`、`step`、`note`、`run_end` 四类）。监听器抛任何异常都要吞掉，绝不能影响运行和产物。不传时行为完全不变。`run_end` 也要发给监听器。

- [ ] **Step 1：加打包配置**

`pyproject.toml` 增加静态文件打包配置，其余不变：

```toml
[tool.setuptools.package-data]
"script_agent.web" = ["static/*", "static/js/*", "static/js/views/*"]
```

- [ ] **Step 2：写失败测试 `tests/test_web_listener.py`**

```python
def make(tmp_path, listener):
    return TraceRecorder(tmp_path, mode="mock", model="scripted", request={"topic": "字幕"}, fault=None, max_steps=10, max_tool_calls=20, listener=listener)

def add_step(trace):
    trace.step(round=1, seq=1, action="search_materials", args={"query": "字幕"}, observation={"ok": True, "count": 0, "materials": []}, decision_note="依据", injected_fault=False, usage={"prompt_tokens": 1, "completion_tokens": 1})

def test_listener_receives_all_record_types(tmp_path):
    seen = []
    trace = make(tmp_path, seen.append)
    add_step(trace)
    trace.note(round=2, event="no_action", detail="没有调用工具")
    trace.finish(AgentResult(status="failed", message="m", mode="mock"))
    assert [r["type"] for r in seen] == ["run_start", "step", "note", "run_end"]
    assert seen[1]["result_summary"] == "命中 0 条"
    assert seen[3]["status"] == "failed"

def test_listener_gets_copies(tmp_path):
    seen = []
    trace = make(tmp_path, seen.append)
    add_step(trace)
    seen[1]["action"] = "tampered"
    trace.finish(AgentResult(status="failed", message="m", mode="mock"))
    assert "tampered" not in (tmp_path / "trace.jsonl").read_text(encoding="utf-8")

def test_listener_errors_do_not_break_the_run(tmp_path):
    def boom(_):
        raise RuntimeError("boom")
    trace = make(tmp_path, boom)
    add_step(trace)
    trace.finish(AgentResult(status="failed", message="m", mode="mock"))
    lines = (tmp_path / "trace.jsonl").read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[-1])["type"] == "run_end"

def test_run_once_forwards_listener(tmp_path):
    seen = []
    steps = [round_of(call("ask_user", missing_fields=["other"], questions=["？"], reason="测试"))]
    result = run_once({"topic": "字幕"}, ScriptedLLM(steps), mode="mock", model_name="scripted", data_dir=DATA_DIR, fault=None, max_steps=3, max_tool_calls=5, out_dir=tmp_path, listener=seen.append)
    assert result.status == "needs_input"
    assert [r["type"] for r in seen] == ["run_start", "step", "run_end"]
```

- [ ] **Step 3：确认失败，实现，确认通过**

运行 `.venv\Scripts\python.exe -m pytest tests/test_web_listener.py -v`。预期：先 FAIL，实现后 4 passed。

- [ ] **Step 4：跑全量回归**

运行 `.venv\Scripts\python.exe -m pytest -q`。预期：原有 240 个加新增的全部通过。

---

### Task 2：后端接口

**Files:**
- Create: `src/script_agent/web/__init__.py`、`__main__.py`、`server.py`、`service.py`、`runs.py`
- Create: `src/script_agent/web/static/index.html`（Task 2 先放最小占位，Task 3 替换）
- Test: `tests/web_helpers.py`、`tests/test_web_api.py`、`tests/test_web_http.py`

**Interfaces:**
- Consumes: `run_once(listener=...)`、`load_catalog`、`estimate_duration`、`check_rules`、`render_script_markdown`、`normalize_request`、`ScriptDraft`、`AgentResult`、`FinalShot`、`Checks`、`ScriptedLLM`、`OpenAICompatibleLLM`、`FaultPlan`
- Produces:
```python
# server.py
@dataclass
class Response:
    status: int
    headers: dict[str, str]
    body: bytes | Iterator[bytes]   # SSE 时是生成器

class WebApp:
    def dispatch(self, method: str, target: str, headers: Mapping[str, str] | None = None, body: bytes = b"") -> Response: ...
    # 请求头大小写不敏感；任何异常都转成 JSON 错误响应，绝不抛给调用方

def create_app(root: Path | None = None, runs_dir: Path | None = None, llm_factory: Callable[[], tuple[LLMClient, str]] | None = None) -> WebApp: ...
# root 默认为仓库根目录（Path(__file__).resolve().parents[3]）
# runs_dir 默认为 root / "runs" / "web"
# 启动时执行 load_dotenv(root / ".env")

def make_handler(app: WebApp) -> type[BaseHTTPRequestHandler]: ...
# Handler 只负责读请求、调 dispatch、写响应；log_message 静默
# 请求体超过 1 MiB 时不读取，直接返回 413

# __main__.py
def main(argv: list[str] | None = None) -> int: ...
# 参数只有 --port，默认 8765；host 固定 "127.0.0.1"
# 启动后打印 http://127.0.0.1:<port>；端口被占用时打印中文错误，返回 1
```

实现要点：
- **`service.py`：** 业务逻辑（meta、materials、examples、runs、verify）。出错时抛 `ApiError(status, code, message, **extra)`，由 `dispatch` 转成响应。请求体用 pydantic 模型校验，`ValidationError` 转 422。
- **路由：** `dispatch` 里用一张 `(方法, 正则, 处理函数)` 表。路径先用 `urlsplit` 拆出 path 和 query，按 `/` 分段匹配后再 `unquote`。
- **静态文件：** 启动时遍历 `static/` 建 `{URL 路径: 文件}` 字典，`/` 映射到 `index.html`。只有字典里的路径能被访问，绝不把 URL 拼成文件路径。类型：`.html` `text/html; charset=utf-8`，`.css` `text/css; charset=utf-8`，`.js` `text/javascript; charset=utf-8`，`.svg` `image/svg+xml`。带 `Cache-Control: no-store`。
- **`runs.py` 的 `RunManager`：** 用 `threading.Lock` 保护。每个活动运行持有 `records` 列表、`result`、`error`、`done`。`start()` 校验没有活动运行后启动 daemon 线程调用 `run_once`。只允许一个活动运行。
- **线程内异常：** 捕获 `Exception`，记为 `crashed`，错误文字用 `trace._redact_text` 按 `LLM_API_KEY` 脱敏，并写入运行目录的 `error.txt`。**活动运行结束后不能保持占用状态。**
- **运行目录：** `runs_dir/<run_id>/`。启动时先写 `meta.json`（`run_id`、`created_at`、`request`（原始）、`mode`、`model`、`data_set`、`fault`、`max_steps`），再由 `run_once` 写其余 4 个产物。
- **运行状态判定：** 活动运行为 `running`；有 `result.json` 取其 `status`；有 `error.txt` 为 `crashed`；两者都没有且不是活动运行，说明服务中途退出，也算 `crashed`，错误文字为 `运行被中断（服务在运行结束前退出）。`
- **白名单：** `data_sets` 是固定字典；`mock_scripts` 是 `{"01_normal": "正常路径", "06_over_duration_fixed": "先超时长再修正"}` 对应 `examples/mock_scripts/<id>.json`；示例名来自 `cases.json`。
- **SSE 响应头：** `Content-Type: text/event-stream; charset=utf-8`、`Cache-Control: no-store`。Handler 每写一块就 flush；写失败（`BrokenPipeError`、`ConnectionError`）时关闭生成器并结束。SSE 响应设 `Connection: close`，不写 `Content-Length`。
- **`.gitignore`：** 不用改，`runs/` 已忽略。

- [ ] **Step 1：写测试辅助 `tests/web_helpers.py`（内容原样使用）**

```python
"""Web 测试辅助：直接调 dispatch，不走 socket。"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_dumps = json.dumps
_loads = json.loads


class Reply:
    def __init__(self, response):
        self.status_code = response.status
        self.headers = {k.lower(): v for k, v in response.headers.items()}
        body = response.body
        self.content = body if isinstance(body, bytes) else b"".join(body)
        self.text = self.content.decode("utf-8")

    def json(self):
        return _loads(self.text)


class Client:
    HOST = {"Host": "127.0.0.1:8765"}

    def __init__(self, app):
        self.app = app

    def get(self, target, headers=None):
        return Reply(self.app.dispatch("GET", target, {**self.HOST, **(headers or {})}))

    def post(self, target, json=None, headers=None, raw=None):
        body = raw if raw is not None else _dumps(json, ensure_ascii=False).encode("utf-8")
        merged = {**self.HOST, "Content-Type": "application/json", **(headers or {})}
        return Reply(self.app.dispatch("POST", target, merged, body))


def parse_events(text):
    events = []
    for block in text.split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line and not line.startswith(":"))
        if "event" in fields:
            events.append(fields)
    return events
```

- [ ] **Step 2：写失败测试 `tests/test_web_api.py`**

```python
RUN_REQUEST = {"request": {"topic": "剪刀鱼的字幕功能", "target_duration_sec": 30}, "mode": "mock", "mock_script": "01_normal", "data_set": "default"}

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("LLM_MODEL", "")
    return Client(create_app(root=ROOT, runs_dir=tmp_path / "runs"))

def start(client, body=RUN_REQUEST):
    response = client.post("/api/runs", json=body)
    assert response.status_code == 202, response.text
    return response.json()["run_id"]

def wait(client, run_id, timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        data = client.get(f"/api/runs/{run_id}").json()
        if data["status"] != "running":
            return data
        time.sleep(0.05)
    raise AssertionError("运行没有结束")

def sse(client, run_id, headers=None):
    response = client.get(f"/api/runs/{run_id}/events", headers=headers)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    return parse_events(response.text)

def test_meta_without_config(client):
    data = client.get("/api/meta").json()
    assert data["real_available"] is False and data["model"] is None
    assert [d["id"] for d in data["data_sets"]] == ["default", "no_subtitle"]
    assert {m["id"] for m in data["mock_scripts"]} == {"01_normal", "06_over_duration_fixed"}

def test_meta_never_exposes_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "sk-should-not-leak")
    monkeypatch.setenv("LLM_MODEL", "demo-model")
    monkeypatch.setenv("LLM_BASE_URL", "https://relay.should-not-leak.example/v1")
    text = Client(create_app(root=ROOT, runs_dir=tmp_path)).get("/api/meta").text
    assert "demo-model" in text
    assert "should-not-leak" not in text

def test_examples_list_follows_cases(client):
    examples = client.get("/api/examples").json()["examples"]
    assert len(examples) == 10 and examples[0]["name"] == "01_normal"
    assert examples[0]["status"] == "completed" and examples[0]["title"]
    assert examples[1]["title"] is None

def test_example_detail(client):
    first = client.get("/api/examples/01_normal").json()
    assert first["data_set"] == "default" and first["result"]["total_duration_sec"] == 25.5
    assert first["records"][0]["type"] == "run_start" and first["markdown"].startswith("#")
    assert client.get("/api/examples/04_tool_fail_transient").json()["fault"] == {"tool": "estimate_duration", "times": 1}
    assert client.get("/api/examples/10_materials_changed").json()["data_set"] == "no_subtitle"

@pytest.mark.parametrize("name", ["nope", "..%2F..%2Fdata", "01_normal%2F..%2F..%2F..%2F.env"])
def test_unknown_example_is_404(client, name):
    assert client.get(f"/api/examples/{name}").status_code == 404

def test_materials_by_data_set(client):
    ids = lambda s: {m["id"] for m in client.get(f"/api/materials?data_set={s}").json()["materials"]}
    assert "P01" in ids("default") and "P01" not in ids("no_subtitle")
    assert client.get("/api/materials?data_set=../../etc").status_code == 400

def test_real_without_config_is_409(client):
    response = client.post("/api/runs", json={**RUN_REQUEST, "mode": "real", "mock_script": None})
    assert response.status_code == 409 and response.json()["detail"]["code"] == "MODEL_NOT_CONFIGURED"

@pytest.mark.parametrize("patch,code", [
    ({"mock_script": "../../secret"}, 400),
    ({"mock_script": None}, 400),
    ({"data_set": "../../etc"}, 400),
    ({"mode": "other"}, 422),
    ({"max_steps": 0}, 422),
    ({"max_steps": 21}, 422),
    ({"fault": {"tool": "delete_all", "times": 1}}, 422),
    ({"fault": {"tool": "check_rules", "times": 0}}, 422),
    ({"request": {"topic": "字" * 201}}, 422),
])
def test_invalid_run_requests(client, patch, code):
    assert client.post("/api/runs", json={**RUN_REQUEST, **patch}).status_code == code

def test_invalid_json_body(client):
    response = client.post("/api/runs", raw=b"{bad")
    assert response.status_code == 400 and response.json()["detail"]["code"] == "INVALID_JSON"

def test_post_requires_json_content_type(client):
    assert client.post("/api/runs", json=RUN_REQUEST, headers={"Content-Type": "text/plain"}).status_code == 415

def test_cross_origin_post_is_rejected(client):
    assert client.post("/api/runs", json=RUN_REQUEST, headers={"Origin": "http://evil.example"}).status_code == 403
    assert client.post("/api/runs", json=RUN_REQUEST, headers={"Origin": "http://127.0.0.1:8765"}).status_code == 202

def test_foreign_host_is_rejected(client):
    response = client.get("/api/meta", headers={"Host": "evil.example"})
    assert response.status_code == 400 and response.json()["detail"]["code"] == "BAD_HOST"

def test_unknown_path_and_method(client):
    assert client.get("/api/nope").status_code == 404
    assert client.post("/api/meta", json={}).status_code == 405
    assert client.get("/../../.env").status_code == 404
    assert client.get("/js/../../../.env").status_code == 404

def test_mock_run_completes_and_writes_artifacts(client, tmp_path):
    run_id = start(client)
    data = wait(client, run_id)
    assert data["status"] == "completed" and data["result"]["mode"] == "mock"
    assert data["markdown"].startswith("[MOCK]")
    assert data["meta"]["request"]["topic"] == "剪刀鱼的字幕功能"
    for name in ["meta.json", "result.json", "script.md", "trace.jsonl", "trace.md"]:
        assert (tmp_path / "runs" / run_id / name).exists()
    listed = client.get("/api/runs").json()["runs"]
    assert listed[0]["run_id"] == run_id and listed[0]["status"] == "completed" and listed[0]["topic"] == "剪刀鱼的字幕功能"

def test_events_replay_and_resume(client):
    run_id = start(client)
    wait(client, run_id)
    events = sse(client, run_id)
    kinds = [e["event"] for e in events]
    assert kinds[0] == "record" and kinds[-2:] == ["result", "end"]
    assert json.loads(events[0]["data"])["type"] == "run_start"
    assert any(json.loads(e["data"]).get("type") == "run_end" for e in events if e["event"] == "record")
    ids = [int(e["id"]) for e in events if e["event"] == "record"]
    assert ids == list(range(len(ids)))
    resumed = sse(client, run_id, {"Last-Event-ID": str(ids[-2])})
    assert [int(e["id"]) for e in resumed if e["event"] == "record"] == [ids[-1]]

def test_active_run_streams_until_done(tmp_path):
    llm = BlockingLLM()
    client = Client(create_app(root=ROOT, runs_dir=tmp_path, llm_factory=lambda: (llm, "stub")))
    run_id = client.post("/api/runs", json=REAL_BODY).json()["run_id"]
    threading.Timer(0.4, llm.release.set).start()
    kinds = [e["event"] for e in sse(client, run_id)]
    assert kinds[0] == "record" and kinds[-2:] == ["result", "end"]

def test_finished_run_survives_restart(client, tmp_path):
    run_id = start(client)
    wait(client, run_id)
    fresh = Client(create_app(root=ROOT, runs_dir=tmp_path / "runs"))
    assert fresh.get(f"/api/runs/{run_id}").json()["status"] == "completed"
    assert sse(fresh, run_id)[-1]["event"] == "end"

def test_interrupted_run_is_reported(client, tmp_path):
    run_id = "20261103-101530-a1b2c3"
    folder = tmp_path / "runs" / run_id
    folder.mkdir(parents=True)
    (folder / "meta.json").write_text(json.dumps({"run_id": run_id, "created_at": "2026-11-03T10:15:30Z", "request": {}, "mode": "real", "model": "m", "data_set": "default", "fault": None, "max_steps": 10}), encoding="utf-8")
    data = client.get(f"/api/runs/{run_id}").json()
    assert data["status"] == "crashed" and "中断" in data["error"]

def test_fault_reaches_the_tool(client):
    run_id = start(client, {**RUN_REQUEST, "fault": {"tool": "estimate_duration", "times": -1}})
    data = wait(client, run_id)
    assert data["status"] != "completed"
    assert any(r.get("injected_fault") for r in data["records"] if r["type"] == "step")

REAL_BODY = {"request": {"topic": "字幕", "target_duration_sec": 30}, "mode": "real", "data_set": "default"}

class BlockingLLM:
    def __init__(self):
        self.release = threading.Event()
    def complete(self, messages, tools):
        self.release.wait(10)
        raise LLMError("结束")

def test_only_one_active_run(tmp_path):
    llm = BlockingLLM()
    client = Client(create_app(root=ROOT, runs_dir=tmp_path, llm_factory=lambda: (llm, "stub")))
    run_id = client.post("/api/runs", json=REAL_BODY).json()["run_id"]
    assert client.get(f"/api/runs/{run_id}").json()["status"] == "running"
    second = client.post("/api/runs", json=REAL_BODY)
    assert second.status_code == 429 and second.json()["detail"]["code"] == "RUN_IN_PROGRESS"
    llm.release.set()
    assert wait(client, run_id)["status"] == "failed"
    assert client.post("/api/runs", json=REAL_BODY).status_code == 202

class CrashingLLM:
    def complete(self, messages, tools):
        raise RuntimeError("boom sk-should-not-leak")

def test_crash_is_reported_and_redacted(tmp_path):
    client = Client(create_app(root=ROOT, runs_dir=tmp_path, llm_factory=lambda: (CrashingLLM(), "stub")))
    run_id = client.post("/api/runs", json=REAL_BODY).json()["run_id"]
    data = wait(client, run_id)
    assert data["status"] == "crashed" and data["error"]
    assert "should-not-leak" not in json.dumps(data, ensure_ascii=False)
    assert sse(client, run_id)[-2]["event"] == "fatal"
    assert client.post("/api/runs", json=REAL_BODY).status_code == 202

@pytest.mark.parametrize("run_id", ["nope", "20261103-101530-zzzzzz", "..%2F..%2F.env", "20261103-101530-000000"])
def test_unknown_run_is_404(client, run_id):
    assert client.get(f"/api/runs/{run_id}").status_code == 404
    assert client.get(f"/api/runs/{run_id}/events").status_code == 404

def draft_of(client, name="01_normal"):
    result = client.get(f"/api/examples/{name}").json()["result"]
    return {"title": result["title"], "shots": [{k: s[k] for k in ("id", "visual", "narration", "claims")} for s in result["shots"]]}

def verify(client, draft, source=None):
    return client.post("/api/verify", json={"source": source or {"kind": "example", "id": "01_normal"}, "draft": draft})

def test_verify_unedited_example_passes(client):
    data = verify(client, draft_of(client)).json()
    assert data["passed"] is True and data["duration"]["total_duration_sec"] == 25.5
    assert data["result"]["status"] == "completed" and data["result"]["mode"] == "real"
    assert [s["duration_sec"] for s in data["result"]["shots"]] == [4.25, 4.5, 4.0, 4.0, 3.5, 5.25]

def test_verify_detects_invented_fact(client):
    draft = draft_of(client)
    draft["shots"][0]["narration"] = "效率提升80%"
    data = verify(client, draft).json()
    assert data["passed"] is False and data["result"]["status"] == "failed"
    assert {"UNSUPPORTED_NUMBER", "UNSUPPORTED_TERM"} <= {v["code"] for v in data["rules"]["violations"]}
    assert "未通过检查" in data["markdown"]

def test_verify_uses_server_side_target(client):
    draft = draft_of(client)
    response = client.post("/api/verify", json={"source": {"kind": "example", "id": "01_normal"}, "draft": draft, "target_duration_sec": 999, "retrieved_ids": ["P06"]})
    assert response.json()["duration"]["target_duration_sec"] == 30.0

def test_verify_retrieved_ids_come_from_trace(client):
    draft = draft_of(client)
    draft["shots"][0]["claims"] = [{"source_id": "P06", "quote": "内置背景音乐库"}]
    codes = {v["code"] for v in verify(client, draft).json()["rules"]["violations"]}
    assert "SOURCE_NOT_RETRIEVED" in codes

def test_verify_keeps_mock_mode(client):
    run_id = start(client)
    wait(client, run_id)
    result = client.get(f"/api/runs/{run_id}").json()["result"]
    draft = {"title": result["title"], "shots": [{k: s[k] for k in ("id", "visual", "narration", "claims")} for s in result["shots"]]}
    data = verify(client, draft, {"kind": "run", "id": run_id}).json()
    assert data["passed"] is True and data["markdown"].startswith("[MOCK]")

@pytest.mark.parametrize("field,message", [("narration", "旁白"), ("visual", "画面")])
def test_verify_rejects_blank_fields(client, field, message):
    draft = draft_of(client)
    draft["shots"][1][field] = "   "
    response = verify(client, draft)
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "BLANK_FIELD" and detail["shot_id"] == 2 and detail["field"] == field and message in detail["message"]

def test_verify_rejects_blank_title_and_oversize(client):
    draft = draft_of(client)
    assert verify(client, {**draft, "title": " "}).json()["detail"]["code"] == "BLANK_FIELD"
    assert verify(client, {**draft, "shots": []}).status_code == 422
    long_shot = json.loads(json.dumps(draft))
    long_shot["shots"][0]["narration"] = "字" * 2001
    assert verify(client, long_shot).status_code == 422

def test_verify_source_errors(client):
    draft = draft_of(client)
    assert verify(client, draft, {"kind": "example", "id": "nope"}).status_code == 404
    assert verify(client, draft, {"kind": "run", "id": "20261103-101530-a1b2c3"}).status_code == 404
    no_target = verify(client, draft, {"kind": "example", "id": "02_missing_target"})
    assert no_target.status_code == 409 and no_target.json()["detail"]["code"] == "NO_TARGET"

def test_index_is_served_with_csp(client):
    response = client.get("/")
    assert response.status_code == 200 and "text/html" in response.headers["content-type"]
    assert "default-src 'self'" in response.headers["content-security-policy"]
    assert "unsafe-inline" not in response.headers["content-security-policy"]
    assert response.headers["x-content-type-options"] == "nosniff"

def test_static_files_have_no_unsafe_dom_or_external_urls():
    static = ROOT / "src/script_agent/web/static"
    banned = re.compile(r"innerHTML|outerHTML|insertAdjacentHTML|document\.write|\beval\(|https?://(?!www\.w3\.org/)")
    offenders = [str(p) for p in static.rglob("*") if p.is_file() and banned.search(p.read_text(encoding="utf-8"))]
    assert offenders == []

def test_server_binds_loopback_only():
    source = (ROOT / "src/script_agent/web/__main__.py").read_text(encoding="utf-8")
    assert '"127.0.0.1"' in source and "--host" not in source
```

`tests/test_web_api.py` 开头需要 `from web_helpers import ROOT, Client, parse_events`。把 `REAL_BODY`、`BlockingLLM` 放到文件靠前的位置。

- [ ] **Step 3：写失败测试 `tests/test_web_http.py`（不走真实网络）**

```python
class FakeSocket:
    """给 BaseHTTPRequestHandler 用的内存 socket。"""
    def __init__(self, raw):
        self.reader = io.BytesIO(raw)
        self.sent = bytearray()
    def makefile(self, mode, *args, **kwargs):
        return self.reader
    def sendall(self, data):
        self.sent.extend(data)
    def shutdown(self, *args):
        pass
    def close(self):
        pass

def exchange(app, raw):
    fake = FakeSocket(raw)
    make_handler(app)(fake, ("127.0.0.1", 1), None)
    head, _, body = bytes(fake.sent).partition(b"\r\n\r\n")
    lines = head.decode("latin-1").split("\r\n")
    headers = {k.lower(): v.strip() for k, v in (line.split(":", 1) for line in lines[1:])}
    return int(lines[0].split()[1]), headers, body

@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("LLM_MODEL", "")
    return create_app(root=ROOT, runs_dir=tmp_path)

def request(method, path, body=b"", headers=()):
    lines = [f"{method} {path} HTTP/1.1", "Host: 127.0.0.1:8765", "Connection: close", *headers]
    if body:
        lines += ["Content-Type: application/json", f"Content-Length: {len(body)}"]
    return ("\r\n".join(lines) + "\r\n\r\n").encode("utf-8") + body

def test_get_json_roundtrip(app):
    status, headers, body = exchange(app, request("GET", "/api/meta"))
    assert status == 200 and headers["content-type"].startswith("application/json")
    assert json.loads(body)["real_available"] is False
    assert "default-src 'self'" in headers["content-security-policy"]
    assert int(headers["content-length"]) == len(body)

def test_post_body_is_read(app):
    status, _, body = exchange(app, request("POST", "/api/verify", b"{bad"))
    assert status == 400 and json.loads(body)["detail"]["code"] == "INVALID_JSON"

def test_oversize_body_is_rejected_without_reading(app):
    raw = ("POST /api/verify HTTP/1.1\r\nHost: 127.0.0.1:8765\r\nConnection: close\r\nContent-Type: application/json\r\nContent-Length: 2000000\r\n\r\n").encode()
    status, _, body = exchange(app, raw)
    assert status == 413 and json.loads(body)["detail"]["code"] == "BODY_TOO_LARGE"

def test_static_file_types(app):
    status, headers, body = exchange(app, request("GET", "/"))
    assert status == 200 and headers["content-type"].startswith("text/html") and b"<title>" in body

def test_sse_response_has_no_content_length(app):
    client = Client(app)
    run_id = client.post("/api/runs", json={"request": {"topic": "字幕", "target_duration_sec": 30}, "mode": "mock", "mock_script": "01_normal", "data_set": "default"}).json()["run_id"]
    deadline = time.time() + 15
    while client.get(f"/api/runs/{run_id}").json()["status"] == "running" and time.time() < deadline:
        time.sleep(0.05)
    status, headers, body = exchange(app, request("GET", f"/api/runs/{run_id}/events"))
    assert status == 200 and headers["content-type"].startswith("text/event-stream")
    assert "content-length" not in headers
    assert b"event: end" in body

def test_client_disconnect_closes_stream(app):
    class Broken(FakeSocket):
        def sendall(self, data):
            raise BrokenPipeError()
    make_handler(app)(Broken(request("GET", "/api/meta")), ("127.0.0.1", 1), None)  # 不能抛异常

def loopback_available():
    server = socket.socket()
    try:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        probe = socket.socket()
        probe.settimeout(2)
        result = probe.connect_ex(server.getsockname())
        probe.close()
        return result == 0
    except OSError:
        return False
    finally:
        server.close()

@pytest.mark.skipif(not loopback_available(), reason="当前环境不允许本机回环连接")
def test_real_socket_roundtrip(app):
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(f"http://127.0.0.1:{server.server_address[1]}/api/meta", timeout=5) as response:
            assert response.status == 200 and json.load(response)["real_available"] is False
    finally:
        server.shutdown()
        server.server_close()
```

`tests/test_web_http.py` 开头需要 `from web_helpers import ROOT, Client`。

- [ ] **Step 4：确认失败，实现，确认通过**

运行 `.venv\Scripts\python.exe -m pytest tests/test_web_api.py tests/test_web_http.py -v`。预期：先 FAIL，实现后全部通过；`test_real_socket_roundtrip` 在当前环境可能显示 SKIPPED，这是预期内的。

- [ ] **Step 5：确认能绑定端口**

当前环境不允许连接回环端口，所以只验证启动和端口占用。运行一段临时脚本（放系统临时目录）：调用 `script_agent.web.__main__.main(["--port", "8765"])` 的后台线程，确认绑定成功、没有异常，然后结束进程。不要尝试用 curl 或浏览器访问。

---

### Task 3：页面骨架、左栏与记录

**Files:**
- Modify: `src/script_agent/web/static/index.html`
- Create: `static/app.css`、`static/js/{main,api,dom,labels,store,derive}.js`、`static/js/views/{brief,history}.js`，以及 Task 4、5 视图的空导出占位
- Test: 现有 `tests/test_web_api.py`

**Interfaces:**
- Consumes: 上面的接口规范
- Produces:
```js
// api.js
getMeta(), getMaterials(dataSet), listExamples(), getExample(name), listRuns(), getRun(id), startRun(body), verify(source, draft)
openEvents(runId, {onRecord, onResult, onFatal, onEnd})  // 返回 close()；使用 EventSource，自动重连由浏览器负责
class ApiError extends Error { status; code; detail }
// dom.js
h(tag, props, ...children)
// store.js
getState(), setState(patch), subscribe(fn)
// main.js
openExample(name), openRun(id), startGeneration(body)
```

- [ ] **Step 1：写 `index.html`**

`<title>脚本剪辑台</title>`、`lang="zh-CN"`、viewport meta、`<link rel="stylesheet" href="/app.css">`、`<script type="module" src="/js/main.js"></script>`。不写内联脚本和内联样式。结构：`header.topbar`、`nav.viewswitch`、`aside#panel-brief`、`main#panel-script`、`aside#panel-trace`，以及一个隐藏的 SVG sprite（icon-check、icon-x、icon-alert、icon-chevron、icon-copy、icon-download、icon-trash、icon-plus，都是 16×16、`stroke="currentColor"`、无填充）。

- [ ] **Step 2：写 `app.css`**

按“设计规范”写全部 token、布局和断点。所有颜色都引用变量，不出现散落的十六进制色值（`rgba` 阴影除外）。

- [ ] **Step 3：实现 `dom.js`、`labels.js`、`store.js`、`api.js`、`derive.js`**

`derive.js` 的函数签名见设计规范，必须是不访问 DOM 的纯函数。

- [ ] **Step 4：实现左栏**

按“设计规范 / 左栏”实现 `brief.js`、`history.js`，以及 `main.js` 的启动流程（读 meta、读 hash、连接视图）。提交时只把非空字段放进 `request`；`target_duration_sec` 空字符串不传。

- [ ] **Step 5：用 Node 校验语法和纯函数**

运行：

```bash
node --check src/script_agent/web/static/js/main.js
```

对 `js/` 下所有文件各跑一次 `node --check`。再用一段临时脚本（放到系统临时目录，不进仓库）动态 `import` `derive.js`，断言：

```js
formatClock(4.25) === "00:04.25"
formatClock(65) === "01:05.00"
JSON.stringify(timecodes([4.25, 4.5])) === JSON.stringify([{start: 0, end: 4.25}, {start: 4.25, end: 8.75}])
JSON.stringify(scaleTicks(30, false)) === JSON.stringify([0, 5, 10, 15, 20, 25, 30])
JSON.stringify(scaleTicks(12, false)) === JSON.stringify([0,1,2,3,4,5,6,7,8,9,10,11,12])
JSON.stringify(retrievedIdsOf([{type:"step",action:"search_materials",result:{ok:true,materials:[{id:"P02"},{id:"P01"}]}},{type:"step",action:"search_materials",result:{ok:false}}])) === JSON.stringify(["P01","P02"])
deriveVersions([{type:"step",action:"estimate_duration",args:{title:"t",shots:[]},result:{ok:true,verdict:"too_long",total_duration_sec:40}},{type:"step",action:"check_rules",args:{title:"t",shots:[]},result:{ok:true,verdict:"fail",violations:[]}}]).length === 1
```

预期：全部成立。

---

### Task 4：决策轨迹与实时运行

**Files:**
- Create: `static/js/views/trace.js`
- Modify: `static/js/main.js`、`static/app.css`

**Interfaces:**
- Consumes: `openEvents`、`store`、`labels`、`derive.statsOf`
- Produces: `renderTrace(container)`，订阅 store 并增量渲染

- [ ] **Step 1：实现 `trace.js`**

按“设计规范 / 右栏”实现全部条目类型。折叠状态保存在模块内（按 `seq`），重绘后保持。

- [ ] **Step 2：实现运行流程**

`startGeneration(body)`：

1. 调 `startRun`。409、429、400 时把 `detail.message` 显示在主按钮下方（`--bad` 12px）。
2. 成功后清空状态，设 `phase="running"`，hash 设为 `#run=<id>`。
3. `openEvents`：
   - `onRecord`：按 `id` 去重后追加 `records`，并更新草稿预览；
   - `onResult`：写入 `result`，再调 `getRun` 取 `markdown`；
   - `onFatal`：写入 `error`；
   - `onEnd`：`phase="done"`，关闭连接，刷新记录列表。

- [ ] **Step 3：刷新续接**

`openRun(id)`：`getRun` 后把已有 `records` 写入 store；`status === "running"` 时用 `openEvents` 继续，前端要按 `id` 去重（重连时浏览器会自动带 `Last-Event-ID`，首次连接从 0 重放，所以必须去重）。

- [ ] **Step 4：校验**

对改动的 JS 跑 `node --check`；运行 `.venv\Scripts\python.exe -m pytest tests/test_web_api.py -q`，预期通过。

---

### Task 5：中栏：时间线、分镜编辑、校验与导出

**Files:**
- Create: `static/js/views/editor.js`、`static/js/views/timeline.js`
- Modify: `static/js/main.js`、`static/app.css`

**Interfaces:**
- Consumes: `verify`、`store`、`derive`、`labels`
- Produces: `renderEditor(container)`、`renderTimeline(container, {shots, durations, target, verdict, total, versions})`

- [ ] **Step 1：实现 `timeline.js`**

严格按“时间线规范”：比例尺、刻度、合格区、片段、斜纹、目标线、读数、版本条、图例。所有几何尺寸通过 `element.style` 设置（`left`、`width` 用百分比）。

- [ ] **Step 2：实现 `editor.js`**

按“中栏”实现状态条、标题、分镜列表、引用增删、违规提示、风险、素材来源、底部操作条、空状态。遵守“保留焦点”要求。

- [ ] **Step 3：实现校验和导出**

`重新校验`：把 `state.draft` 的分镜 `id` 重排为 1…n 后调 `verify`。
- 成功：写入 `verification`，`dirty=false`，用返回的时长更新每镜和时间线，违规显示到对应分镜。
- 422 `BLANK_FIELD`：滚动到对应分镜并聚焦字段，底部条显示 `detail.message`（`--bad`）。
- 409 `NO_TARGET`：底部条显示 `这条记录没有目标时长，无法校验。`

`撤销修改`：恢复 `originalDraft`，清除 `verification`。

导出：`复制 Markdown` 用 `navigator.clipboard.writeText`，成功后按钮文字短暂变 `已复制`（1.5 秒）；失败显示 `复制失败，请用下载`。下载用 `Blob` + `<a download>`。

- [ ] **Step 4：校验**

对改动的 JS 跑 `node --check`；运行 `.venv\Scripts\python.exe -m pytest -q`，预期全部通过。

---

### Task 6：文档

**Files:**
- Modify: `README.md`、`docs/02-solution.md`

不要修改 `docs/03-evaluation.md`、`docs/04-ai-usage.md`、`docs/05-retrospective.md`、`examples/test-results.txt`，它们由后续统一更新。

- [ ] **Step 1：`README.md`**

在“真实运行”之后加一节“Web 工作台（可选）”，内容：

```bash
python -m script_agent.web --port 8765
```

然后打开 `http://127.0.0.1:8765`。说明：
- 题目要求的运行入口仍是 CLI，Web 是可选的查看和编辑界面；
- 只监听本机；
- 没配置模型时可以用离线演示，并查看已提交的 10 条真实运行记录；
- 编辑脚本后可重新校验，校验只调用确定性的工具，不调用模型，也不消耗 token；
- 运行产物保存在 `runs/web/<run_id>/`。

- [ ] **Step 2：`docs/02-solution.md`**

末尾加一节“Web 工作台”：
- 架构：标准库 `ThreadingHTTPServer` 外壳、后台线程、SSE；路由集中在不依赖 socket 的 `dispatch()`，所以接口测试不走网络；
- Agent 决策逻辑没有改动；
- 为什么不用 FastAPI、前端框架和构建工具：这是只监听本机的单用户工具，不新增依赖，评审者装完项目后一条命令就能启动；代价是路由和校验要自己写；
- 校验接口的目标时长、素材库、已检索素材都由服务端决定，客户端不能绕过。

---

## 完成后执行方要汇报

1. 改动和新增的文件清单。
2. `.venv\Scripts\python.exe -m pytest -q` 的最后两行实际输出。
3. 任何偏离本方案的地方和原因。
4. 没有完成或没有验证的部分。

不要声称界面已经在浏览器里验证过，除非真的打开过；浏览器验收由审查方完成。
