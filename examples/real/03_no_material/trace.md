# Trace

| 步骤 | 动作 | 关键参数 | 返回摘要 | 下一步 | 决策依据 |
|---:|---|---|---|---|---|
| 1 | search_materials | query=剪刀鱼 直播推流；top_k=8 | 命中 0 条 | search_materials | 主题为剪刀鱼直播推流，先检索产品素材 |
| 2 | search_materials | query=剪刀鱼 直播 功能 教程；top_k=8 | 命中 0 条 | search_materials | 首次检索零结果，换查询词重试 |
| 3 | search_materials | query=剪刀鱼 剪映 推流 直播伴侣；top_k=10 | 命中 0 条 | ask_user | 两次零结果，第三次换更宽泛查询 |
| 4 | ask_user | missing_fields=["materials"]；questions=["我在素材库里没检索到“剪刀鱼”的任何资料（试过「剪刀鱼 直播推流」「剪刀鱼 直播 功能 教程」「剪刀鱼 剪映 推流…；reason=脚本中的产品事实只能来自本次检索返回的素材，当前素材为空，无法在保证不虚构的前提下写出直播推流脚本。 | 已请求用户补充信息 | END:needs_input | 三次不同检索均无素材，无法写产品事实 |
