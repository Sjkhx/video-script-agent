# Trace

| 步骤 | 动作 | 关键参数 | 返回摘要 | 下一步 | 决策依据 |
|---:|---|---|---|---|---|
| 1 | search_materials | query=短视频 静音 字幕 内容理解 剪辑；top_k=5 | 命中 1 条: P01 | search_materials | 主题指向静音观看的短视频创作方法，先检索相关素材 |
| 2 | search_materials | query=剪辑工具 自动字幕 短视频发布；top_k=5 | 命中 1 条: P01 | search_materials | 上次仅1条素材且缺产品名，换更贴近产品的查询再试 |
| 3 | search_materials | query=静音观看 竖屏 短视频 产品功能；top_k=8 | 命中 1 条: P02 | estimate_duration | 两次结果仅P01且无产品名，最后再试一次更宽泛查询 |
| 4 | estimate_duration | 标题=静音也能看懂：新手短视频三步法；分镜=6 | 总时长 32.5s，目标 30s，判定 too_long，超出 2.5s | check_rules | 素材仅两条字幕与模板事实，按静音可读设计6镜30秒 |
| 5 | check_rules | 标题=静音也能看懂：新手短视频三步法；分镜=6 | 判定 fail: UNCITED_FEATURE, UNSUPPORTED_NUMBER, BANNED_TERM, MISSING_CLOSING_SLOGAN | estimate_duration | 同步做规则检查与素材引用核对 |
| 6 | estimate_duration | 标题=静音也能看懂：新手短视频三步法；分镜=6 | 总时长 31.75s，目标 30s，判定 too_long，超出 1.75s | check_rules | 修复引用、数字、禁用词与品牌语，并压到30秒内 |
| 7 | check_rules | 标题=静音也能看懂：新手短视频三步法；分镜=6 | 判定 fail: UNCITED_FEATURE | estimate_duration | 按violations逐条修正后重检 |
| 8 | estimate_duration | 标题=静音也能看懂：新手短视频三步法；分镜=6 | 总时长 29.25s，目标 30s，判定 pass | check_rules | 再压旁白至30秒内，并去掉镜6画面里的“字幕”标签 |
| 9 | check_rules | 标题=静音也能看懂：新手短视频三步法；分镜=6 | 判定 pass | submit_script | 删除镜6画面中的字幕标签后再检 |
| 10 | submit_script | 标题=静音也能看懂：新手短视频三步法；分镜=6 | 提交通过 | END:completed | 时长29.25秒通过，规则检查无违规，提交同一份脚本 |
