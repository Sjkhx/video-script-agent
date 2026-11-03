# 02 方案说明

## 调用流程

```text
输入 JSON + CLI 覆盖项
  │
  ├─ normalize_request：去空白、空串视为缺失、目标时长解析成秒（0/负数/无法解析/超 600 秒记为 invalid_fields）
  │
  ├─ 选模型
  │    ├─ --mock-script 指定文件 → ScriptedLLM（预设脚本，mode="mock"）
  │    └─ 否则读 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL → OpenAICompatibleLLM（mode="real"）
  │        缺配置直接退出码 2，不写任何产物，不静默回退 Mock
  │
  └─ run_agent：一轮 = 一次模型调用，最多 10 轮

       模型返回 tool_calls
         ├─ 没有 tool_calls → Trace 记一条 note，追加提醒，进入下一轮
         └─ 逐个执行（累计最多 20 次），每次 ToolRegistry.execute 走 8 类分支：
              1 工具名未知              → UNKNOWN_TOOL
              2 解析/校验参数           → INVALID_ARGS
              3 记下草稿与哈希
              4 故障注入 → 加载数据 → 执行业务工具
              5 更新运行状态（命中素材、检查结果）
              6 可预期问题（空查询、缺目标时长）单独报错
              7 提交把关（时长 + 规则都 pass 才通关）
              8 ask_user / report_failure 终止
            Trace 记一步：参数、返回摘要、决策依据
            结果以 tool 消息回给模型

       未终止且未达上限 → 回到“模型返回 tool_calls”

终止：
  submit_script 把关通过 → completed
  submit_script 被拒     → GATE_REJECTED 回给模型，循环继续
  ask_user               → needs_input
  report_failure         → failed
  达到 10 轮或 20 次调用 → incomplete
  模型调用异常           → failed（message 以“模型调用失败”开头）

收尾：Trace 回填每步的 next_action，写 result.json、script.md、trace.jsonl、trace.md
```

代码分工：`cli.py` 负责参数与配置校验，`app.py` 负责跑一次并落盘，`agent.py` 是循环本身（约 140 行），`registry.py` 是唯一的工具网关（校验、故障注入、状态、把关、组装结果），`tools.py` 是三个无状态的纯业务函数，`trace.py` 负责记录与脱敏。

## 模型决策与代码把关的分工

| 情况 | 模型决定 | 代码保证 |
|---|---|---|
| 缺关键信息 | 调 `ask_user` | 缺主题或目标时长时，`submit_script` 一定被拒 |
| 检索无结果 | 改写查询，或请求补充素材 | 引用本次没检索到的素材，规则检查不通过 |
| 超时长 | 怎么压缩，或者说明无法满足 | 目标时长取自请求，时长取自工具 |
| 规则不通过 | 怎么改写 | 改过的脚本必须重新检查 |
| 工具失败 | 重试或结束 | 失败不算通过，`retries_left` 如实返回 |
| 决策依据 | 每次调用填 `decision_note` | 必填，写入 Trace |

这张表是这套设计的核心边界：**凡是“该怎么改”都属于模型，凡是“算不算通过”都属于代码**。代码里没有“超时长就截断”“失败就重试”这类分支，只有上限、协议和判定。

## 工具设计

工具参数全部走 OpenAI function calling 的 JSON Schema，六个工具都要求一个 `decision_note`（非空字符串，说明这一步的依据）。`estimate_duration`、`check_rules`、`submit_script` 的 schema 里**没有时长字段和目标时长字段**，模型即使多传也会被 pydantic 丢弃，所以最终时长只可能来自工具计算。

### search_materials

| 项 | 内容 |
|---|---|
| 入参 | `query`（必填，可用空格或逗号分隔）、`top_k`（默认 5，范围 1–10）、`decision_note` |
| 返回 | `{ok: true, query, count, materials: [{id, topic, facts}]}` |
| 匹配 | 查询与素材文本都做 NFKC + 小写；得分 = 命中词项数 + “标签是某个查询词项的子串且不等于该词项”的个数；按得分降序、ID 升序取前 `top_k` |
| 副作用 | 命中素材 ID 并入本次运行的可引用集合 `retrieved_ids` |

### estimate_duration

| 项 | 内容 |
|---|---|
| 入参 | `title`、`shots`（每镜 `id`、`visual`、`narration`、可选 `claims`）、`decision_note` |
| 返回 | `{ok, shots: [{id, units, duration_sec}], total_duration_sec, target_duration_sec, min_allowed_sec, max_allowed_sec, verdict, overflow_sec, shortfall_sec}` |
| 算法 | 每镜计时单位 = 汉字数 + 每段连续字母数字 `ceil(长度/2)`；时长 = `max(min_shot_sec, units / chars_per_sec + pause_per_shot_sec)`，保留 2 位小数；总时长 = 各镜已舍入值之和 |
| 判定 | `total > target` → `too_long`；`total < target × lower_ratio` → `too_short`；否则 `pass` |

### check_rules

| 项 | 内容 |
|---|---|
| 入参 | `title`、`shots`、`decision_note` |
| 返回 | `{ok, verdict: "pass" 或 "fail", violations: [{code, shot_id, detail, evidence}]}` |
| 检查项 | 全脚本无引用、标题超长、引用素材不存在、引用素材本次未检索到、`quote` 不是素材原文、品牌禁用词、无素材支持的词、无素材支持的数字、未引用素材的标签被提到、末镜没有以品牌语结尾 |
| 违规码 | `NO_SOURCE`、`TITLE_TOO_LONG`、`SOURCE_NOT_FOUND`、`SOURCE_NOT_RETRIEVED`、`CLAIM_NOT_IN_SOURCE`、`BANNED_TERM`、`UNSUPPORTED_TERM`、`UNSUPPORTED_NUMBER`、`UNCITED_FEATURE`、`MISSING_CLOSING_SLOGAN` |

### submit_script / ask_user / report_failure

| 工具 | 入参 | 行为 |
|---|---|---|
| `submit_script` | `title`、`shots`、`risks`（可选）、`decision_note` | 用草稿内容算哈希，只有同一份草稿的 `duration` 和 `rules` 都是 `pass`、且请求不缺必填项才通关 → `completed`；否则返回 `GATE_REJECTED` 并逐条说明原因，循环继续 |
| `ask_user` | `missing_fields`、`questions`、`reason`、`decision_note` | 记录要问的内容 → `needs_input` |
| `report_failure` | `reason`、`unmet_requirements`（可选）、`failed_tools`（可选）、`decision_note` | 记录原因 → `failed` |

### 错误码

任何错误都不抛给调用方，统一作为观察结果回给模型：

| 错误码 | 含义 | 额外字段 |
|---|---|---|
| `UNKNOWN_TOOL` | 工具名不存在 | 无 |
| `INVALID_ARGS` | 参数不是合法 JSON，或校验不通过 | 无（不参与连续失败计数） |
| `TOOL_UNAVAILABLE` | 注入的故障；文案不含“注入”“测试”字样，避免影响模型判断 | `retries_left` |
| `DATA_UNAVAILABLE` | 数据文件缺失或损坏 | `retries_left` |
| `TOOL_EXCEPTION` | 工具内部异常 | `retries_left` |
| `MISSING_TARGET` | 请求没有有效目标时长，无法估算 | 无 |
| `GATE_REJECTED` | 提交被把关拒绝 | `reasons` |

`retries_left = max(0, 2 - 同一工具连续失败次数)`，工具成功后该计数归零。

## 两条真实路径

以下引用的数字与动作全部来自已提交的 `examples/real/` 记录，不是示意。

### 路径一：超时长后修正（`06_over_duration_fixed`）

输入 `examples/inputs/06_over_duration_fixed.json`：主题“给新手讲清剪刀鱼的字幕、模板和配音三个卖点”，目标 12 秒。

`examples/real/06_over_duration_fixed/trace.md` 记录的六步（这里按 Trace 的 `seq` 编号，与实际工具调用次数一致）：

| 步骤 | 动作 | 返回摘要 | 下一步 | 决策依据（模型自述） |
|---:|---|---|---|---|
| 1 | search_materials | 命中 3 条: P01, P02, P04 | estimate_duration | 需先获取剪刀鱼三个卖点的素材事实 |
| 2 | estimate_duration | 总时长 15.25s，目标 12s，判定 too_long，超出 3.25s | check_rules | 素材已拿到三个卖点，先估算 12 秒是否放得下 |
| 3 | check_rules | 判定 fail: UNSUPPORTED_TERM, UNCITED_FEATURE, MISSING_CLOSING_SLOGAN | estimate_duration | 同时检查脚本是否有事实或品牌表述问题 |
| 4 | estimate_duration | 总时长 9.75s，目标 12s，判定 pass | check_rules | 首版 15.25 秒超时且规则失败，压缩为四镜并修正引用 |
| 5 | check_rules | 判定 pass | submit_script | 同步复检压缩版是否清除了不支持词与漏引用 |
| 6 | submit_script | 提交通过 | END:completed | 压缩版时长 9.75 秒通过、规则 pass，提交同一份脚本 |

要点：第 2 步是**工具**判的 `too_long`（不是模型自述），第 3 步的违规项给出可执行的修改方向（包括词表拦下的“轻松”），第 4、5 步是同一份压缩稿的复检，第 6 步提交的也是同一份。最终 `result.json` 为 `completed`，4 个分镜，`total_duration_sec` 9.75，`checks` 两项都是 `pass`，`source_ids` 为 P01、P02、P04。第 2 条风险是模型自己写的：脚本“未展开任何使用效果、操作步骤或对比说明”。

这条路径覆盖了题目“参考实例”的结构：素材只有一句话 → 首稿超时长 → 按检查结果压缩 → 重新估算 → 通过后提交同一份。

### 路径二：素材变了，路径也变了（`01_normal` 对比 `10_materials_changed`）

两个用例的输入文件逐字节相同（`diff examples/inputs/01_normal.json examples/inputs/10_materials_changed.json` 无输出），唯一差别是 `cases.json` 里 `10` 用 `--data-dir examples/data_variants/no_subtitle`，那个目录的 `materials.json` 拿掉了 P01。

`01_normal`（`examples/real/01_normal/trace.md`，10 次工具调用 / 7 轮模型决策）走完了一个完整的“初稿→修正→通关”过程（“第 N 步”同前，指 Trace 的 `seq`）：

- 第 1–3 步换了三次查询，只拿到 P01（第 2 次 0 条）；
- 第 4 步首稿 26.25 秒，时长 `pass`；
- 第 5 步规则判 `fail`，违规里有 `BANNED_TERM:第一`、`UNCITED_FEATURE`、`MISSING_CLOSING_SLOGAN`；
- 第 6–7 步改稿后 26 秒 `pass`，但规则又拦下 `UNSUPPORTED_TERM:上手`；
- 第 8–9 步删掉“上手”后两项都 `pass`；第 10 步提交。

`10_materials_changed`（`examples/real/10_materials_changed/trace.md`，4 步）没有 P01，三次检索（含一次只用产品名）都是 0 条，第 4 步直接 `ask_user`，`missing_info=["materials"]`。

同一份需求、同一个模型，只换素材目录，一条走到 `completed`，一条走到 `needs_input`。这不是预设分支：检索结果不同，模型后续的选择就不同了。`tests/test_examples_consistency.py::test_10_action_changes_when_materials_change` 就是在核对这件事。

另两条值得对照的路径：

- **工具故障**：`04_tool_fail_transient` 第 2 步 `estimate_duration` 返回 `TOOL_UNAVAILABLE`、`retries_left=1`，同一轮的第 3 步 `check_rules` 正常返回 `fail`；第 4–5 步模型漏填分镜 `id`，两个工具都返回 `INVALID_ARGS`，它据此补上；第 7 步重估 `too_long`，第 9 步 `pass`，第 10 步提交成功。`05_tool_fail_permanent` 的 `check_rules` 连续两次不可用（`retries_left` 1→0），第 8 步 `report_failure`，`checks.rules` 是 `error` 而不是 `pass`。
- **明确失败**：`07_over_duration_infeasible` 目标 3 秒。第 2 步 3.5 秒 `too_long`，规则提示缺品牌语；第 4 步加上品牌语后 5 秒；第 7 步只留品牌语一镜，仍 3.25 秒 `too_long`；第 8 步 `report_failure`，理由写的是“仅品牌语一镜已3.25秒，超3秒上限”。`result.json` 里 `shots` 和 `total_duration_sec` 都是 `null`，只留 `unverified_draft` 和 `last_estimate` 作依据。

## 技术取舍

### 原生循环，不用 Agent 框架

循环本体就是 `agent.py` 里的一个 `for round_no in range(1, max_steps + 1)`：每轮一次 `llm.complete`，每个 tool_call 一次 `registry.execute`。用框架的代价是：多一层抽象、多一份版本说明、出错时要在框架日志和自己的 Trace 之间来回对照；收益（多 Agent、工具生态、持久化）在这个单循环任务里都用不上，而题目明确说“框架名称不加分”。原生实现还有一个直接好处：`steps_used`、`tool_calls_used`、`next_action` 的语义完全由自己定义，能一句话讲清，也方便写针对性测试。

### 工具结果是唯一事实来源

模型不能自己声明时长，也不能改目标时长。具体做法有三层：

1. `estimate_duration` / `check_rules` / `submit_script` 的 schema 不提供 `duration_sec`、`total_duration_sec`、`target_duration_sec`，多传的字段被 pydantic 丢弃（`tests/test_registry.py::test_submit_after_checks_uses_tool_durations` 里模型传了 `duration_sec=1`，最终结果仍是工具的 7.5）；
2. 组装 `completed` 结果时，每镜 `duration_sec` 从对应哈希的估算结果里按顺序取，不是从模型参数里取；
3. 目标时长只从请求读，模型没有入口修改。

代价是模型看不到“自己算的时长”，得靠工具返回；好处是审核时不需要判断哪句话是模型的估计、哪句话是事实。

### 用 `draft_hash` 防止检查后改稿

每次 `estimate_duration` / `check_rules` 先算 `sha256(draft.model_dump_json())`，把判定记在 `checks_by_hash[hash]`。`submit_script` 用自己的哈希去查，查不到就说明这份稿子没检查过，直接 `GATE_REJECTED`。

没有这道门，模型可以“检查一份、提交另一份”，检查记录就失去意义。代价是检查后改一个字都要重跑两个工具——`01_normal` 的第 7–10 步就是这个代价：第 7、9 步各做一次估算，第 8、10 步各做一次规则检查，因为第 8 步发现末镜缺引用后必须改稿再复检。这是设计上愿意付的成本。对应测试是 `test_changing_draft_after_checks_is_rejected`。

### Prompt 不透露语速和品牌语

`prompts.py` 的 system prompt 只说“时长以 `estimate_duration` 的返回为准”“规则以 `check_rules` 的返回为准”，不写“每秒 4 字”“品牌语是剪刀鱼，剪出属于你的故事”。

- 好处：修正过程必须真的看工具结果，Trace 里能观察到“模型按违规清单改”这件事，而不是模型心算后一次写对；也顺带验证了工具返回的信息量是否足够。
- 代价：多跑几轮。`01_normal` 的 Trace 第 5 步一次报出三类违规（`第一`、未引用标签、缺品牌语），第 7 步又拦下“上手”，模型据此改稿、补引用、再复检，到第 9 步才全部通过。生产环境更常见的做法是提前把语速口径和品牌语写进 Prompt，减少来回。这个项目选“晚告知”，是因为评估的重点是“模型能否根据工具结果调整”，而不是省 token。

### 用词表而不是模型做事实校验

`check_rules` 用确定性规则：`quote` 必须与素材 `facts` 逐字相同（NFKC 后比较）、数字必须是素材里出现过的完整数字、`banned_terms` 命中即违规、`unsupported_unless_in_source` 里的词只有在被引用的素材事实里出现才放行。

- 好处：可复现、可测试、零成本、毫秒级，判定理由能直接写给模型（`detail` 里就是改法）；一致性测试可以离线重算同一份结果。
- 代价：只能拦“词和数字”，拦不住换一种说法的夸大；中文数字覆盖不全；“第一次”会被“第一”误拦。这些都在 `docs/03-evaluation.md` 的已知限制里列明。这不是理论风险：早期两批真实运行里，就有“字幕放哪都行”这样超出素材的句子通过了检查，详见 `docs/03-evaluation.md` 的失败记录。之后才收紧了 Prompt、扩充了词表，但词表只能覆盖已知说法，防不住所有新说法。
- 为什么不用模型复核：再加一次模型判断会让“通过与否”变得不可复现，也把成本和延迟翻倍。代价是语义层面的编造只能靠 Prompt 约束和人工审阅，生产环境应该补上独立的事实审校环节。

### `decision_note` 只记录模型给出的简要依据

每次工具调用都要求 `decision_note`（非空，提示词里建议不超过 40 字）。它记的是“是哪个观察结果让我选这个动作”，例如“上轮15秒超出且规则fail，压缩旁白并修标题措辞”。

不记录模型内部思维：`trace.py` 里有一组 `_INTERNAL_KEYS`（`reasoning_content`、`thinking`、`chain_of_thought` 等），即使厂商把思维字段塞进返回或参数也会被丢掉。原因是题目只要求“简要决策依据”，不要求内部思维；而内部思维既不稳定也没法校验，写进 Trace 反而会让文件更大、更难读。代价是调试时看不到模型的推理细节，只能从 `decision_note` 和工具返回反推。

### 其他取舍

- **不做真实素材检索**：6 条合成素材配词项匹配，够覆盖“命中/不命中/换查询”三种情况，也便于把“改素材目录后动作变化”做成可复现的用例。真实场景应换成向量检索或关键词服务，接口形状不变。
- **评审入口是 CLI**：题目允许三选一，CLI 最省事，也最容易在评审时复制粘贴。下面的 Web 工作台是可选的查看和编辑界面，不是评审入口。
- **产物落盘而不是只打印**：`result.json` 给机器，`script.md` 给人改，`trace.jsonl` 给程序核对，`trace.md` 给人读。四种角色分开，比塞进一个大 JSON 更实用。

## Web 工作台

Web 工作台（`src/script_agent/web/`）在 CLI 之外提供一个本地界面：填写需求、实时看模型决策、编辑脚本并重新校验、导出结果、回放已提交的真实运行记录。

### 架构

```text
浏览器（原生 ES Modules）
  ↓ fetch / EventSource
ThreadingHTTPServer → Handler（只负责读写）
  ↓
WebApp.dispatch()（路由、Host 和 Origin 检查，不依赖 socket）
  ↓
WebService（编排）→ RunManager（后台线程跑 run_once，记录供 SSE 读取）
```

**Agent 的决策逻辑没有改动。** 核心代码只有 `trace.py` 和 `app.py` 加了一个可选的 `listener` 参数，用来把 Trace 记录实时交给 Web 层；不传时行为不变。活动运行结束后，状态一律从 `runs/web/<run_id>/` 的产物读取，所以刷新页面或重启服务后仍能打开。

### 技术取舍

- **用标准库而不是 FastAPI：** 这是只监听本机的单用户工具，标准库够用。这样不新增依赖，装完项目后一条命令就能启动。代价是路由和请求检查要自己写，大约两百行。
- **路由集中在 `dispatch()`：** 它接收方法、路径、请求头和请求体，返回响应对象，不碰 socket，接口测试因此不需要真实网络。
- **不用前端框架和构建工具：** 不需要 npm，也不依赖 CDN 和外部字体。代价是状态和重绘要自己管，界面复杂后会比框架吃力。
- **SSE 而不是 WebSocket：** 只有服务端单向推送，SSE 够用，浏览器还会自动重连。前端按记录序号去重，重连后不会重复显示步骤。

### 校验不能被前端绕过

`POST /api/verify` 只接收“来源”和“草稿”。目标时长、素材库、已检索素材 ID 和运行模式，全部由服务端从这条记录的 Trace 和结果里取，客户端多传的字段会被忽略。校验调用的是和 Agent 相同的 `estimate_duration`、`check_rules`，不调用模型。

### 安全边界

- 只监听 `127.0.0.1`，不提供 `--host`；`Host` 不是本机地址时拒绝，防 DNS 重绑定。
- POST 必须是 `application/json`；带 `Origin` 时必须与 `Host` 一致，防其他网站跨站触发运行。
- 客户端只传白名单 ID，运行 ID 过正则，静态文件走启动时建好的路径表，都不会把用户输入拼成文件路径。
- 模型和用户文本一律通过文本节点显示，并配合严格的 CSP（不允许内联脚本和外部资源）。
- 接口不返回密钥和 `LLM_BASE_URL`；运行崩溃时的错误文字先脱敏再写盘和返回。
