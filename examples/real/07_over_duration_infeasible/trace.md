# Trace

| 步骤 | 动作 | 关键参数 | 返回摘要 | 下一步 | 决策依据 |
|---:|---|---|---|---|---|
| 1 | search_materials | query=剪刀鱼 字幕功能；top_k=6 | 命中 1 条: P01 | estimate_duration | 需求关键信息齐全，先检索剪刀鱼字幕功能素材 |
| 2 | estimate_duration | 标题=剪刀鱼字幕功能｜3秒口播；分镜=2 | 总时长 5s，目标 3s，判定 too_long，超出 2s | check_rules | 素材仅一条“支持字幕”，先按2镜短旁白估算3秒时长 |
| 3 | check_rules | 标题=剪刀鱼字幕功能｜3秒口播；分镜=2 | 判定 fail: UNSUPPORTED_NUMBER, UNCITED_FEATURE, MISSING_CLOSING_SLOGAN | estimate_duration | 同时检查规则，确认事实引用只来自P01 |
| 4 | estimate_duration | 标题=剪刀鱼字幕功能｜新手快看；分镜=1 | 总时长 3.25s，目标 3s，判定 too_long，超出 0.25s | check_rules | 试算仅含品牌语的最短版本，看能否压进3秒上限 |
| 5 | check_rules | 标题=剪刀鱼字幕功能｜新手快看；分镜=1 | 判定 pass | report_failure | 同步检查单镜版本是否满足品牌语与引用规则 |
| 6 | report_failure | reason=目标时长3.0秒（工具允许上限3.0秒）与品牌规则冲突：check_rules 要求最后一个分镜旁白必须以品牌语「剪刀…；unmet_requirements=["目标时长3.0秒内讲清剪刀鱼字幕功能：仅品牌语一句即需3.25秒，超时长上限", "脚本需包含品牌语「剪刀鱼，剪出…；failed_tools=["estimate_duration"] | 已报告无法满足要求 | END:failed | 仅品牌语一句已达3.25秒，超3秒硬上限，无法满足 |
