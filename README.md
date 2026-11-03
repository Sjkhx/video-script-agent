# 短视频脚本 Agent（第 4 题）

一个由真实模型驱动 ReAct 决策的短视频脚本 Agent：模型自己选择动作、看工具结果、再决定下一步，代码只做把关；脚本产出事实可追溯、时长经工具验证。**未使用 Agent 框架**，只用 `openai` 的兼容客户端加原生循环。

## 环境要求

- Python 3.12 或更高（本仓库在 3.12.13 上开发并验证）
- 任意 OpenAI 兼容的 chat completions 接口和密钥（离线模式不需要）

## 安装

两套命令任选其一，都在仓库根目录执行。`Activate.ps1` 和 `activate` 都在 `.venv/Scripts/` 下，已确认存在。

**PowerShell**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

若激活脚本被执行策略拦住，可直接用解释器全路径，不必激活（下面所有 `python ...` 换成 `.\.venv\Scripts\python.exe ...`）：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

**Git Bash**

```bash
python -m venv .venv
source .venv/Scripts/activate
python -m pip install -r requirements.txt
```

`requirements.txt` 最后一行是 `-e .`，所以安装同时会把 `src/` 装成可导入的 `script_agent` 包；不激活虚拟环境时请统一写成 `.venv/Scripts/python.exe -m script_agent ...`。

## 配置模型

复制 `.env.example` 为 `.env`，填三项：

```text
LLM_BASE_URL=      # OpenAI 兼容接口地址，例如 https://<host>/v1；留空则用 SDK 默认地址
LLM_API_KEY=       # 你的密钥
LLM_MODEL=         # 接口侧支持的模型名
```

任何 OpenAI 兼容接口都可以用：代码只读这三个环境变量，不写死厂商或模型名。本仓库 `examples/real/` 里的记录来自 `deepseek-v4.1-flash`。

`.env` 在 `.gitignore` 里，不会进仓库。真实密钥不打印、不写入 Trace。

## 离线运行（无需密钥）

```bash
python -m pytest -q
python -m script_agent --input examples/inputs/01_normal.json --mock-script examples/mock_scripts/06_over_duration_fixed.json
```

`--mock-script` 用 `examples/mock_scripts/` 里的预设脚本代替模型，只走一遍真实代码路径（同上限、同把关）。产物写在 `runs/<时间戳>/`，也可以用 `--out-dir` 指定。

**边界：Mock 只验证流程，不证明真实模型决策效果。** 预设脚本里的决策是人写的，模型会不会这么走，只能看 `examples/real/` 下的真实运行记录。

补充：`--mock-script` 只是替换模型，不会跳过把关。`examples/mock_scripts/06_over_duration_fixed.json` 第一版被 `estimate_duration` 判为 `too_long`，压缩后才提交成功，可以在产物的 `trace.md` 里看到。

## 真实运行

```bash
python -m script_agent --input examples/inputs/01_normal.json
python scripts/run_examples.py
```

第一条跑单个用例，产物在 `runs/<时间戳>/`。第二条按 `examples/cases.json` 批量跑 10 个用例，直接覆盖写入 `examples/real/<case>/` 并重建 `examples/real/summary.json`、`examples/real/summary.md`；注意这会覆盖仓库里已提交的运行记录（想保留就先复制一份或用 git 恢复）。只重跑一个用例用 `python scripts/run_examples.py --case 06_over_duration_fixed`，其余用例的记录会保留。

## Web 工作台（可选）

题目要求的运行入口仍是上面的 CLI。Web 工作台是后加的可选界面，没有改动 Agent 的决策逻辑，也不新增依赖。

```bash
python -m script_agent.web --port 8765
```

启动后用浏览器打开 `http://127.0.0.1:8765`。

- **没配置模型也能用：** 可以查看已提交的 10 条真实运行记录，也可以跑离线演示。Mock 的边界同上：只验证流程，不证明真实模型决策效果。
- **实时轨迹：** 运行时逐步显示模型的动作、工具结果和决策依据。
- **时间线：** 分镜按秒数显示长度，标出目标线和合格区，超时长的部分用红色斜纹。
- **编辑并校验：** 分镜可以直接修改。重新校验只调用确定性的时长和规则工具，不调用模型，也不消耗 token。目标时长、素材库和已检索素材都由服务端根据这条记录决定，前端改不了。
- **限制：** 只监听本机；同一时间只跑一个任务；运行产物保存在 `runs/web/<run_id>/`，重启服务后仍能打开。

## 退出码

- 单次运行（`python -m script_agent ...`）：`0` 完成或需要补充信息；`1` 失败或未完成；`2` 用法或配置错误（缺密钥时不会写任何产物，也不会静默退回 Mock）。
- 批量运行（`python scripts/run_examples.py`）：`0` 表示所有用例都达到 `cases.json` 里的预期状态；`1` 表示至少一个用例偏离预期；`2` 表示配置或用例文件有误。`05`、`07` 的预期状态就是 `failed`，达标时不返回 `1`。

## 评审入口

五个必须验收点 → 复现命令 → 已提交的真实运行记录。每个目录下都有 `result.json`、`script.md`、`trace.jsonl`、`trace.md` 四个产物；“实际状态”一列取自 `examples/real/summary.json` 与对应 `result.json`。

| 验收点 | 复现命令 | 结果路径 | 实际状态 |
|---|---|---|---|
| 正常生成 | `python -m script_agent --input examples/inputs/01_normal.json` | `examples/real/01_normal/`（`result.json`、`script.md`、`trace.jsonl`、`trace.md`） | `completed`，5 分镜，26 秒 / 目标 30 秒，引用 P01 |
| 缺关键信息 | `python -m script_agent --input examples/inputs/02_missing_target.json` | `examples/real/02_missing_target/` | `needs_input`，`missing_info=["target_duration_sec"]`，一次 `ask_user` 结束 |
| 无素材 | `python -m script_agent --input examples/inputs/03_no_material.json` | `examples/real/03_no_material/` | `needs_input`，三次不同查询均 0 条后 `ask_user`，`missing_info=["materials"]` |
| 工具失败 | `python -m script_agent --input examples/inputs/04_tool_fail_transient.json --fail-tool estimate_duration --fail-times 1`<br>`python -m script_agent --input examples/inputs/05_tool_fail_permanent.json --fail-tool check_rules --fail-times -1` | `examples/real/04_tool_fail_transient/`（可恢复）；`examples/real/05_tool_fail_permanent/`（不可恢复） | `04` 为 `completed`（第 2 步故障、`retries_left=1`，重估后通过）；`05` 为 `failed`（`check_rules` 两次不可用，`retries_left=0` 后 `report_failure`） |
| 超时长后的修正或明确失败 | `python -m script_agent --input examples/inputs/06_over_duration_fixed.json`<br>`python -m script_agent --input examples/inputs/07_over_duration_infeasible.json` | `examples/real/06_over_duration_fixed/`（修正）；`examples/real/07_over_duration_infeasible/`（明确失败） | `06` 为 `completed`，首估 15.25 秒 `too_long`，压到 9.75 秒（目标 12 秒，合格范围 9.6–12 秒）；`07` 为 `failed`，仅品牌语一镜就 3.25 秒超过 3 秒上限 |

另外三个用例也一并提交了，覆盖“改输入后动作是否变化”这类审核要点：

| 用例 | 复现命令 | 结果路径 | 实际状态 |
|---|---|---|---|
| 规则风险、不编造 | `python -m script_agent --input examples/inputs/08_rule_conflict.json` | `examples/real/08_rule_conflict/` | `completed`，脚本没写用户要求的“效率提升 80%”，改到 `risks` 里说明缺数据 |
| 改写查询 | `python -m script_agent --input examples/inputs/09_query_rewrite.json` | `examples/real/09_query_rewrite/` | `completed`，25.5 秒，仅引用 P01 |
| 改检索结果 | `python -m script_agent --input examples/inputs/10_materials_changed.json --data-dir examples/data_variants/no_subtitle` | `examples/real/10_materials_changed/` | `needs_input`，同一需求换个素材目录后从“能写”变成“无素材” |

**怎么读结果：** `result.json` 是机器可读的最终结果，`script.md` 是可直接编辑的脚本，`trace.md` 是给人看的逐步表格（步骤、动作、关键参数、返回摘要、下一步、决策依据），`trace.jsonl` 是同一份记录的逐行 JSON（含每轮 token 用量）。`summary.json` 是结果索引，`summary.md` 是同一份汇总的表格版。

## 改输入复测

以下命令在真实模型下运行，用来观察动作是否随输入变化；本文档不提供这些命令的新运行记录，已提交的记录在 `examples/real/` 里。

```bash
python -m script_agent --input examples/inputs/01_normal.json --target 15
python -m script_agent --input examples/inputs/01_normal.json --target 3
python -m script_agent --input examples/inputs/01_normal.json --data-dir examples/data_variants/no_subtitle
python -m script_agent --input examples/inputs/01_normal.json --fail-tool estimate_duration --fail-times 1
python -m script_agent --input examples/inputs/01_normal.json --fail-tool check_rules --fail-times -1
```

`--target` 覆盖输入里的目标时长，`--data-dir` 换素材目录，`--fail-tool` / `--fail-times` 注入工具故障（`-1` 表示一直失败）。除这五项外，`--topic`、`--audience`、`--platform`、`--style` 也能覆盖对应字段，`--max-steps` 改轮数上限（默认 10）。

## 输出字段

`result.json` 的字段：

| 字段 | 含义 |
|---|---|
| `status` | 任务状态，见下表 |
| `message` | 给人看的一句话结论；失败时含原因和未满足项 |
| `mode` | `real` 或 `mock`；`mock` 的 `script.md` 开头有 `[MOCK]` 标记 |
| `title` | 脚本标题；未完成时为 `null` |
| `shots` | 分镜列表，每项含 `id`、`visual`、`narration`、`claims`（`source_id` + 逐字 `quote`）、`duration_sec`、`source_ids`；未完成时为 `null` |
| `total_duration_sec` | 预计总时长，只取自 `estimate_duration` 的返回；未完成时为 `null` |
| `target_duration_sec` | 目标时长（用户输入，模型不能改） |
| `source_ids` | 全脚本引用的素材 ID 并集，升序 |
| `checks` | `duration` 与 `rules` 各自的最后一次判定：`pass`、`too_long`、`too_short`、`fail`、`error`、`not_run` |
| `risks` | 模型声明的风险，加上缺受众/平台/风格时自动补的假设说明 |
| `missing_info` | `needs_input` 时缺的信息类别 |
| `unverified_draft` | 未通过检查的最后一版草稿；`script.md` 里标注“未通过检查，不可直接使用” |
| `last_estimate` | 最近一次时长估算的原始返回，说明失败时用了什么依据 |
| `steps_used` | 实际发起的模型调用轮数 |
| `tool_calls_used` | 实际执行的工具调用次数（上限 20） |

四种状态：

| 状态 | 含义 |
|---|---|
| `completed` | 同一份脚本的时长和规则检查都通过，已提交；产物里有标题、分镜、总时长、来源 ID、风险 |
| `needs_input` | 缺主题、目标时长这类关键信息，或缺素材；模型调了 `ask_user`，`missing_info` 写明缺什么 |
| `failed` | 模型确认无法满足要求（`report_failure`），或模型调用本身失败；`message` 写明原因 |
| `incomplete` | 达到步数上限（10 轮）或工具调用上限（20 次）仍未结束；`message` 写明触发了哪个上限 |

## 已知限制

与 `docs/03-evaluation.md` 的“已知限制”一节相同：

1. 词表和数字校验拦不全语义上的夸大。词表只覆盖已知说法，换一种说法描述素材没有的能力（例如只引用了“支持字幕”，却写“说过的话都会出现在屏幕上，样式也能改”），检查不会报错。
2. 中文数字只校验带倍、成、折和“百分之”的写法。“十二种”这类写法查不出来，只有阿拉伯数字会被拦。
3. 旁白是否真实表达了 `claims` 引用的那一条事实，没有语义校验。引用逐字校验只保证 `quote` 是素材原文。
4. “第一次”这类正常表达会被“第一”误拦。`banned_terms` 是子串匹配，没有词边界。
5. 语速是固定估算：汉字每秒 4 个、每镜加 0.5 秒停顿，不是真实配音时长。
6. 真实模型每次输出不同，`examples/real/` 只代表当次运行。几批记录的动作序列都有差异。
7. 素材级授权：引用某条素材后，该素材的其它事实也被视为有据。例如引用 P05 的“基础版免费使用”后，写“会员价 18 元/月”不会被拦。
8. 某一轮模型没有调用工具时，这一轮没有 token 用量记录，`total_tokens` 会少算这一轮。
9. 严格贴着素材写，脚本可能信息量偏低。素材只有“支持字幕”一条时，旁白只能反复表达这一点。词表也可能误拦正常说法，比如“快速滑动”“简单说”，模型需要换一种写法。

## 实际用时与未完成部分

- 实际用时：约 9 小时，分两天。第一天（2026-11-02 01:00–09:11）完成核心链路、Trace 与模型客户端、CLI、10 个真实用例的前两批运行和评估文档；第二天（2026-11-03）做质量复查与第三批重跑、Web 工作台，以及娱乐向素材库的补充验证。不含评审准备和本次填写文档的时间。约 3 小时的题目建议时长没守住，主要差在第三批全量重跑（收紧规则后旧记录全部失效）和 Web 工作台这两块。
- 未完成部分：
  1. **Web 工作台和本批代码尚未提交到 git。** 工作区有 71 个改动文件未进版本库，其中 `src/script_agent/web/` 整个目录、`src/` 下 5 个文件的修改、`tests/test_web_*.py` 都还是未跟踪状态。文档已把 Web 工作台当交付物描述，但仓库里没有对应提交。
  2. **“纯剧情、零产品植入”的脚本无法生成。** `check_rules` 的首条规则是必须至少引用一条素材（`NO_SOURCE`），所以用户要求“不带产品的搞笑短剧”时，模型只能追问或硬插两句产品台词。题目只要求产品事实可追溯，没有要求必须植入，当前实现比题目更严。
  3. **真实 socket 上的 Web 访问只在单机上验证过。** `test_real_socket_roundtrip` 带 `skipif` 探针，环境不允许本机回环时会被静默跳过（之前记录的 316 passed / 1 skipped 就是这种情况）；本次允许回环，已实际执行并通过。界面是手动在浏览器点过的，没有自动化端到端。
  4. **素材库不足以支撑 30 秒有信息量的脚本。** 默认库 6 条素材、7 条事实，全部用上也只到 19.5 秒，模型只能靠重复或情绪铺垫凑时长。
  5. **语义层面的编造仍然拦不住。** 词表只覆盖已知说法，换一种说法就能绕过，详见 `docs/03-evaluation.md` 的已知限制第 1 条。
