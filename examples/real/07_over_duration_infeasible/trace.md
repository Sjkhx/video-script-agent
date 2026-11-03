# Trace

| 步骤 | 动作 | 关键参数 | 返回摘要 | 下一步 | 决策依据 |
|---:|---|---|---|---|---|
| 1 | search_materials | query=剪刀鱼 字幕功能；top_k=5 | 命中 1 条: P01 | estimate_duration | 需求齐全，先检索剪刀鱼字幕功能素材 |
| 2 | estimate_duration | 标题=剪刀鱼的字幕功能｜新手一句话版；分镜=1 | 总时长 3.5s，目标 3s，判定 too_long，超出 0.5s | check_rules | 素材仅一条事实"支持字幕"，据此写短脚本并测时长 |
| 3 | check_rules | 标题=剪刀鱼的字幕功能｜新手一句话版；分镜=1 | 判定 fail: MISSING_CLOSING_SLOGAN | estimate_duration | 同版脚本送规则检查，确认无引申 |
| 4 | estimate_duration | 标题=剪刀鱼的字幕功能｜新手一句话版；分镜=1 | 总时长 5s，目标 3s，判定 too_long，超出 2s | check_rules | 规则要求结尾品牌语，加上后需重新测时长 |
| 5 | check_rules | 标题=剪刀鱼的字幕功能｜新手一句话版；分镜=1 | 判定 pass | estimate_duration | 加上品牌语后同步送规则检查 |
| 6 | estimate_duration | 标题=剪刀鱼的字幕功能｜新手一句话版；分镜=1 | 总时长 4.25s，目标 3s，判定 too_long，超出 1.25s | estimate_duration | 测仅保留品牌语的最短版本，看是否仍超3秒 |
| 7 | estimate_duration | 标题=剪刀鱼的字幕功能｜极限时长测试；分镜=1 | 总时长 3.25s，目标 3s，判定 too_long，超出 0.25s | report_failure | 测纯品牌语的极限版本，确认3秒硬限制能否达成 |
| 8 | report_failure | reason=规则要求脚本最后一个分镜旁白必须以品牌语「剪刀鱼，剪出属于你的故事」结尾，而仅这一句单独成镜经 estimate_du…；unmet_requirements=["目标时长 3.0 秒：最短可行脚本（只含品牌语一镜）实测 3.25 秒，超出 0.25 秒", "无法在该时长内同…；failed_tools=[] | 已报告无法满足要求 | END:failed | 仅品牌语一镜已3.25秒，超3秒上限，无法同时满足规则与时长 |
