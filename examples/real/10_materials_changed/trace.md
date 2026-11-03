# Trace

| 步骤 | 动作 | 关键参数 | 返回摘要 | 下一步 | 决策依据 |
|---:|---|---|---|---|---|
| 1 | search_materials | query=剪刀鱼 字幕功能；top_k=8 | 命中 0 条 | search_materials | 需求聚焦剪刀鱼字幕功能，先检索对应素材 |
| 2 | search_materials | query=剪刀鱼 视频剪辑 自动字幕；top_k=8 | 命中 0 条 | search_materials | 首次检索无结果，换关键词再试 |
| 3 | search_materials | query=剪刀鱼；top_k=10 | 命中 0 条 | ask_user | 第二次仍无结果，做最后一次换词检索 |
| 4 | ask_user | missing_fields=["materials"]；questions=["已用「剪刀鱼 字幕功能」「剪刀鱼 视频剪辑 自动字幕」「剪刀鱼」检索三次，均未命中任何素材。请问能否提供剪刀鱼字幕…；reason=脚本中的产品事实只能来自 search_materials 返回的素材，当前三次检索均无结果，无法安全地描述剪刀鱼的字… | 已请求用户补充信息 | END:needs_input | 三次检索均无素材，缺产品事实来源 |
