# Trace

| 步骤 | 动作 | 关键参数 | 返回摘要 | 下一步 | 决策依据 |
|---:|---|---|---|---|---|
| 1 | search_materials | query=剪刀鱼 字幕功能；top_k=8 | 命中 1 条: P01 | search_materials | 关键信息齐全，先检索剪刀鱼字幕素材 |
| 2 | search_materials | query=剪刀鱼 语音识别 自动生成字幕 文字样式；top_k=8 | 命中 1 条: P01 | search_materials | 仅1条且极简，换查询补充字幕相关事实 |
| 3 | search_materials | query=剪刀鱼 剪辑 视频 新手 教程；top_k=8 | 命中 0 条 | estimate_duration | 素材仅"支持字幕"一条，再试宽泛查询看有无其他可讲功能 |
| 4 | estimate_duration | 标题=新手第一条短视频，先学会加字幕；分镜=7 | 总时长 33.75s，目标 30s，判定 too_long，超出 3.75s | check_rules | 素材仅"支持字幕"，先按7镜写30秒稿并测时长 |
| 5 | check_rules | 标题=新手第一条短视频，先学会加字幕；分镜=7 | 错误 TOOL_UNAVAILABLE: 工具 check_rules 当前不可用，请稍后重试。 | estimate_duration | 同步做规则检查，确认仅一处产品事实且引用原文 |
| 6 | estimate_duration | 标题=新手第一条短视频，先学会加字幕；分镜=7 | 总时长 29s，目标 30s，判定 pass | check_rules | 33.75秒超时，压缩旁白后重估；同时重试规则检查 |
| 7 | check_rules | 标题=新手第一条短视频，先学会加字幕；分镜=7 | 错误 TOOL_UNAVAILABLE: 工具 check_rules 当前不可用，请稍后重试。 | report_failure | 上一轮规则工具不可用，此处重试完整脚本 |
| 8 | report_failure | reason=脚本已成型且时长检查通过（estimate_duration：总时长 29.0 秒，目标 30 秒，判定 pass），…；unmet_requirements=["check_rules 校验未通过（工具不可用，重试耗尽），脚本无法提交", "素材仅「支持字幕」一条事实，无法展…；failed_tools=["check_rules"] | 已报告无法满足要求 | END:failed | check_rules 两次返回不可用且 retries_left=0，无法完成规则校验 |
