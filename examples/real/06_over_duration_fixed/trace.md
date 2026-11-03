# Trace

| 步骤 | 动作 | 关键参数 | 返回摘要 | 下一步 | 决策依据 |
|---:|---|---|---|---|---|
| 1 | search_materials | query=剪刀鱼 字幕 模板 配音；top_k=8 | 命中 3 条: P01, P02, P04 | estimate_duration | 需先获取剪刀鱼三个卖点的素材事实 |
| 2 | estimate_duration | 标题=新手三点记住剪刀鱼；分镜=5 | 总时长 15.25s，目标 12s，判定 too_long，超出 3.25s | check_rules | 素材已拿到三个卖点，先估算 12 秒是否放得下 |
| 3 | check_rules | 标题=新手三点记住剪刀鱼；分镜=5 | 判定 fail: UNSUPPORTED_TERM, UNCITED_FEATURE, MISSING_CLOSING_SLOGAN | estimate_duration | 同时检查脚本是否有事实或品牌表述问题 |
| 4 | estimate_duration | 标题=新手三点记住剪刀鱼；分镜=4 | 总时长 9.75s，目标 12s，判定 pass | check_rules | 首版 15.25 秒超时且规则失败，压缩为四镜并修正引用 |
| 5 | check_rules | 标题=新手三点记住剪刀鱼；分镜=4 | 判定 pass | submit_script | 同步复检压缩版是否清除了不支持词与漏引用 |
| 6 | submit_script | 标题=新手三点记住剪刀鱼；分镜=4 | 提交通过 | END:completed | 压缩版时长 9.75 秒通过、规则 pass，提交同一份脚本 |
