# Trace

| 步骤 | 动作 | 关键参数 | 返回摘要 | 下一步 | 决策依据 |
|---:|---|---|---|---|---|
| 1 | search_materials | query=静音刷 短视频 字幕 可看懂 技巧；top_k=8 | 命中 1 条: P01 | search_materials | 需求主题是静音也能看懂，先检索是否有可用素材 |
| 2 | search_materials | query=字幕 封面 标题 短视频工具 功能；top_k=8 | 命中 1 条: P01 | search_materials | 仅命中1条素材，换查询再试以获取更多事实 |
| 3 | search_materials | query=剪辑 文本 识别 自动 音频 转写；top_k=8 | 命中 0 条 | estimate_duration | 两次均只命中P01，再换查询最后一次尝试 |
| 4 | estimate_duration | 标题=静音刷也能看懂：新手必学的5个画面表达法；分镜=7 | 总时长 30.75s，目标 30s，判定 too_long，超出 0.75s | check_rules | 素材仅P01「支持字幕」，据此写30秒静音可看懂的脚本并先估时长 |
| 5 | check_rules | 标题=静音刷也能看懂：新手必学的5个画面表达法；分镜=7 | 判定 fail: UNSUPPORTED_NUMBER, UNCITED_FEATURE, MISSING_CLOSING_SLOGAN | estimate_duration | 脚本初稿完成，同步做品牌规则与素材来源检查 |
| 6 | estimate_duration | 标题=静音刷也能看懂：新手必学的画面表达法；分镜=7 | 总时长 27.25s，目标 30s，判定 pass | check_rules | 按违规删数字与「竖屏」、补P01引用、加品牌语并压缩旁白，重新估时长 |
| 7 | check_rules | 标题=静音刷也能看懂：新手必学的画面表达法；分镜=7 | 判定 pass | submit_script | 同一份修改稿同步做规则检查，确认违规已消除 |
| 8 | submit_script | 标题=静音刷也能看懂：新手必学的画面表达法；分镜=7 | 提交通过 | END:completed | 时长27.25秒pass且规则pass，提交同一份脚本 |
