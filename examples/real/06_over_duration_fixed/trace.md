# Trace

| 步骤 | 动作 | 关键参数 | 返回摘要 | 下一步 | 决策依据 |
|---:|---|---|---|---|---|
| 1 | search_materials | query=剪刀鱼 字幕 模板 配音；top_k=10 | 命中 3 条: P01, P02, P04 | search_materials | 主题涉及字幕、模板、配音三个卖点，先检索产品素材 |
| 2 | search_materials | query=剪刀鱼 新手 一键生成 竖屏 音色 功能介绍；top_k=10 | 命中 2 条: P02, P04 | estimate_duration | 现有3条素材事实较简略，换词补检细节 |
| 3 | estimate_duration | 标题=新手 12 秒认识剪刀鱼：字幕、模板、配音；分镜=5 | 总时长 15s，目标 12s，判定 too_long，超出 3s | check_rules | 按三条素材事实写成5镜口语脚本，先验证12秒时长 |
| 4 | check_rules | 标题=新手 12 秒认识剪刀鱼：字幕、模板、配音；分镜=5 | 判定 fail: TITLE_TOO_LONG, UNCITED_FEATURE, BANNED_TERM, MISSING_CLOSING_SLOGAN | estimate_duration | 同步检查规则合规性，事实均引用素材原文 |
| 5 | estimate_duration | 标题=新手必看：剪刀鱼三件套；分镜=5 | 总时长 12s，目标 12s，判定 pass | check_rules | 上轮15秒超出且规则fail，压缩旁白并修标题措辞 |
| 6 | check_rules | 标题=新手必看：剪刀鱼三件套；分镜=5 | 判定 pass | submit_script | 同步复查改后脚本是否满足禁用词与结尾品牌语规则 |
| 7 | submit_script | 标题=新手必看：剪刀鱼三件套；分镜=5 | 提交通过 | END:completed | 时长12.0秒与规则均pass，提交同一份脚本 |
