# Trace

| 步骤 | 动作 | 关键参数 | 返回摘要 | 下一步 | 决策依据 |
|---:|---|---|---|---|---|
| 1 | search_materials | query=剪刀鱼 字幕功能；top_k=8 | 命中 0 条 | search_materials | 主题与时长齐全，先检索产品素材 |
| 2 | search_materials | query=剪刀鱼 视频剪辑 自动识别语音 字幕；top_k=8 | 命中 0 条 | search_materials | 首次检索无结果，换用产品名+字幕关键词重试 |
| 3 | search_materials | query=剪刀鱼；top_k=10 | 命中 0 条 | ask_user | 第二次仍无结果，最后换用更宽泛的产品名检索 |
| 4 | ask_user | missing_fields=["materials"]；questions=["我连续检索了「剪刀鱼 字幕功能」「剪刀鱼 视频剪辑 自动识别语音 字幕」「剪刀鱼」三次，素材库均无结果。能否提供剪…；reason=脚本中的产品事实只能来自素材库，当前无任何关于剪刀鱼字幕功能的可用素材，若强行书写功能、数字或效果即属编造，需要补充素… | 已请求用户补充信息 | END:needs_input | 三次检索（含宽泛查询）均为0条素材，无法写产品事实 |
