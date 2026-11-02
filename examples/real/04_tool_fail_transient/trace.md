# Trace

| 步骤 | 动作 | 关键参数 | 返回摘要 | 下一步 | 决策依据 |
|---:|---|---|---|---|---|
| 1 | search_materials | query=剪刀鱼 字幕功能；top_k=8 | 命中 1 条: P01 | search_materials | 主题是剪刀鱼字幕功能，先检索产品素材 |
| 2 | search_materials | query=剪刀鱼 自动识别语音 生成字幕 剪辑；top_k=8 | 命中 1 条: P01 | search_materials | 仅得一条极简素材，换查询词补充素材 |
| 3 | search_materials | query=剪刀鱼 视频编辑 功能 新手；top_k=10 | 命中 0 条 | estimate_duration | 仍只有一条素材，最后一次换词检索 |
| 4 | estimate_duration | 标题=剪刀鱼字幕功能｜新手30秒上手；分镜=6 | 错误 TOOL_UNAVAILABLE: 工具 estimate_duration 当前不可用，请稍后重试。 | check_rules | 脚本已成形，按规则同时做时长与规则检查 |
| 5 | check_rules | 标题=剪刀鱼字幕功能｜新手30秒上手；分镜=6 | 判定 fail: UNSUPPORTED_NUMBER, UNCITED_FEATURE, MISSING_CLOSING_SLOGAN | estimate_duration | 核对claims是否逐字来自P01，并确认脚本无未授权功能描述 |
| 6 | estimate_duration | 标题=剪刀鱼字幕功能｜新手轻松上手；分镜=6 | 总时长 37s，目标 30s，判定 too_long，超出 7s | check_rules | 规则检查已指出问题，须对修改后脚本重跑时长估算 |
| 7 | check_rules | 标题=剪刀鱼字幕功能｜新手轻松上手；分镜=6 | 判定 pass | estimate_duration | 按violations修正后，重新核对修改稿 |
| 8 | estimate_duration | 标题=剪刀鱼字幕功能｜新手轻松上手；分镜=5 | 总时长 25s，目标 30s，判定 pass | check_rules | 上轮too_long超7秒，压缩旁白并合并分镜后重估 |
| 9 | check_rules | 标题=剪刀鱼字幕功能｜新手轻松上手；分镜=5 | 判定 pass | submit_script | 压缩后核对引用与结尾品牌语是否仍合规 |
| 10 | submit_script | 标题=剪刀鱼字幕功能｜新手轻松上手；分镜=5 | 提交通过 | END:completed | 时长与规则双项pass，提交同一份脚本 |
