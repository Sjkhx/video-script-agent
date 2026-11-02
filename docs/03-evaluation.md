# 03 评估

## 结论

- 10 个真实模型用例，**两批独立运行，两批 10/10 都达到预期状态**（`examples/real/summary.json` 中 `status_ok` 全为 `true`）。
- 全量测试 **239 passed，0 skipped，0 failed**（`examples/test-results.txt`，本机复跑同结果）。
- 模型：`deepseek-v4.1-flash`，通过 OpenAI 兼容接口调用。
- 运行时间：第一批 2026-11-02T10:48:13Z 起（commit `bfac6f7`），第二批 2026-11-02T10:54:37Z–11:04:58Z（commit `ae98952`，即当前 `examples/real/` 内容）。日期均为 2026-11-02。

## 验收映射表

预期取 `examples/cases.json` 的 `expect.status`，实际取 `examples/real/summary.json`（当前第二批）与对应 `result.json`。模型 `deepseek-v4.1-flash`，运行日期 2026-11-02。

| 验收点 | 用例 | 路径（`examples/real/<case>/`） | 预期 | 实际（`summary.json` + `result.json`） |
|---|---|---|---|---|
| 正常生成 | `01_normal` | `examples/real/01_normal/` | `completed`，`must_cite=["P01"]` | `completed`，`status_ok=true`，`steps_used=7`、`tool_calls_used=11`、`total_tokens=37210`；`total_duration_sec=25.5`（目标 30），`checks={duration:pass, rules:pass}`，`source_ids=[P01,P02,P03]` |
| 缺关键信息 | `02_missing_target` | `examples/real/02_missing_target/` | `needs_input` | `needs_input`，`status_ok=true`，1 步 1 次调用，`total_tokens=2701`；`missing_info=["target_duration_sec"]`，`shots=null` |
| 无素材 | `03_no_material` | `examples/real/03_no_material/` | `needs_input` | `needs_input`，`status_ok=true`，4 步 4 次调用（3 次检索 + `ask_user`），`total_tokens=11478`；`missing_info=["materials"]` |
| 工具失败（可恢复） | `04_tool_fail_transient` | `examples/real/04_tool_fail_transient/` | `completed`，`must_cite=["P01"]` | `completed`，`status_ok=true`，8 步 12 次调用，`total_tokens=38697`；第 4 步 `estimate_duration` 注入故障、`retries_left=1`、`injected_fault=true`，第 10 步 `pass`，第 12 步提交 |
| 工具失败（明确失败） | `05_tool_fail_permanent` | `examples/real/05_tool_fail_permanent/` | `failed` | `failed`，`status_ok=true`，6 步 8 次调用，`total_tokens=24051`；`check_rules` 两次 `TOOL_UNAVAILABLE`（`retries_left` 1→0），`checks={duration:pass, rules:error}`，`shots=null` |
| 超时长后修正 | `06_over_duration_fixed` | `examples/real/06_over_duration_fixed/` | `completed`，`must_cite=["P01","P02","P04"]` | `completed`，`status_ok=true`，5 步 7 次调用，`total_tokens=22948`；`total_duration_sec=12.0`（目标 12），5 分镜，`checks` 两项 `pass` |
| 超时长后明确失败 | `07_over_duration_infeasible` | `examples/real/07_over_duration_infeasible/` | `failed` | `failed`，`status_ok=true`，4 步 6 次调用，`total_tokens=14498`；`shots=null`、`total_duration_sec=null`，`last_estimate.verdict=too_long`（3.25 秒 / 目标 3 秒），`checks={duration:too_long, rules:pass}` |
| 规则风险、不编造 | `08_rule_conflict` | `examples/real/08_rule_conflict/` | `completed` / `needs_input` / `failed` 均可 | `completed`，`status_ok=true`，6 步 8 次调用，`total_tokens=26717`；`total_duration_sec=24.75`，`checks` 两项 `pass`；首条 `risks` 写明“效率提升 80%”无素材来源、未写入脚本 |
| 改写查询 | `09_query_rewrite` | `examples/real/09_query_rewrite/` | `completed` / `needs_input` 均可 | `completed`，`status_ok=true`，6 步 8 次调用，`total_tokens=26201`；`total_duration_sec=27.25`，仅引用 P01 |
| 改检索结果后动作变化 | `10_materials_changed` | `examples/real/10_materials_changed/` | `needs_input` | `needs_input`，`status_ok=true`，4 步 4 次调用，`total_tokens=11442`；3 次检索均 0 条后 `ask_user`，`missing_info=["materials"]` |

`summary.json` 里另有两列值得对照：`model` 全部为 `deepseek-v4.1-flash`，`total_tokens` 合计 215943。首批（`git show bfac6f7:examples/real/summary.json`）同样 10/10 达标，`total_tokens` 合计 236813。

每个用例的四个产物：

| 文件 | 内容 |
|---|---|
| `result.json` | 最终结果（上面表格里的数值都出自这里） |
| `script.md` | 可编辑的 Markdown 脚本；失败时为未通过检查的草稿，标题写明“未通过检查，不可直接使用” |
| `trace.jsonl` | 逐步记录，含工具参数、完整返回、决策依据、`next_action`、每轮 token 用量 |
| `trace.md` | 同一份记录的六列表格：步骤、动作、关键参数、返回摘要、下一步、决策依据 |

## 测试结果

`examples/test-results.txt` 是 `python -m pytest -q -rs > examples/test-results.txt 2>&1` 的输出（Git Bash）。本机复跑同一条命令，输出与该文件逐字一致，只差最后一行耗时（2.45s vs 2.28s）：

```text
........................................................................ [ 30%]
........................................................................ [ 60%]
........................................................................ [ 90%]
.......................                                                  [100%]
239 passed in 2.45s
```

即 **239 passed，0 skipped，0 failed**。本机另跑 `.venv/Scripts/python.exe -m pytest -q` 也是 `239 passed`。其中 `tests/test_examples_consistency.py` 单独运行是 **45 passed**，全部依赖已提交的 `examples/real/`。

分层看：

| 测试文件 | 数量 | 作用 |
|---|---:|---|
| `tests/test_catalog.py` | 5 | 数据加载与损坏数据 |
| `tests/test_models.py` | 20 | 请求规范化、目标时长边界、结果模型 |
| `tests/test_search.py` | 13 | 检索打分与 `top_k` |
| `tests/test_duration.py` | 13 | 计时单位与时长判定 |
| `tests/test_rules.py` | 15 | 十类违规与误报边界 |
| `tests/test_registry.py` | 18 | 参数校验、故障注入、提交把关、结果组装 |
| `tests/test_llm.py` | 11 | 真实/脚本两种客户端、错误与脱敏 |
| `tests/test_trace.py` | 66 | Trace 记录、脱敏、摘要渲染 |
| `tests/test_agent_loop.py` | 18 | 循环、上限、无动作提醒、终止动作 |
| `tests/test_cli.py` | 15 | 退出码、覆盖项、编码、密钥不入产物 |
| `tests/test_examples_consistency.py` | 45 | 核对已提交的真实运行结果 |

一致性测试里最重的几条：

- `test_completed_results_recompute_exactly`（按用例参数化）：用 `data/` 重算每个 `completed` 用例的时长与规则，逐镜核对 `duration_sec`、核对 `quote` 是 `catalog.material(...).facts` 的原文、核对 `source_ids` 与 claims 一致、核对 `must_cite`。
- `test_trace_steps_are_complete`：每一步都必须有 `action`、`result_summary`、`next_action`、`args`，且非 `INVALID_ARGS` 的步骤必须有 `decision_note`。
- `test_status_and_real_mode`：`mode` 必须是 `real`，Trace 首行的模型不能是 `scripted`，`run_end.total_tokens > 0`，`steps_used` 不超过 `max_steps`。
- `test_at_least_two_distinct_paths`：10 个用例的动作序列至少有 2 种不同。

`test_completed_results_recompute_exactly` 的测试体里有一个 `pytest.skip` 保护（期望 `completed` 但该次没走到 `completed` 时跳过）。第二批的 `08`、`09` 都走到了 `completed`，所以没有跳过；`test-results.txt` 里也没有 skipped 统计，与“0 skipped”一致。

## 路径差异

### 同一输入，只改目标时长（`01` → `07`）

两个输入文件只差 `target_duration_sec`：

```text
01_normal.json                 target_duration_sec: 30
07_over_duration_infeasible.json target_duration_sec: 3
```

| | `01_normal` | `07_over_duration_infeasible` |
|---|---|---|
| 动作路径 | 11 次工具调用（7 轮模型决策）：检索×3 → 估算 → 检查 → 检索 → 估算 → 检查 → 估算 → 检查 → 提交 | 6 次工具调用（4 轮模型决策）：检索 → 估算 → 检查 → 估算 → 检查 → `report_failure` |
| 时长结果 | 40.25 秒（`too_long`）→ 25.5 秒（`pass`） | 5 秒（`too_long`）→ 3.25 秒（`too_long`） |
| 结局 | `completed`，25.5 秒 | `failed`，`shots=null` |

`07` 的失败理由来自工具而不是猜测：最后一镜必须带品牌语，仅品牌语一镜就是 3.25 秒，超过 3 秒硬上限（`examples/real/07_over_duration_infeasible/result.json` 的 `last_estimate` 里是 `shots[0].units=11`、`duration_sec=3.25`、`overflow_sec=0.25`）。

### 同一输入，只改素材（`01` → `10`）

`examples/inputs/01_normal.json` 与 `examples/inputs/10_materials_changed.json` 逐字节相同（`diff` 无输出）；`cases.json` 里 `10` 的 `data_dir` 指向 `examples/data_variants/no_subtitle/`，该目录的 `materials.json` 没有 P01（只有 P02–P06）。

| | `01_normal` | `10_materials_changed` |
|---|---|---|
| 检索结果 | 命中 P01 → 再命中 P01 → 0 条 | 0 条 → 0 条 → 0 条（第三次只用“剪刀鱼”） |
| 后续动作 | 继续写稿、估算、检查、修正、提交 | `ask_user`，`missing_info=["materials"]` |
| 结局 | `completed`（25.5 秒） | `needs_input` |

两次运行用的是同一个模型、同一份 Prompt、同一个输入，唯一的变量是素材目录；模型在检索为空后走了完全不同的分支。`tests/test_examples_consistency.py::test_10_action_changes_when_materials_change` 把这个差异固定成断言。

### `01` 内部的“改稿后复检”

`01` 的第 4–10 步也能看到动作随检查结果变化：首稿 40.25 秒被判 `too_long`、规则判 `fail`（标题超长、`第一`、`30`、未引用标签、缺品牌语）→ 模型回头检索 P02 的“竖屏”相关素材 → 压到 25.5 秒 → 规则只剩一条 `UNCITED_FEATURE` → 复检 `pass` → 提交。逐条见 `examples/real/01_normal/trace.jsonl` 的 `result.violations`。

## 失败记录

### 两批真实运行

**两批都没有用例偏离预期。** 第一批（`bfac6f7`）10/10 `status_ok=true`；第二批（`ae98952`，即当前 `examples/real/`）同样 10/10。

两批之间**没有做任何改动**：`git diff --stat bfac6f7 ae98952 -- src data tests scripts examples/cases.json examples/inputs` 无输出；`git show --name-only ae98952` 只包含 `examples/real/` 和 `examples/test-results.txt`。`src/script_agent/prompts.py` 自 `f63f9e1` 之后没有再改动，所以两批之间也没有 Prompt 改动。

第二批复跑的目的就是看稳定性，不是修问题。差异出现在动作序列和 token 上，符合“真实模型每次输出不同”的预期：

| 用例 | 第一批动作数 | 第二批动作数 | 第一批 tokens | 第二批 tokens |
|---|---:|---:|---:|---:|
| `01_normal` | 8 | 11 | 28185 | 37210 |
| `04_tool_fail_transient` | 10 | 12 | 37390 | 38697 |
| `06_over_duration_fixed` | 6 | 7 | 20410 | 22948 |
| `08_rule_conflict` | 11 | 8 | 49231 | 26717 |
| `09_query_rewrite` | 10 | 8 | 34376 | 26201 |

两批的动作序列都不同（例如 `08_rule_conflict` 第一批 11 次调用、第二批 8 次），但状态全部达标。已提交的 `examples/real/` 是第二批。

另外：两批的 `trace.jsonl` 里都没有 `GATE_REJECTED`（对 `examples/real/*/trace.jsonl` 逐个 `grep -c`，结果全为 0）。提交把关确实会拒绝“检查后改稿”的情况，但它在单元测试 `tests/test_registry.py::test_changing_draft_after_checks_is_rejected` 和 `test_submit_without_checks_is_rejected` 里被直接验证，两批真实运行恰好都没有触发。

### 开发过程中发现并修复的缺陷

这些不是“真实运行失败”，而是实现过程中发现的实际缺陷；它们都有修复提交，记录在此以便与 `git log` 对应：

| 问题 | 发现方式 | 修复 commit |
|---|---|---|
| 数字校验把“1”当成“12”的合法依据：引用 P04 的“提供 12 种中文配音音色”，脚本写“提供 1 种音色”也能通过 | 实现后自查数字匹配逻辑，发现用的是子串包含；加了“数字必须完整”的回归测试 | `63e010b fix: require whole number tokens in fact matching` |
| Trace 的自由文本摘要没有脱敏，密钥可能进 `trace.jsonl` | 实现 Trace 后按“密钥不写入 Trace”逐路径推演 | `468c06b fix: redact trace summaries, key names and configured secrets` |
| 先截断再脱敏：密钥跨截断点被切成残片后无法再匹配 | 复查脱敏顺序 | `8cdf412 fix: redact before clipping and normalize bare-string secrets` |
| 摘要内部的错误信息未拿到密钥列表，非 `sk-` 形状的密钥漏网 | 复查 `summarize_observation` 的调用链 | `ee6bf3e fix: pass secrets into summary redaction and cover error paths` |
| 两条新增测试在修复前的提交上也能通过（没有区分力） | 复查测试是否真的能失败 | `9000598 test: cover direct summary redaction paths` |
| 引用原文里含竖线字符会撑破 `script.md` 的表格 | 渲染时逐行核对竖线数量 | `adfc6fc fix: escape table pipes in claim quotes` |
| 故障计划是 dataclass，直接传给 `TraceRecorder` 会写成 `fault: null` | 对照实验：直接把 dataclass 传进去，`trace.jsonl` 首行确实是 `null` | 随 `14c20b2 feat: add cli, markdown output and offline mock entry` 一并修正（`app._fault_record`） |

## Mock 边界

单元测试和 `--mock-script` 只验证流程，**不证明真实模型决策效果**：

- 单元测试用的是 `ScriptedLLM`，预设的每一步由人写死，验证的是代码路径（上限、把关、错误回传、判定、脱敏、渲染），不是模型能力。
- `--mock-script` 同理，产物里 `mode="mock"`，`script.md` 首行是 `[MOCK] 本次模型决策来自预设脚本，只验证流程，不证明真实模型效果。`
- 模型决策效果只看 `examples/real/`：那 10 个目录是真实接口调用的产物，`mode="real"`，`trace.jsonl` 首行记录了模型名与 `started_at`。
- 离线（没有密钥）时 `python -m pytest -q` 仍然通过：`tests/test_examples_consistency.py` 只在 `examples/real/summary.json` 缺失时整体跳过，本仓库已提交该文件，所以离线也会实际执行这 45 条核对，但核对的是**已提交的记录**，不会重新调用模型。

## 已知限制

按方案要求列出的六条：

1. **词表和数字校验拦不全语义上的夸大。** 换一种说法描述素材没有的能力就查不出来。实测：引用 P01 的“支持字幕”，旁白写“把说过的话变成屏幕上的字，不用自己打”，`check_rules` 返回空违规列表——这句话其实扩展了“支持字幕”的含义。
2. **中文数字只校验带倍、成、折和“百分之”的写法。** `_NUMBER_PATTERN` 覆盖 `百分之[一二三四五六七八九十百]+` 和 `[一二三四五六七八九十两]+(?:倍|成|折)`；实测引用 P04 的“提供 12 种中文配音音色”、旁白写“提供十二种中文配音音色”，`check_rules` 返回空——写法本身没被当成数字，所以既不算不支持、也不算支持。
3. **旁白是否真实表达了 `claims` 引用的内容，没有语义校验。** 逐字校验只保证 `quote` 是素材原文，不保证旁白用了这条事实；第 1 条的实测就是这个限制的具体表现。
4. **“第一次”这类正常表达会被“第一”误拦。** `banned_terms` 是子串匹配，没有词边界。实测旁白“第一次做短视频，先开声音”会报 `BANNED_TERM`（证据 `第一`）。`01_normal` 首稿的标题“……新手第一次加字幕”也因此被拦。
5. **语速是固定估算，不是真实配音时长。** 汉字每秒 4 个、每镜加 0.5 秒、单镜不少于 2 秒，都是 `data/duration_config.json` 里的常量；真人口播、语速变化、配音停顿都会让实际时长不同。
6. **真实模型每次输出不同，示例只代表当次运行。** 两批记录的动作序列与 token 都不同（见上表），不能拿某一次的具体步骤当作“模型一定会这样走”。

本项目实际存在的另外两条：

7. **素材级授权：引用某条素材后，该素材的其它事实也被视为有据。** 检查的粒度是“这条素材被引用了没有”，不是“这句话对应哪一条事实”。实测：引用 P05 的“基础版免费使用”，旁白写“会员价 18 元/月，按需选择”，`check_rules` 返回空；P05 的 facts 里确实同时有这两条，所以结论不算编造，但引用关系并不精确。同样的机制意味着：只要某条素材被引用，该素材任意一条事实都可以被写成旁白，即使 `quote` 写的是另一条。
8. **某一轮模型没有调用工具时，这一轮没有 token 用量记录。** Trace 只在执行工具时记 `usage`，`run_end.total_tokens` 按轮累加这些记录，所以“只回复文字”的轮次不计入。实测：用一个假模型在第 1 轮返回“先想想”（报 15 tokens、无工具调用）、第 2 轮调 `ask_user`（报 120 tokens），`trace.jsonl` 里第 1 轮只有 `note` 且不带 `usage`，`run_end.total_tokens` 是 120 而不是 135。两批真实运行没有出现无动作轮次（`grep '"type": "note"' examples/real/*/trace.jsonl` 无命中），所以已提交的 `total_tokens` 不受影响；但如果模型出现空转，统计会偏低。
