# Trace

| 步骤 | 动作 | 关键参数 | 返回摘要 | 下一步 | 决策依据 |
|---:|---|---|---|---|---|
| 1 | search_materials | query=剪刀鱼 字幕功能；top_k=8 | 命中 0 条 | search_materials | 主题与时长齐全，先检索剪刀鱼字幕功能素材 |
| 2 | search_materials | query=剪刀鱼 自动字幕 识别；top_k=8 | 命中 0 条 | search_materials | 首查无结果，换「剪刀鱼 自动字幕」再试 |
| 3 | search_materials | query=剪刀鱼 视频剪辑 字幕 教程；top_k=8 | 命中 0 条 | ask_user | 两次无结果，最后一次换「剪刀鱼 剪辑 字幕 教程」 |
| 4 | ask_user | missing_fields=["materials"]；questions=["请问「剪刀鱼」是哪个产品（App／剪辑软件）？能否提供它的字幕功能官方素材、功能介绍或功能截图说明？", "字幕功…；reason=已用 3 种不同查询检索「剪刀鱼」字幕相关素材均无结果，脚本中的产品事实必须来自素材，目前无任何可用来源。 | 已请求用户补充信息 | END:needs_input | 三次不同查询均零命中，缺产品素材无法写事实 |
