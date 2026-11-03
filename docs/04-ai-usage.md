# 04 AI 使用说明

本文如实记录 AI 在项目里承担了什么、人工环节落在哪里。最后四节留空，由本人填写。

## 方案设计

施工方案由 Claude（Claude Code）产出，保存在仓库内：

- `docs/superpowers/plans/2026-11-02-video-script-agent.md`

方案在本仓库里同时充当规格说明（Spec）：附录 A 是题目原文，正文按 Task 1–11 拆成可执行步骤，每个 Task 都写了要改的文件、接口签名、测试代码、验证命令和提交信息。执行时以它为准，遇到它没定义又会影响验收的问题先停下来确认，不自行改需求。

Web 工作台另有一份方案，同样由 Claude 产出：

- `docs/superpowers/plans/2026-11-03-web-workbench.md`

## Web 工作台的实现

Web 工作台（`src/script_agent/web/` 和 `tests/test_web_*.py`）由 **Claude（Claude Code）直接实现**，不是下面的 ZCode。

原计划交给 DeepSeek 子代理。它启动后中转站持续返回 503，几次尝试都没能完成，只留下 `tests/test_web_listener.py` 和 `tests/web_helpers.py` 两个按方案原样抄写的测试文件。之后改由 Claude 接手，并按方案要求把接口改成了标准库实现。

Claude 的验证方式：
- 运行 `tests/test_web_*.py`，见 `examples/test-results.txt`。
- 用 Edge 无头模式配合请求拦截，把浏览器请求直接转给 `dispatch()`，检查桌面、平板、手机三种宽度下的主要流程和截图。这个脚本是临时的，没有提交。
- 没有验证的部分：当时开发环境禁止本机回环连接，`test_real_socket_roundtrip` 被跳过。后来在允许回环的环境里这条用例已实际跑通，并且我在浏览器里对真实监听端口 `127.0.0.1:8765` 手动走查过主流程（新建需求、实时轨迹、编辑与重新校验）；但没有做自动化端到端。

## 质量复查

第二批真实运行之后的质量复查也由 Claude 完成：人工读脚本发现超出素材的说法，收紧 Prompt、扩充词表、修了两个代码问题，并重跑第三批。经过见 `docs/03-evaluation.md` 的“失败记录”。

## 代码实现

代码由 **ZCode CLI 的编码 Agent** 实现。该工具在本工作区的会话记录里登记的模型是 `deepseek-v4.1-flash`（推理档位 `max`），通过 OpenAI 兼容接口调用；这条记录来自本机 ZCode 的会话索引（`tasks-index.sqlite` 中 `workspace_path` 为本仓库的那条记录），不在仓库内。

几点需要说明清楚，避免误读：

- **实现用的模型 ≠ 项目运行用的模型（即使名字相同）。** `examples/real/` 里记录的 `deepseek-v4.1-flash` 是项目 `.env` 里 `LLM_MODEL` 指定的、被 Agent 调用来写脚本的模型；写代码的模型是编码 Agent 自身的会话模型。两者在这里恰好同名，但用途完全分开：前者决定“脚本写得好不好”，后者决定“代码是谁写的”。项目 `.env` 里换任何模型，都不影响 `examples/real/` 已提交的记录，只是重跑会得到新的记录。
- 实现按方案逐个 Task 推进，每个 Task 结束至少提交一次（`ae98952` 及之前共 18 个提交，见 `git log --oneline`；其中 Task 5、Task 7、Task 10 因为返工或分批真实运行产生了多个提交）。Task 之间有审查环节，审查发现的问题在 `docs/05-retrospective.md` 的“施工记录”里按提交写明。
- 方案里没有、但实现时必要的细节（例如 `app._fault_record`、Trace 的脱敏顺序、`render.py` 的竖线转义）由实现方补，并写进测试。
- AI 没有代写本文档的四节个人内容，也没有代填 `README.md` 的“实际用时与未完成部分”。

## 验证方式

以下是实际跑过的命令，不是建议。全部在本仓库根目录执行，Python 用 `.venv/Scripts/python.exe`。

**1. 离线全量测试（不需要密钥）**

```bash
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m pytest -q -rs
```

结果：`317 passed, 0 skipped`。`examples/test-results.txt` 保存的就是这条命令的完整输出。此前记录的 `316 passed, 1 skipped` 是开发环境禁止本机回环连接时 `test_real_socket_roundtrip` 被跳过的结果；这次环境允许回环，该用例实际执行并通过。

**2. 真实运行结果的一致性校验**

```bash
.venv/Scripts/python.exe -m pytest tests/test_examples_consistency.py -q
```

结果：`45 passed`。这 45 条断言读的是已提交的 `examples/real/<case>/result.json` 与 `trace.jsonl`，会用 `data/` 重算时长与规则，逐镜核对，不需要重新调用模型。

**3. 真实模型批量运行**

```bash
.venv/Scripts/python.exe scripts/run_examples.py
```

按 `examples/cases.json` 顺序跑 10 个用例，写 `examples/real/<case>/` 下的四个产物，并重建 `examples/real/summary.json` 和 `summary.md`。共跑了三批：

- 第一批：`git log` 里的 `bfac6f7 chore: record real model run batch 1`，首个用例 2026-11-02T10:48:13Z 开始，末个用例 10:52:05Z 开始。
- 第二批：`ae98952 chore: record second real model run batch and test results`，首个用例 2026-11-02T10:54:37Z 开始，末个用例 11:04:58Z 开始。
- 第三批：首个用例 2026-11-03T10:56:48Z 开始，`03_no_material` 因中转站断连重跑，11:02:43Z 开始；这是当前 `examples/real/` 的内容。

（时间取自各用例 `trace.jsonl` 首行 `run_start.started_at`。）

三批最终都是 10/10 达到预期状态。前两批之间没有改代码、测试或 Prompt（`git diff bfac6f7 ae98952 -- src data tests scripts examples/cases.json examples/inputs` 无输出），第二批复跑只为看稳定性。第三批是收紧 Prompt、扩充词表后重跑的。

**4. 离线跑通流程**

```bash
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m script_agent --input examples/inputs/01_normal.json --mock-script examples/mock_scripts/06_over_duration_fixed.json
```

第二条 `--mock-script` 换掉模型，其余代码路径不变，产出 `completed`、30 秒、4 分镜，`script.md` 首行是 `[MOCK] 本次模型决策来自预设脚本，只验证流程，不证明真实模型效果。`

**5. 安装可复现性**

在临时目录另建一个干净虚拟环境，按 `requirements.txt` 安装后跑测试，结果同样是 `316 passed, 1 skipped`（当时该环境不允许本机回环）；用该环境的解释器执行上面的离线命令，同样是退出码 0、`script.md` 带 `[MOCK]` 首行。当前工作环境复跑是 `317 passed, 0 skipped`，差别就是那条 socket 用例。

**6. 配置与安全**

```bash
git ls-files | grep -E "\.env$|runs/"   # 无输出
git grep -n "sk-"                        # 只有源码里的脱敏正则、文档说明和测试用的假值
```

缺配置时的行为也验证过：`LLM_API_KEY` 与 `LLM_MODEL` 为空时，命令返回退出码 2、打印缺哪两项、不创建产物目录，也不会退回 Mock。

## 本人审查了什么

按“能不能复现”逐项核对，不只看文档结论：

- **验收点逐条对照产物。** 打开 `examples/real/` 下每个用例的 `result.json`，核对 `status`、`checks`、`total_duration_sec`、`source_ids` 与 `docs/03-evaluation.md` 表格里写的是否一致；再读 `script.md`，把每句涉及产品的旁白对照该分镜的 `claims.quote`，确认没有超出素材字面意思。第三批里 5 个 `completed` 的脚本是这样逐条读完的。
- **时长自己重算。** 不信任 `total_duration_sec`，按 `data/duration_config.json` 的口径（汉字每秒 4 个、每镜加 0.5 秒、单镜不少于 2 秒）手算 `01_normal` 和 `06_over_duration_fixed` 的分镜时长，与 `trace.jsonl` 里 `estimate_duration` 的返回逐镜对齐。
- **测试数字不采信文档。** 自己跑 `.venv/Scripts/python.exe -m pytest -q`，确认输出与 `examples/test-results.txt` 一致。加娱乐向素材库后重跑是 **317 passed**，比文档记的 316 多 1，原因是 `test_web_api.py` 里断言素材库列表的用例随新增库更新，用例总数没变。
- **文档里的命令逐条执行。** README 的离线 Mock、单用例运行、Web 工作台启动，`docs/04-ai-usage.md` 第 1–6 节列的验证命令都实际跑过；不接受“应该能跑通”这样的表述。
- **失败记录不放过。** `docs/03-evaluation.md` 里“状态全绿、脚本内容却有问题”那一条，自己用 `check_rules` 复现了“说过的话都会出现在屏幕上，样式也能改”这类句子确实被放行，确认这是真限制而不是文档写重了。

## 本人修改了什么

- **修了一条被新素材库打破的断言。** 新增娱乐向素材库（`examples/data_variants/entertainment/`）后，`tests/test_web_api.py:63` 仍断言 `/api/meta` 只返回两个素材库，全量测试变成 1 failed。改为断言三个库（`default`、`no_subtitle`、`entertainment`），并把 `src/script_agent/web/service.py` 的 `_DATA_SETS` 补上这一项。
- **补了娱乐向素材库本身。** 8 条素材（表情包、音效、变声、反转模板、文字动画、绿幕、变速、分屏），每个事实都能在素材原文里找到；场景词写进 `topic` 而不是 `tags`——因为 `tags` 不参与检索打分，却会触发 `UNCITED_FEATURE`，第一版把“表情包”放进 tags，结果画面里出现“模板”两个字就被判违规。
- **收紧娱乐向的品牌规则。** 去掉 `banned_terms` 里的“第一”（娱乐向脚本里“第一分钟”“第一次”太常见，而“第一”误拦“第一次”已经写进已知限制），并把“4K”“免费”“专业”“无水印”等加入 `unsupported_unless_in_source`。
- **确认了“纯剧情不可行”这个设计口子。** 实测零产品引用的脚本返回 `NO_SOURCE` 直接 fail（`src/script_agent/tools.py:231`），也就是说用户要求“不带产品植入的纯搞笑短剧”时，模型追问“是否接受不出现产品”其实是在问一个代码不允许的选项。这一条记在这里，是因为题目只要求产品事实可追溯，没有要求必须植入产品——当前实现比题目更严，属于自己加约束。
- **填了本次这几处个人内容。** 除本节外，`README.md` 的“实际用时与未完成部分”、`docs/05-retrospective.md` 的最后三节也一并填写。

## 本人独立验证了什么

以下都是自己动手跑出来的结果，不是转述文档：

- **真实模型能按工具结果改稿。** 用 Web 工作台跑“室友半夜整活，我用变声回敬他”（娱乐向素材库，目标 30 秒），`trace.jsonl` 记录 10 步：三次检索 → 首稿 26.25 秒 `pass` 但规则 `fail`（`UNCITED_FEATURE`、`MISSING_CLOSING_SLOGAN`）→ 改稿后 34.25 秒 `too_long` → 再改 24 秒 `pass` → 提交。动作确实跟着工具返回变，不是预设流程。
- **无素材路径的两种结局都复现了。** 同一句主题在**默认素材库**下三次检索全为 0 条，走 `ask_user` 返回 `needs_input`、`missing_info=["materials"]`；换成**娱乐向素材库**则命中 E03、E02 并最终 `completed`。同一份输入、同一个模型，只换素材目录，结局相反——这条差异是 `tests/test_examples_consistency.py::test_10_action_changes_when_materials_change` 断言的内容，我按同样方法手工复核了一遍。
- **边界值逐个数过。** 目标时长 `0`、`-5`、`abc`、`三十秒`、`601`、`true` 全部判为无效并给出原因；`45秒`、`45s`、`600`、`0.5` 解析正常。标题 20 字通过、21 字报 `TITLE_TOO_LONG`。品牌语少一个字或逗号都报 `MISSING_CLOSING_SLOGAN`，末尾多一个句号或感叹号不报。
- **重复分镜 id、引用不存在的素材、`quote` 非原文、纯标点凑时长** 分别报 `DUPLICATE_SHOT_ID`、`SOURCE_NOT_FOUND`、`CLAIM_NOT_IN_SOURCE`、`NO_SPEECH`，与文档列的违规码一致。
- **界面里的“编辑并校验”不花 token。** 改完分镜点重新校验，只调用 `estimate_duration` 和 `check_rules`；目标时长、素材库、已检索素材 ID 由服务端从记录里取，前端传的字段会被忽略。
- **没验证的部分：** 真实 socket 上的 Web 访问。开发环境禁止本机回环连接，`test_real_socket_roundtrip` 在这里被跳过；界面是在浏览器里手动点过的，但没有跑自动化端到端。

## 哪些部分本人能完整解释

- **循环本体（`src/script_agent/agent.py`）。** 一轮等于一次模型调用，模型返回 `tool_calls` 就逐个交给 `registry.execute`，结果以 `tool` 消息回传，直到终止动作或撞上 10 轮 / 20 次上限。`steps_used` 是实际发起的模型调用轮数，`tool_calls_used` 只统计真正执行的调用。
- **为什么工具结果是唯一事实来源。** 三层：`estimate_duration`、`check_rules`、`submit_script` 的 schema 里没有时长字段，模型多传会被 pydantic 丢弃；组装 `completed` 结果时每镜时长从同一哈希的估算结果按顺序取；目标时长只从请求读。
- **`draft_hash` 门禁为什么必要。** 每次估算/检查把判定记在 `checks_by_hash[sha256(draft)]`，`submit_script` 用自己的哈希去查，查不到就 `GATE_REJECTED`。没有这道门，模型可以检查一份、提交另一份。代价是改一个字就要重跑两个工具，`01_normal` 的第 7–10 步就是这个代价。
- **三个业务工具的口径。** 检索是词项匹配（NFKC + 小写，得分 = 命中词项数 + 标签是查询词项子串的个数）；时长是每镜 `max(2, 计时单位/4 + 0.5)`，计时单位 = 汉字数 + 每段连续字母数字的 `ceil(长度/2)`；规则检查是确定性的词表、数字、逐字引用和标签引用校验。
- **四种状态怎么产生。** `completed` 需要同一份草稿的时长和规则都 `pass` 才能提交；`needs_input` 只由 `ask_user` 产生；`failed` 来自 `report_failure` 或模型调用异常；`incomplete` 来自步数或工具调用上限。
- **能解释但没做到的：** 词表拦不住换说法的语义夸大（`docs/03-evaluation.md` 已知限制第 1 条）。这是确定性规则的固有代价，要解决得加独立的事实审校环节，本次没做。
