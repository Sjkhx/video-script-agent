# 05 回顾

## 施工记录

只写事实：实现中实际遇到的问题、怎么发现的、对应的修复提交。以下内容可在 `git log --oneline` 与各提交的 diff 中逐条核对。实现与真实运行历史共 18 个提交（`git log --oneline ae98952 | wc -l` = 18；加上本文档所在的提交，`git rev-list --count HEAD` = 19）。

### 1. 数字校验把“1”当成“12”的依据

**问题。** 事实校验最初用“数字是素材事实的子串”判断数字有没有素材支持。于是引用 P04 的 `提供 12 种中文配音音色`、脚本写 `提供 1 种音色` 也能通过，因为 `1` 是 `12` 的子串；同理 `80` 会被 `1080` 放行。

**发现方式。** 代码审查第一轮指出：数字门用的是子串包含，`提供 1 种音色` 引用 P04 的 `提供 12 种中文配音音色`、`支持导出 80P` 引用 P03 的 `支持导出 1080P`，两者都得到零违规和 `pass`。随后先补回归测试 `tests/test_rules.py::test_shortened_quantity_is_rejected`，确认在旧实现上失败（RED：`assert 'UNSUPPORTED_NUMBER' in set()`），再改实现（GREEN）。RED/GREEN 输出记在 `task-5-report.md`。

**修复。** `63e010b fix: require whole number tokens in fact matching`。新增 `_contains_number`，用 `(?<!\d)…(?!\d)` 要求数字是完整数字串。`1080` 仍然能匹配 `1080P`，`12` 匹配 `提供 12 种`，但 `1` 不再匹配 `12`。

### 2. 密钥可能进入 Trace（三轮修复）

**问题。** Trace 要求“密钥不进记录”，但初版只对部分字段做了处理，自由文本摘要、错误信息、字段名三条路径都可能带出密钥。

**发现方式。** 第一轮代码审查把三条路径都列为必修：自由文本摘要、错误信息、字段名。修复过程中又逐路径复查，发现 `_clip` 先截断后替换，跨截断点的密钥会被切成残片（残片不再匹配 `sk-` 正则）；以及 `secrets` 传单个字符串时被逐字符迭代成“每个字符都是密钥”。

**修复（三个提交，一个比一个深）：**

- `468c06b fix: redact trace summaries, key names and configured secrets`：摘要、参数名、已配置密钥全部纳入脱敏。
- `8cdf412 fix: redact before clipping and normalize bare-string secrets`：改为先脱敏再截断；`secrets` 传单字符串时按一个密钥处理。
- `ee6bf3e fix: pass secrets into summary redaction and cover error paths`：把密钥列表传进摘要函数内部，并覆盖错误分支。

**后续。** `9000598 test: cover direct summary redaction paths` 整理测试。复查时发现其中一条新测试在修复前的提交上也能通过（没有区分力）：因为 `step()` 层还有一道外层脱敏，掩盖了 fallback 密钥的缺陷。保留了一条确实会失败的用例（裸字符串被逐字符替换，旧实现产生 5 个以上星号），另一条降级为直接调的回归覆盖。

### 3. 引用原文里的竖线撑破 Markdown 表格

**问题。** `script.md` 用 Markdown 表格列分镜，`claims` 的 `quote` 直接拼进单元格。素材原文里只要有一个 `|`，整行就会错位。

**发现方式。** Task 9 自检渲染逻辑时发现：表格单元格里的竖线没有转义，`quote` 或画面描述里含 `|` 就会多切出列。修复后逐行统计行内竖线数量固定为 9（6 列 + 边界）。

**修复。** `adfc6fc fix: escape table pipes in claim quotes`，在 `_claims_text` 里转义 `|`。

### 4. 故障计划写进 Trace 变成 `null`

**问题。** `FaultPlan` 是 dataclass，`TraceRecorder` 的 `fault` 参数按 `dict | None` 处理，直接传 dataclass 会被判为非 dict，`trace.jsonl` 首行写成 `"fault": null`，注入记录就丢了。

**发现方式。** 做对照实验：把 dataclass 直接传进去，读 `trace.jsonl` 首行，确认是 `null`。

**修复。** 在 `app.py` 加 `_fault_record`，先转成 `{"tool": ..., "times": ...}` 再交给 `TraceRecorder`。该修正随 `14c20b2 feat: add cli, markdown output and offline mock entry` 提交，并由 `tests/test_cli.py::test_fault_plan_is_serialized_into_trace` 固定。

### 5. 两批真实运行：没有失败用例

**事实。** 两批各 10 个用例，都是 10/10 达到预期状态（`bfac6f7`、`ae98952` 的 `summary.json` 里 `status_ok` 全为 `true`）。两批之间没有改代码、测试、Prompt 或输入，`git diff --stat bfac6f7 ae98952 -- src data tests scripts examples/cases.json examples/inputs` 无输出；第二批只包含 `examples/real/` 与 `examples/test-results.txt`。

**两批之间唯一的差异**是模型输出的随机性：动作序列和 token 数不同，例如 `08_rule_conflict` 第一批 11 次工具调用、第二批 8 次，`01_normal` 第一批 8 次、第二批 11 次。第二批复跑就是为看稳定性，没有做任何调整。

**另外记录一处观察：** 两批 `trace.jsonl` 里都没有出现 `GATE_REJECTED`。提交把关的拒绝分支由单元测试覆盖（`tests/test_registry.py::test_submit_without_checks_is_rejected`、`test_changing_draft_after_checks_is_rejected`），两批真实运行恰好都没触发。

### 6. 测试数量变化

- Trace 与模型客户端完成后（`93a20e8`），全量是 148 passed（`.superpowers/sdd/2026-11-02-video-script-agent/task-7-report.md` 的记录）。
- Task 10 加入一致性测试、尚未跑真实批次时，离线是 `194 passed, 45 skipped`，跳过原因是“尚未生成真实运行结果”（同目录 `task-10-report.md` 的记录）。
- 两批真实运行提交后，`examples/test-results.txt` 记录 `240 passed`，无跳过。

### 7. 已知限制未在实现阶段解决

以下问题在评估文档里作为已知限制保留，没有在本次实现中修复（详见 `docs/03-evaluation.md`）：词表与数字校验拦不住换说法的夸大、中文数字覆盖不全、“第一”会误拦“第一次”、旁白与 `quote` 之间无语义校验、语速是固定估算、素材级授权、无工具调用的轮次不计 token。它们都是设计取舍或需要语义模型才能解决的问题，不是遗漏。

## 最难问题

【需本人填写】

## 学习收获

【需本人填写】

## 下一步

【需本人填写】
