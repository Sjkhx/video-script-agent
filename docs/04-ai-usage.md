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

按“这个决定站不站得住”来审，而不是按“东西有没有做出来”：

- **范围取舍。** 题目只要求“至少 3 组输入覆盖正常、信息不足、工具失败”，实际做到了 10 个用例。多做的理由不是为了凑数：单靠 3 个用例无法体现“改变输入后动作是否随之变化”，而这是题目的审核要点之一。所以特意做了两组对照——`01` 对 `07`（只改目标时长 30→3 秒）、`01` 对 `10`（只改素材目录）。这两组是审出来的设计，不是顺手加的。
- **入口选择。** 题目允许 CLI / HTTP API / Notebook 三选一，选定 CLI 作评审入口，理由是复制粘贴最省事、最容易在评审时一次跑通。后来的 Web 工作台是在这个前提下的补充，不是替代——题目的“运行方式”仍然由 CLI 满足。
- **判据是否够用。** 这是花时间最多的一项。前两批真实运行 10/10 达标、测试全绿，但人工读脚本时发现“字幕放哪都行”“它能帮你搞定”这类句子，素材 P01 只有“支持字幕”一条事实。结论是测试只能证明“符合规则”，证明不了“规则够用”——判据本身有洞，测试就跟着一起漏。于是把判据从“`check_rules` 返回 pass”换成“每句话能不能对应到某条 `facts` 原文”，重新审了全部 5 个 `completed` 脚本，没有一个达标。
- **写结论前先跑一遍。** 文档里每个数字都从产物里取：`summary.json` 的 token 合计、`trace.jsonl` 的首行时间戳、`pytest` 的实际输出。复审时发现文档记的 `316 passed, 1 skipped` 与实跑不符，查下来是 `test_real_socket_roundtrip` 的 `skipif` 探针在这台机器上转为可用，已把差异写回 `docs/03-evaluation.md`。

## 本人修改了什么

只列由自己提出或拍板的改动，以及每一条的理由：

- **否掉 Agent 框架，用原生循环。** 讨论方案时考虑过用现成框架（有 tool 调用封装），但否掉了：题目明确说“框架名称不加分”，而这个任务只有单循环、单进程，框架带来的多 Agent、持久化在这个规模用不上，出错时还要在框架日志和自己的 Trace 之间来回对照。不用框架还有一个直接好处——`steps_used`、`tool_calls_used`、`next_action` 的语义完全自己定义，能一句话讲清，也方便写针对性测试。
- **坚持“时长只能由工具算”。** 否掉了“让模型自己报时长”的简化做法，因为那样审核时无法区分哪句话是模型的估算、哪句是事实。落地成三层约束：三个工具的 schema 里没有时长字段（模型传了也被 pydantic 丢弃）、结果组装时每镜时长从同一哈希的估算结果里取、目标时长只从请求读。代价是模型必须多调工具、多跑几轮。
- **要求以 TDD 推进，修复必须带能失败的回归测试。** 具体要求是：先写测试、确认它在旧实现上失败，再改实现。这一条不是空的，本次交付前补的 `INVALID_SHOT_ID` 就是按这个流程做的：先写 `test_non_positive_shot_ids_are_rejected`，跑出 `assert 'INVALID_SHOT_ID' in set()` 失败（RED），再在 `check_rules` 里加序号校验，转绿（GREEN）。选题也来自实测——分镜序号填 `0` 或 `-1` 原本能通过全部检查，产物表格里会出现“-1”这样的序号。
- **要求每个 Task 结束至少提交一次。** 目的是让审查能落在 diff 上，而不是靠回忆。到第二批真实运行为止是 18 个提交，交付整理后又加了 5 个。
- **决定补 Web 工作台。** 题目说界面非必需，还是决定加，理由是 CLI 只能看最终产物，看不到“模型为什么这么改”的过程，而这是本项目最想展示的东西。加的前提是不动决策逻辑：`trace.py` 和 `app.py` 只加一个可选的 `listener` 回调，不传时行为完全不变。
- **决定全量重跑第三批，而不是只修失败的用例。** 新规则下旧的 5 个 `completed` 脚本全部不再通过，如果只重跑失败的那几个，`examples/real/` 就成了两套规则的混合物，一致性测试失去意义。多花一倍时间换记录自洽，这个代价值得。
- **决定交付前的提交拆分。** 71 个文件拆成五笔：质量复查 + 第三批记录、娱乐向素材库、Web 工作台、`INVALID_SHOT_ID` 修复、文档。素材库必须排在 Web 工作台之前——`tests/test_web_api.py` 的断言依赖三个素材库，顺序错了那一笔就是红的。

## 本人独立验证了什么

只列能当场重跑的：

- **全量测试 `319 passed`**，与 `examples/test-results.txt` 一致；`tests/test_examples_consistency.py` 单独跑是 `45 passed`。
- **TDD 的红绿两步可复现。** `test_non_positive_shot_ids_are_rejected` 在加校验前是 `2 failed`（`AssertionError: assert 'INVALID_SHOT_ID' in set()`），加校验后是 `32 passed`。这条能现场演示。
- **同一主题换素材库结局相反。** “室友半夜整活，我用变声回敬他”：默认素材库三次检索全为 0 条、走 `ask_user`；娱乐向素材库命中 E03/E02 并 `completed`（24 秒）。
- **边界值。** 目标时长 `0`、`-5`、`abc`、`三十秒`、`601` 都判无效并给出原因；`45秒`、`45s`、`600` 正常。标题 20 字通过、21 字报 `TITLE_TOO_LONG`。
- **提交历史自洽。** 用 `git worktree add --detach` 逐笔检出跑测试，确认没有留下测试为红的中间节点。
- **没验证的部分：** 没有手算全部分镜时长；没有逐字比对全部 10 个用例的 `quote`；没有在干净虚拟环境重装；没有自动化端到端。

## 哪些部分本人能完整解释

- **为什么用原生循环而不是框架。** 一轮一次模型调用，`tool_calls` 逐个交给 `registry.execute`，结果以 `tool` 消息回传，直到终止动作或 10 轮 / 20 次上限。框架能提供的多 Agent、持久化在这里用不上，而自有循环让三个计数器语义清晰。
- **为什么时长只能来自工具。** 三层约束见“本人修改了什么”第二条。核心是：审核时不希望出现“这句话是模型的估计还是事实”这种无法回答的问题。
- **`draft_hash` 门禁。** 检查时按草稿内容算 `sha256` 记判定，提交时用自己的哈希查，查不到就 `GATE_REJECTED`。防的是“检查一份、提交另一份”。代价是改一个字就要重跑两个工具。
- **四种状态的来源。** `completed` 需同一份草稿的时长与规则都 `pass`；`needs_input` 只由 `ask_user` 产生；`failed` 来自 `report_failure` 或模型调用异常；`incomplete` 来自步数 / 工具调用上限。
- **能解释但没做到的：** 词表拦不住换说法的语义夸大（已知限制第 1 条）；`NO_SOURCE` 使纯剧情无法提交。两条都是设计取舍，不是遗漏。
