# Trace

| 步骤 | 动作 | 关键参数 | 返回摘要 | 下一步 | 决策依据 |
|---:|---|---|---|---|---|
| 1 | search_materials | query=剪刀鱼 字幕功能；top_k=8 | 命中 1 条: P01 | search_materials | 主题是剪刀鱼字幕功能，先检索相关素材 |
| 2 | search_materials | query=剪刀鱼 视频剪辑 自动识别语音生成字幕；top_k=8 | 命中 1 条: P01 | search_materials | 仅命中1条极简素材，换关键词补充检索 |
| 3 | search_materials | query=剪刀鱼 剪辑软件 功能介绍 上手；top_k=10 | 命中 0 条 | estimate_duration | 第二次仍只有P01，最后换查询再试一次 |
| 4 | estimate_duration | 标题=新手剪视频别忽略字幕｜剪刀鱼字幕功能；分镜=6 | 错误 TOOL_UNAVAILABLE: 工具 estimate_duration 当前不可用，请稍后重试。 | check_rules | 素材仅P01，先按现有事实排6镜估时长 |
| 5 | check_rules | 标题=新手剪视频别忽略字幕｜剪刀鱼字幕功能；分镜=6 | 判定 fail: UNCITED_FEATURE, MISSING_CLOSING_SLOGAN | search_materials | 与估时长同轮检查规则合规性 |
| 6 | search_materials | query=剪刀鱼 竖屏 比例；top_k=5 | 命中 1 条: P02 | search_materials | 规则提示P02含“竖屏”，需检索确认其事实 |
| 7 | search_materials | query=剪刀鱼 字幕 竖屏 抖音；top_k=10 | 命中 2 条: P01, P02 | estimate_duration | 估计时长工具不可用，先补齐素材再重试 |
| 8 | estimate_duration | 标题=新手剪视频，别省掉字幕这一步｜剪刀鱼；分镜=6 | 总时长 32.5s，目标 30s，判定 too_long，超出 2.5s | check_rules | 已修正字幕引用与结尾品牌语，重估时长 |
| 9 | check_rules | 标题=新手剪视频，别省掉字幕这一步｜剪刀鱼；分镜=6 | 判定 fail: UNSUPPORTED_TERM | estimate_duration | 同步对修正后脚本做规则检查 |
| 10 | estimate_duration | 标题=新手剪视频，别省掉字幕这一步｜剪刀鱼；分镜=6 | 总时长 26s，目标 30s，判定 pass | check_rules | 上版32.5秒超长且有未支持词，压缩旁白并删“同步” |
| 11 | check_rules | 标题=新手剪视频，别省掉字幕这一步｜剪刀鱼；分镜=6 | 判定 pass | submit_script | 同步重查规则：已删“同步”一词 |
| 12 | submit_script | 标题=新手剪视频，别省掉字幕这一步｜剪刀鱼；分镜=6 | 提交通过 | END:completed | 时长与规则均pass，提交同一份脚本 |
