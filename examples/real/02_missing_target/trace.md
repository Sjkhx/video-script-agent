# Trace

| 步骤 | 动作 | 关键参数 | 返回摘要 | 下一步 | 决策依据 |
|---:|---|---|---|---|---|
| 1 | ask_user | missing_fields=["target_duration_sec"]；questions=["这条关于「剪刀鱼字幕功能」的抖音短视频，你希望成片时长是多少秒？（例如 15 秒、30 秒、60 秒）"]；reason=目标时长是脚本创作的关键信息，缺失时无法判断分镜数量与旁白密度，需要你确认具体秒数后才能开始写。 | 已请求用户补充信息 | END:needs_input | 需求 JSON 中 target_duration_sec 为 null，属必填关键信息缺失。 |
