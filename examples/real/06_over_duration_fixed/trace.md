# Trace

| 步骤 | 动作 | 关键参数 | 返回摘要 | 下一步 | 决策依据 |
|---:|---|---|---|---|---|
| 1 | search_materials | query=剪刀鱼 字幕 模板 配音；top_k=8 | 命中 3 条: P01, P02, P04 | estimate_duration | 主题含三个卖点，需先检索剪刀鱼素材核实事实 |
| 2 | estimate_duration | 标题=新手 12 秒看懂剪刀鱼：字幕、模板、配音；分镜=4 | 总时长 14s，目标 12s，判定 too_long，超出 2s | check_rules | 素材已拿到三个卖点事实，先估算初稿时长 |
| 3 | check_rules | 标题=新手 12 秒看懂剪刀鱼：字幕、模板、配音；分镜=4 | 判定 fail: TITLE_TOO_LONG, UNCITED_FEATURE, BANNED_TERM, MISSING_CLOSING_SLOGAN | estimate_duration | 同时检查规则，确认引用与品牌合规 |
| 4 | estimate_duration | 标题=剪刀鱼三点：字幕模板配音；分镜=3 | 总时长 11s，目标 12s，判定 pass | check_rules | 超时2秒且规则有4处问题，压缩旁白并补品牌语 |
| 5 | check_rules | 标题=剪刀鱼三点：字幕模板配音；分镜=3 | 判定 pass | submit_script | 同步复查标题长度、禁用词与结尾品牌语 |
| 6 | submit_script | 标题=剪刀鱼三点：字幕模板配音；分镜=3 | 提交通过 | END:completed | 时长11秒达标且规则通过，提交同一份脚本 |
