# Trace

| 步骤 | 动作 | 关键参数 | 返回摘要 | 下一步 | 决策依据 |
|---:|---|---|---|---|---|
| 1 | search_materials | query=剪刀鱼 字幕功能；top_k=5 | 命中 1 条: P01 | search_materials | 需求完整，先检索剪刀鱼字幕相关素材 |
| 2 | search_materials | query=剪刀鱼 自动识别 语音转字幕 剪辑工具；top_k=10 | 命中 1 条: P01 | search_materials | 仅得1条极简素材，换查询补充字幕细节 |
| 3 | search_materials | query=剪刀鱼 视频剪辑 功能；top_k=10 | 命中 0 条 | estimate_duration | 同时检索产品整体功能素材 |
| 4 | estimate_duration | 标题=剪刀鱼字幕功能｜新手第一次加字幕（30秒）；分镜=6 | 总时长 40.25s，目标 30s，判定 too_long，超出 10.25s | check_rules | 素材仅1条事实，脚本已按此写，先测时长 |
| 5 | check_rules | 标题=剪刀鱼字幕功能｜新手第一次加字幕（30秒）；分镜=6 | 判定 fail: TITLE_TOO_LONG, BANNED_TERM, UNSUPPORTED_NUMBER, UNCITED_FEATURE, MISSING_CLOSING_SLOGAN | search_materials | 同一份脚本同时做规则检查 |
| 6 | search_materials | query=竖屏 画幅 导出；top_k=10 | 命中 2 条: P02, P03 | estimate_duration | 规则提示P02「竖屏」，检索获取其facts以便正确引用 |
| 7 | estimate_duration | 标题=剪刀鱼字幕功能｜新手口播加字幕；分镜=6 | 总时长 25.5s，目标 30s，判定 pass | check_rules | 上版超时10秒且多条违规，按violations重写并压缩 |
| 8 | check_rules | 标题=剪刀鱼字幕功能｜新手口播加字幕；分镜=6 | 判定 fail: UNCITED_FEATURE | estimate_duration | 同一份重写脚本同时做规则检查 |
| 9 | estimate_duration | 标题=剪刀鱼字幕功能｜新手口播加字幕；分镜=6 | 总时长 25.5s，目标 30s，判定 pass | check_rules | 仅剩分镜6未引用P01，补claims后复检 |
| 10 | check_rules | 标题=剪刀鱼字幕功能｜新手口播加字幕；分镜=6 | 判定 pass | submit_script | 复检分镜6补引用后是否合规 |
| 11 | submit_script | 标题=剪刀鱼字幕功能｜新手口播加字幕；分镜=6 | 提交通过 | END:completed | 时长25.5s合规、规则pass，提交同一份脚本 |
