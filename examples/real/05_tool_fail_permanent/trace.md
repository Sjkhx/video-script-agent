# Trace

| 步骤 | 动作 | 关键参数 | 返回摘要 | 下一步 | 决策依据 |
|---:|---|---|---|---|---|
| 1 | search_materials | query=剪刀鱼 字幕功能；top_k=8 | 命中 1 条: P01 | search_materials | 主题与时长齐全，先检索剪刀鱼字幕功能素材 |
| 2 | search_materials | query=剪刀鱼 自动识别语音 生成字幕 编辑；top_k=8 | 命中 1 条: P01 | search_materials | 仅一条素材且信息极少，换查询补充字幕能力细节 |
| 3 | search_materials | query=剪刀鱼 剪辑 App 功能介绍；top_k=8 | 命中 0 条 | estimate_duration | 前两次仅P01，最后一次换关键词确认素材边界 |
| 4 | estimate_duration | 标题=剪刀鱼字幕功能｜新手30秒上手；分镜=5 | 总时长 31.5s，目标 30s，判定 too_long，超出 1.5s | check_rules | 已有素材P01，写出30秒新手向口播脚本待双检查 |
| 5 | check_rules | 标题=剪刀鱼字幕功能｜新手30秒上手；分镜=5 | 错误 TOOL_UNAVAILABLE: 工具 check_rules 当前不可用，请稍后重试。 | estimate_duration | 同一份脚本提交规则检查，确认claim均出自P01 |
| 6 | estimate_duration | 标题=剪刀鱼字幕功能｜新手30秒上手；分镜=5 | 总时长 29.75s，目标 30s，判定 pass | check_rules | 31.5秒超目标1.5秒，压缩旁白后重估 |
| 7 | check_rules | 标题=剪刀鱼字幕功能｜新手30秒上手；分镜=5 | 错误 TOOL_UNAVAILABLE: 工具 check_rules 当前不可用，请稍后重试。 | report_failure | check_rules上次不可用仅剩1次重试，立即重试 |
| 8 | report_failure | reason=脚本已完成：时长检查通过（总时长 29.75 秒，目标 30 秒，verdict=pass），产品事实仅引用素材 P0…；unmet_requirements=["品牌规则与素材来源检查未完成（check_rules 工具不可用）", "脚本未通过 submit_script …；failed_tools=["check_rules"] | 已报告无法满足要求 | END:failed | 时长已pass，但check_rules重试耗尽仍不可用，无法提交 |
