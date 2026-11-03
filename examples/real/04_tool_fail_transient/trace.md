# Trace

| 步骤 | 动作 | 关键参数 | 返回摘要 | 下一步 | 决策依据 |
|---:|---|---|---|---|---|
| 1 | search_materials | query=剪刀鱼 字幕功能；top_k=5 | 命中 1 条: P01 | estimate_duration | 主题是剪刀鱼字幕功能，先检索对应素材 |
| 2 | estimate_duration | 标题=剪刀鱼的字幕功能｜新手30秒版；分镜=7 | 错误 TOOL_UNAVAILABLE: 工具 estimate_duration 当前不可用，请稍后重试。 | check_rules | 按素材仅“支持字幕”写好初稿，先看时长判定 |
| 3 | check_rules | 标题=剪刀鱼的字幕功能｜新手30秒版；分镜=7 | 判定 fail: UNSUPPORTED_NUMBER, UNCITED_FEATURE, MISSING_CLOSING_SLOGAN | check_rules | 同步跑规则检查，确认事实引用与表述合规 |
| 4 | check_rules | 标题=剪刀鱼的字幕功能｜新手友好版；分镜=7 | 错误 INVALID_ARGS: 参数校验失败：shots.6.id: Field required | estimate_duration | 按 violations 改标题、去掉未引用提及并补品牌语 |
| 5 | estimate_duration | 标题=剪刀鱼的字幕功能｜新手友好版；分镜=7 | 错误 INVALID_ARGS: 参数校验失败：shots.6.id: Field required | check_rules | 规则检查已改稿，同时重试估算时长 |
| 6 | check_rules | 标题=剪刀鱼的字幕功能｜新手友好版；分镜=7 | 判定 fail: UNSUPPORTED_TERM | estimate_duration | 补上分镜 7 的 id 后重跑规则检查 |
| 7 | estimate_duration | 标题=剪刀鱼的字幕功能｜新手友好版；分镜=7 | 总时长 31.75s，目标 30s，判定 too_long，超出 1.75s | check_rules | 补上分镜 7 的 id 后重跑时长估算 |
| 8 | check_rules | 标题=剪刀鱼的字幕功能｜新手友好版；分镜=7 | 判定 pass | estimate_duration | 删除“轻松”并压缩旁白后重跑规则检查 |
| 9 | estimate_duration | 标题=剪刀鱼的字幕功能｜新手友好版；分镜=7 | 总时长 25.5s，目标 30s，判定 pass | submit_script | 压缩旁白以消除 1.75 秒超时 |
| 10 | submit_script | 标题=剪刀鱼的字幕功能｜新手友好版；分镜=7 | 提交通过 | END:completed | check_rules 通过且时长 25.5 秒达标，提交同一份脚本 |
