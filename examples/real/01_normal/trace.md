# Trace

| 步骤 | 动作 | 关键参数 | 返回摘要 | 下一步 | 决策依据 |
|---:|---|---|---|---|---|
| 1 | search_materials | query=剪刀鱼 字幕功能；top_k=8 | 命中 1 条: P01 | search_materials | 主题是字幕功能，先检索产品素材 |
| 2 | search_materials | query=剪刀鱼 视频剪辑 功能 卖点；top_k=8 | 命中 0 条 | search_materials | 仅返回一条事实，换查询再补充素材 |
| 3 | search_materials | query=剪刀鱼 新手 字幕 教程；top_k=8 | 命中 1 条: P01 | estimate_duration | 第二次检索无结果，还有一次换词机会 |
| 4 | estimate_duration | 标题=新手剪片别漏字幕，剪刀鱼这一点先记住；分镜=5 | 总时长 26.25s，目标 30s，判定 pass | check_rules | 素材仅有「支持字幕」，先估时长看是否需调整 |
| 5 | check_rules | 标题=新手剪片别漏字幕，剪刀鱼这一点先记住；分镜=5 | 判定 fail: BANNED_TERM, UNCITED_FEATURE, MISSING_CLOSING_SLOGAN | estimate_duration | 同一稿同时做规则检查 |
| 6 | estimate_duration | 标题=新手剪片别漏字幕，剪刀鱼这一点先记住；分镜=5 | 总时长 26s，目标 30s，判定 pass | check_rules | 按 violations 删「第一」、补品牌语后重估时长 |
| 7 | check_rules | 标题=新手剪片别漏字幕，剪刀鱼这一点先记住；分镜=5 | 判定 fail: UNSUPPORTED_TERM | estimate_duration | 同步复查规则是否已修复 |
| 8 | estimate_duration | 标题=新手剪片别漏字幕，剪刀鱼这一点先记住；分镜=5 | 总时长 26s，目标 30s，判定 pass | check_rules | 删去未支持的「上手」后重估时长 |
| 9 | check_rules | 标题=新手剪片别漏字幕，剪刀鱼这一点先记住；分镜=5 | 判定 pass | submit_script | 复查「上手」已删除 |
| 10 | submit_script | 标题=新手剪片别漏字幕，剪刀鱼这一点先记住；分镜=5 | 提交通过 | END:completed | 时长与规则均 pass，提交同一稿 |
