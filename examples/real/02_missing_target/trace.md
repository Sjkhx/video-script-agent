# Trace

| 步骤 | 动作 | 关键参数 | 返回摘要 | 下一步 | 决策依据 |
|---:|---|---|---|---|---|
| 1 | ask_user | missing_fields=["target_duration_sec"]；questions=["这条「剪刀鱼的字幕功能」短视频希望控制在多少秒？（例如 15 秒、30 秒、60 秒）"]；reason=目标时长是关键信息且当前缺失，脚本分镜数量和旁白长度都依赖它，不能自行假设。 | 已请求用户补充信息 | END:needs_input | 需求中 target_duration_sec 为 null，属关键信息缺失，须先询问。 |
