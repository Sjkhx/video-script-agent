# Trace

| 步骤 | 动作 | 关键参数 | 返回摘要 | 下一步 | 决策依据 |
|---:|---|---|---|---|---|
| 1 | ask_user | missing_fields=["target_duration_sec"]；questions=["这条“剪刀鱼字幕功能”的抖音短视频，你希望成片时长是多少秒？（例如 30 秒 / 45 秒 / 60 秒）"]；reason=目标时长是关键信息，缺失时不能自行假设，否则分镜数量和旁白长度无法确定。 | 已请求用户补充信息 | END:needs_input | 需求 JSON 中 target_duration_sec 为 null 且在 missing_required 里，必须先补齐 |
