# Trace

| 步骤 | 动作 | 关键参数 | 返回摘要 | 下一步 | 决策依据 |
|---:|---|---|---|---|---|
| 1 | search_materials | query=剪刀鱼 字幕功能；top_k=5 | 命中 1 条: P01 | search_materials | 需求关键信息齐全，先检索字幕功能素材 |
| 2 | search_materials | query=剪刀鱼 App 视频剪辑 字幕 功能；top_k=8 | 命中 1 条: P01 | search_materials | 仅得一条素材，换宽泛查询再补素材 |
| 3 | search_materials | query=字幕 自动识别 剪辑工具 新手；top_k=8 | 命中 1 条: P01 | estimate_duration | 两次结果相同，最后一次换查询确认素材上限 |
| 4 | estimate_duration | 标题=新手拍第一条视频，别有压力；分镜=7 | 总时长 34s，目标 30s，判定 too_long，超出 4s | check_rules | 素材仅“支持字幕”，据此写30秒新手向脚本 |
| 5 | check_rules | 标题=新手拍第一条视频，别有压力；分镜=7 | 错误 TOOL_UNAVAILABLE: 工具 check_rules 当前不可用，请稍后重试。 | estimate_duration | 素材仅一句事实，先查规则确认表述合规 |
| 6 | estimate_duration | 标题=新手拍第一条视频，别有压力；分镜=7 | 总时长 28.75s，目标 30s，判定 pass | check_rules | 返回 too_long 4秒，压缩各镜旁白 |
| 7 | check_rules | 标题=新手拍第一条视频，别有压力；分镜=7 | 错误 TOOL_UNAVAILABLE: 工具 check_rules 当前不可用，请稍后重试。 | report_failure | 重试上次不可用的 check_rules，校验压缩后脚本 |
| 8 | report_failure | reason=脚本已写好并压缩到 28.75 秒（30 秒目标，判定 pass），但品牌规则与素材来源检查工具 check_rule…；unmet_requirements=["脚本未经 check_rules 品牌规则与素材来源检查，不能提交"]；failed_tools=["check_rules"] | 已报告无法满足要求 | END:failed | check_rules 两次不可用且 retries_left=0，无法完成校验 |
