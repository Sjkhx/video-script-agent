# Trace

| 步骤 | 动作 | 关键参数 | 返回摘要 | 下一步 | 决策依据 |
|---:|---|---|---|---|---|
| 1 | search_materials | query=短视频 静音观看 字幕 明确信息 拍摄技巧；top_k=8 | 命中 1 条: P01 | search_materials | 主题是短视频创作技巧，先检索是否有对应产品素材 |
| 2 | search_materials | query=短视频剪辑App 自动字幕 新手 教程；top_k=8 | 命中 1 条: P01 | search_materials | 并行检索剪辑类产品素材，确认可用事实 |
| 3 | search_materials | query=剪辑工具 字幕样式 大字标题 功能；top_k=8 | 命中 1 条: P01 | estimate_duration | 仅1条素材，再换查询看是否能补充更多可用事实 |
| 4 | estimate_duration | 标题=静音刷也能看懂：新手短视频信息表达3招；分镜=8 | 总时长 39.25s，目标 30s，判定 too_long，超出 9.25s | check_rules | 素材仅P01「支持字幕」，按此写30秒口语脚本并测时长 |
| 5 | check_rules | 标题=静音刷也能看懂：新手短视频信息表达3招；分镜=8 | 判定 fail: UNSUPPORTED_NUMBER, UNCITED_FEATURE, BANNED_TERM, MISSING_CLOSING_SLOGAN | estimate_duration | 与测时长同步校验规则，确认字幕表述有素材支撑 |
| 6 | estimate_duration | 标题=静音刷也能看懂：新手短视频信息表达；分镜=7 | 总时长 29.5s，目标 30s，判定 pass | check_rules | 上版39.25秒超长且规则fail，已压缩并修正违例 |
| 7 | check_rules | 标题=静音刷也能看懂：新手短视频信息表达；分镜=7 | 判定 pass | submit_script | 同步校验：已去数字、去禁用词、补尾部品牌语 |
| 8 | submit_script | 标题=静音刷也能看懂：新手短视频信息表达；分镜=7 | 提交通过 | END:completed | 时长29.5秒通过、规则零违例，提交同一份脚本 |
