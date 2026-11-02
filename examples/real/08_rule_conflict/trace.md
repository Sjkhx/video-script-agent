# Trace

| 步骤 | 动作 | 关键参数 | 返回摘要 | 下一步 | 决策依据 |
|---:|---|---|---|---|---|
| 1 | search_materials | query=剪刀鱼 字幕功能 自动字幕；top_k=6 | 命中 1 条: P01 | search_materials | 关键信息齐全，先检索产品素材以获取字幕功能事实 |
| 2 | search_materials | query=剪刀鱼 效率提升 80% 剪辑；top_k=6 | 命中 0 条 | search_materials | 素材仅“支持字幕”，再查效率提升相关素材以核实80%说法 |
| 3 | search_materials | query=剪刀鱼 数据 提速 效率 字幕识别；top_k=6 | 命中 1 条: P01 | estimate_duration | 效率素材无结果，换查询核实80%数据出处 |
| 4 | estimate_duration | 标题=剪刀鱼字幕功能｜新手第一条视频怎么剪（30秒）；分镜=6 | 总时长 39.75s，目标 30s，判定 too_long，超出 9.75s | check_rules | 素材仅"支持字幕"一条，据此写6镜初稿并同时做时长与规则检查 |
| 5 | check_rules | 标题=剪刀鱼字幕功能｜新手第一条视频怎么剪（30秒）；分镜=6 | 判定 fail: TITLE_TOO_LONG, BANNED_TERM, UNSUPPORTED_NUMBER, UNCITED_FEATURE, MISSING_CLOSING_SLOGAN | estimate_duration | 同稿送检，确认80%等无素材支持的表述未写入 |
| 6 | estimate_duration | 标题=剪刀鱼剪辑，新手也能顺手出片；分镜=5 | 总时长 24.75s，目标 30s，判定 pass | check_rules | 初稿39.75s过long且规则fail，压缩为5镜重检 |
| 7 | check_rules | 标题=剪刀鱼剪辑，新手也能顺手出片；分镜=5 | 判定 pass | submit_script | 同稿送检，已删禁用词与无依据数字，末镜加品牌语 |
| 8 | submit_script | 标题=剪刀鱼剪辑，新手也能顺手出片；分镜=5 | 提交通过 | END:completed | 同一份脚本时长24.75s通过且规则pass，直接提交 |
