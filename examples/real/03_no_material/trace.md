# Trace

| 步骤 | 动作 | 关键参数 | 返回摘要 | 下一步 | 决策依据 |
|---:|---|---|---|---|---|
| 1 | search_materials | query=剪刀鱼 直播推流 功能；top_k=5 | 命中 0 条 | search_materials | 主题为剪刀鱼直播推流，先检索对应素材 |
| 2 | search_materials | query=剪刀鱼 推流 直播工具；top_k=5 | 命中 0 条 | search_materials | 首轮无结果，换关键词再检索 |
| 3 | search_materials | query=剪刀鱼 视频编辑 功能介绍；top_k=10 | 命中 0 条 | ask_user | 第二次仍无结果，最后一次换更宽泛的关键词 |
| 4 | ask_user | missing_fields=["materials"]；questions=["能否提供“剪刀鱼”直播推流功能的官方介绍、功能清单或产品说明（原文）？", "是否有可用的素材库条目或素材 ID …；reason=脚本中的产品事实必须来自本次检索到的素材，但用“剪刀鱼 直播推流 功能”“剪刀鱼 推流 直播工具”“剪刀鱼 视频编辑 … | 已请求用户补充信息 | END:needs_input | 三次不同检索均返回0条素材，无法获取产品事实 |
