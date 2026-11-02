# Trace

| 步骤 | 动作 | 关键参数 | 返回摘要 | 下一步 | 决策依据 |
|---:|---|---|---|---|---|
| 1 | search_materials | query=剪刀鱼 字幕功能；top_k=8 | 命中 1 条: P01 | estimate_duration | 需求已含主题与3秒时长，先检索剪刀鱼字幕相关素材 |
| 2 | estimate_duration | 标题=剪刀鱼字幕功能｜3秒口播；分镜=2 | 总时长 4.25s，目标 3s，判定 too_long，超出 1.25s | check_rules | 素材仅1条事实，写极简2镜先测3秒时长 |
| 3 | check_rules | 标题=剪刀鱼字幕功能｜3秒口播；分镜=2 | 判定 fail: UNSUPPORTED_NUMBER, UNCITED_FEATURE, MISSING_CLOSING_SLOGAN | estimate_duration | 同步检查素材引用是否合规 |
| 4 | estimate_duration | 标题=剪刀鱼字幕功能口播；分镜=1 | 总时长 3.25s，目标 3s，判定 too_long，超出 0.25s | estimate_duration | 规则强制片尾品牌语，先测仅含品牌语的极限时长 |
| 5 | estimate_duration | 标题=剪刀鱼字幕功能口播；分镜=1 | 总时长 5s，目标 3s，判定 too_long，超出 2s | report_failure | 再测含主题+品牌语的最小合规版本时长 |
| 6 | report_failure | reason=素材 P01 仅提供「支持字幕」一条事实，内容本身可写；但品牌规则要求最后一个分镜旁白必须以品牌语「剪刀鱼，剪出属于你…；unmet_requirements=["目标时长 3.0 秒无法满足：合规片尾品牌语单独即 3.25 秒（溢出 0.25 秒）", "在 3 秒内无法同时…；failed_tools=[] | 已报告无法满足要求 | END:failed | 仅含强制品牌语已3.25秒超3秒上限，无法满足时长 |
