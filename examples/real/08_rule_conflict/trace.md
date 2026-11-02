# Trace

| 步骤 | 动作 | 关键参数 | 返回摘要 | 下一步 | 决策依据 |
|---:|---|---|---|---|---|
| 1 | search_materials | query=剪刀鱼 字幕功能 自动字幕；top_k=8 | 命中 1 条: P01 | search_materials | 需求为剪刀鱼字幕功能，先检索产品素材核实可写事实 |
| 2 | search_materials | query=剪刀鱼 视频剪辑 字幕 效率 新手；top_k=8 | 命中 1 条: P01 | search_materials | 素材过少，换查询再找字幕相关事实 |
| 3 | search_materials | query=剪刀鱼 剪辑软件 功能介绍；top_k=10 | 命中 0 条 | estimate_duration | 两次仅命中同一素材，最后换词再试一次 |
| 4 | estimate_duration | 标题=30秒看懂剪刀鱼的字幕功能（新手版）；分镜=7 | 总时长 29.25s，目标 30s，判定 pass | check_rules | 素材仅有一条事实，先估时长看是否接近30秒 |
| 5 | check_rules | 标题=30秒看懂剪刀鱼的字幕功能（新手版）；分镜=7 | 判定 fail: UNSUPPORTED_NUMBER, UNCITED_FEATURE, MISSING_CLOSING_SLOGAN | search_materials | 同步检查规则，确认未支持的80%说法是否需删除 |
| 6 | search_materials | query=剪刀鱼 竖屏 抖音；top_k=8 | 命中 1 条: P02 | estimate_duration | 规则提示存在 P02「竖屏」标签，检索确认其事实 |
| 7 | estimate_duration | 标题=新手必看：剪刀鱼的字幕功能速览；分镜=6 | 总时长 24.75s，目标 30s，判定 pass | check_rules | 按规则加引用与品牌语、去数字，重估时长 |
| 8 | check_rules | 标题=新手必看：剪刀鱼的字幕功能速览；分镜=6 | 判定 pass | estimate_duration | 同步复检引用完整性、数字与结尾品牌语 |
| 9 | estimate_duration | 标题=新手必看：剪刀鱼的字幕功能速览；分镜=6 | 总时长 27.5s，目标 30s，判定 pass | check_rules | 已通过但仅24.75秒，补充开场铺垫更贴近30秒 |
| 10 | check_rules | 标题=新手必看：剪刀鱼的字幕功能速览；分镜=6 | 判定 pass | submit_script | 修改后重新检查完整脚本规则 |
| 11 | submit_script | 标题=新手必看：剪刀鱼的字幕功能速览；分镜=6 | 提交通过 | END:completed | 时长27.5秒与规则检查均通过，提交同一份脚本 |
