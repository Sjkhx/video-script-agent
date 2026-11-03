# Trace

| 步骤 | 动作 | 关键参数 | 返回摘要 | 下一步 | 决策依据 |
|---:|---|---|---|---|---|
| 1 | search_materials | query=剪刀鱼 字幕功能；top_k=8 | 命中 1 条: P01 | search_materials | 需先检索剪刀鱼字幕功能的素材事实 |
| 2 | search_materials | query=剪刀鱼 效率提升 剪辑；top_k=8 | 命中 0 条 | search_materials | 素材仅一条"支持字幕"，再查效率类事实以确认是否有80%依据 |
| 3 | search_materials | query=自动字幕 识别 语音转文字；top_k=8 | 命中 1 条: P01 | estimate_duration | 效率查询无结果，换字幕识别/自动字幕方向再试一次 |
| 4 | estimate_duration | 标题=剪刀鱼字幕功能｜新手30秒入门；分镜=6 | 总时长 34.75s，目标 30s，判定 too_long，超出 4.75s | check_rules | 脚本初稿完成，先估算是否接近30秒 |
| 5 | check_rules | 标题=剪刀鱼字幕功能｜新手30秒入门；分镜=6 | 判定 fail: UNSUPPORTED_NUMBER, UNCITED_FEATURE, BANNED_TERM, UNSUPPORTED_TERM, MISSING_CLOSING_SLOGAN | estimate_duration | 同步检查规则，确认无越界表述 |
| 6 | estimate_duration | 标题=剪刀鱼字幕功能｜新手入门版；分镜=6 | 总时长 22s，目标 30s，判定 too_short，不足 2s | check_rules | 上版34.75秒超长且规则多项违规，压缩并修正后重检 |
| 7 | check_rules | 标题=剪刀鱼字幕功能｜新手入门版；分镜=6 | 判定 pass | estimate_duration | 同步按违规项修正：补引用P01、删禁用词、加品牌语 |
| 8 | estimate_duration | 标题=剪刀鱼字幕功能｜新手入门版；分镜=6 | 总时长 26s，目标 30s，判定 pass | check_rules | 上版22秒偏短，补充不含新事实的场景旁白 |
| 9 | check_rules | 标题=剪刀鱼字幕功能｜新手入门版；分镜=6 | 判定 pass | submit_script | 同步重检合规，确保补充内容不涉产品事实 |
| 10 | submit_script | 标题=剪刀鱼字幕功能｜新手入门版；分镜=6 | 提交通过 | END:completed | 时长26秒与规则均通过，提交同一份脚本 |
