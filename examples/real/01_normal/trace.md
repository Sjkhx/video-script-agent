# Trace

| 步骤 | 动作 | 关键参数 | 返回摘要 | 下一步 | 决策依据 |
|---:|---|---|---|---|---|
| 1 | search_materials | query=剪刀鱼 字幕功能；top_k=8 | 命中 1 条: P01 | search_materials | 主题为剪刀鱼字幕功能，先检索素材 |
| 2 | search_materials | query=剪刀鱼 自动识别 语音转字幕 剪辑；top_k=8 | 命中 1 条: P01 | search_materials | 只返回1条极简素材，换查询再试 |
| 3 | search_materials | query=剪刀鱼 App 功能 介绍；top_k=8 | 命中 0 条 | estimate_duration | 仍只有一条，第三次换查询确认素材上限 |
| 4 | estimate_duration | 标题=剪刀鱼的字幕功能｜新手 30 秒速览；分镜=6 | 总时长 35.75s，目标 30s，判定 too_long，超出 5.75s | check_rules | 素材仅有“支持字幕”，先按6镜写30秒脚本并核时长 |
| 5 | check_rules | 标题=剪刀鱼的字幕功能｜新手 30 秒速览；分镜=6 | 判定 fail: UNSUPPORTED_NUMBER, UNCITED_FEATURE, MISSING_CLOSING_SLOGAN | estimate_duration | 同步检查该版脚本是否符合品牌与素材来源规则 |
| 6 | estimate_duration | 标题=剪刀鱼的字幕功能｜新手速览；分镜=6 | 总时长 26.75s，目标 30s，判定 pass | check_rules | 初版35.75s偏长，压缩旁白并补结尾品牌语后重估 |
| 7 | check_rules | 标题=剪刀鱼的字幕功能｜新手速览；分镜=6 | 判定 pass | submit_script | 按violations补P01引用、删标题数字、改结尾品牌语 |
| 8 | submit_script | 标题=剪刀鱼的字幕功能｜新手速览；分镜=6 | 提交通过 | END:completed | 时长26.75s在窗口内且规则通过，提交同版脚本 |
