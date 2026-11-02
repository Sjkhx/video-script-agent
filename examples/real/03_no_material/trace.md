# Trace

| 步骤 | 动作 | 关键参数 | 返回摘要 | 下一步 | 决策依据 |
|---:|---|---|---|---|---|
| 1 | search_materials | query=剪刀鱼 直播推流 功能；top_k=8 | 命中 0 条 | search_materials | 主题明确为剪刀鱼直播推流功能，先检索素材再写脚本 |
| 2 | search_materials | query=剪刀鱼 直播 推流 一键开播；top_k=8 | 命中 0 条 | search_materials | 首查0结果，换产品名+推流直播相关词再试 |
| 3 | search_materials | query=剪刀鱼；top_k=10 | 命中 0 条 | ask_user | 第二次检索仍为0，最后一次换更宽泛的产品关键词 |
| 4 | ask_user | missing_fields=["materials"]；questions=["请提供“剪刀鱼”直播推流功能的素材（如功能说明、支持平台、操作步骤、画质/延迟等官方描述），或告知素材库中的正确产…；reason=已用“剪刀鱼 直播推流 功能”“剪刀鱼 直播 推流 一键开播”“剪刀鱼”三次不同检索，素材库均无命中。脚本里的产品事实… | 已请求用户补充信息 | END:needs_input | 三次不同检索均返回0条素材，无法核实产品事实 |
