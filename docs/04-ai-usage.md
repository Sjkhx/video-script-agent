# 04 AI 使用说明

本文如实记录 AI 在项目里承担了什么、人工环节落在哪里。最后四节留空，由本人填写。

## 方案设计

施工方案由 Claude（Claude Code）产出，保存在仓库内：

- `docs/superpowers/plans/2026-11-02-video-script-agent.md`

方案在本仓库里同时充当规格说明（Spec）：附录 A 是题目原文，正文按 Task 1–11 拆成可执行步骤，每个 Task 都写了要改的文件、接口签名、测试代码、验证命令和提交信息。执行时以它为准，遇到它没定义又会影响验收的问题先停下来确认，不自行改需求。

方案阶段留下的痕迹：仓库根目录的 `.claude/settings.local.json`（Claude Code 的本地权限配置），以及方案文件本身的形态（Task 清单 + checkbox + 逐步命令）。

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

结果：`239 passed`。`examples/test-results.txt` 保存的就是这条命令的完整输出（`239 passed in 2.45s`），其中 `-rs` 版本没有 skip 报告，与“0 skipped”一致。

**2. 真实运行结果的一致性校验**

```bash
.venv/Scripts/python.exe -m pytest tests/test_examples_consistency.py -q
```

结果：`45 passed`。这 45 条断言读的是已提交的 `examples/real/<case>/result.json` 与 `trace.jsonl`，会用 `data/` 重算时长与规则，逐镜核对，不需要重新调用模型。

**3. 真实模型批量运行**

```bash
.venv/Scripts/python.exe scripts/run_examples.py
```

按 `examples/cases.json` 顺序跑 10 个用例，写 `examples/real/<case>/` 下的四个产物，并重建 `examples/real/summary.json` 和 `summary.md`。共跑了两批：

- 第一批：`git log` 里的 `bfac6f7 chore: record real model run batch 1`，首个用例 2026-11-02T10:48:13Z 开始，末个用例 10:52:05Z 开始。
- 第二批：`ae98952 chore: record second real model run batch and test results`，首个用例 2026-11-02T10:54:37Z 开始，末个用例 11:04:58Z 开始；这是当前 `examples/real/` 的内容。

（时间取自各用例 `trace.jsonl` 首行 `run_start.started_at`。）

两批都是 10/10 达到预期状态。两批之间没有改代码、测试或 Prompt（`git diff bfac6f7 ae98952 -- src data tests scripts examples/cases.json examples/inputs` 无输出），第二批复跑只为看稳定性。

**4. 离线跑通流程**

```bash
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m script_agent --input examples/inputs/01_normal.json --mock-script examples/mock_scripts/06_over_duration_fixed.json
```

第二条 `--mock-script` 换掉模型，其余代码路径不变，产出 `completed`、30 秒、4 分镜，`script.md` 首行是 `[MOCK] 本次模型决策来自预设脚本，只验证流程，不证明真实模型效果。`

**5. 安装可复现性**

在临时目录另建一个干净虚拟环境，按 `requirements.txt` 安装后跑测试，结果同样是 `239 passed`；用该环境的解释器执行上面的离线命令，同样是退出码 0、`script.md` 带 `[MOCK]` 首行。

**6. 配置与安全**

```bash
git ls-files | grep -E "\.env$|runs/"   # 无输出
git grep -n "sk-"                        # 只有源码里的脱敏正则、文档说明和测试用的假值
```

缺配置时的行为也验证过：`LLM_API_KEY` 与 `LLM_MODEL` 为空时，命令返回退出码 2、打印缺哪两项、不创建产物目录，也不会退回 Mock。

## 本人审查了什么

【需本人填写】

## 本人修改了什么

【需本人填写】

## 本人独立验证了什么

【需本人填写】

## 哪些部分本人能完整解释

【需本人填写】
