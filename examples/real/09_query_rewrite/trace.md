# Trace

| 步骤 | 动作 | 关键参数 | 返回摘要 | 下一步 | 决策依据 |
|---:|---|---|---|---|---|
| 1 | search_materials | query=静音 字幕 短视频 看懂内容；top_k=6 | 命中 1 条: P01 | search_materials | 关键信息齐全，先检索静音观看/字幕相关素材 |
| 2 | search_materials | query=无声观看 字幕 画面表达 短视频创作工具；top_k=6 | 命中 1 条: P01 | search_materials | 仅命中一条极简素材，换查询再试 |
| 3 | search_materials | query=字幕功能 产品；top_k=10 | 命中 1 条: P01 | estimate_duration | 仍只有 P01，最后换角度再试一次 |
| 4 | estimate_duration | 标题=静音也能看懂：新手3步自查法；分镜=8 | 总时长 34.25s，目标 30s，判定 too_long，超出 4.25s | check_rules | 素材仅P01支持字幕，写成方法类脚本并同步查时长与规则 |
| 5 | check_rules | 标题=静音也能看懂：新手3步自查法；分镜=8 | 判定 fail: UNSUPPORTED_NUMBER, BANNED_TERM, MISSING_CLOSING_SLOGAN | estimate_duration | 检查脚本是否越界引申产品能力 |
| 6 | estimate_duration | 标题=静音也看得懂：新手自查法；分镜=8 | 总时长 25.5s，目标 30s，判定 pass | check_rules | 上轮超长4.25秒且规则失败，已压缩旁白、去序数、补品牌语 |
| 7 | check_rules | 标题=静音也看得懂：新手自查法；分镜=8 | 判定 pass | submit_script | 复核标题无数字、无禁用序数、结尾带品牌语 |
| 8 | submit_script | 标题=静音也看得懂：新手自查法；分镜=8 | 提交通过 | END:completed | 时长25.5秒在允许区间且规则通过，提交同一份脚本 |
