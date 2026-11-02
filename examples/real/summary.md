# 真实运行汇总

共 10 个用例；本文件由 `scripts/run_examples.py` 生成。

| 用例 | 状态 | 符合预期 | 动作路径 | 模型 | tokens | 覆盖 | 备注 |
|---|---|---|---|---|---:|---|---|
| 01_normal | completed | 是 | search_materials -> search_materials -> search_materials -> estimate_duration -> check_rules -> estimate_duration -> check_rules -> submit_script | deepseek-v4.1-flash | 28185 | 正常生成、参考实例 | — |
| 02_missing_target | needs_input | 是 | ask_user | deepseek-v4.1-flash | 2604 | 缺关键信息 | — |
| 03_no_material | needs_input | 是 | search_materials -> search_materials -> search_materials -> ask_user | deepseek-v4.1-flash | 11173 | 无素材、改写查询后请求补充 | — |
| 04_tool_fail_transient | completed | 是 | search_materials -> search_materials -> search_materials -> estimate_duration -> check_rules -> estimate_duration -> check_rules -> estimate_duration -> check_rules -> submit_script | deepseek-v4.1-flash | 37390 | 工具失败后恢复 | — |
| 05_tool_fail_permanent | failed | 是 | search_materials -> search_materials -> search_materials -> estimate_duration -> check_rules -> estimate_duration -> check_rules -> report_failure | deepseek-v4.1-flash | 26206 | 工具失败、明确失败 | — |
| 06_over_duration_fixed | completed | 是 | search_materials -> estimate_duration -> check_rules -> estimate_duration -> check_rules -> submit_script | deepseek-v4.1-flash | 20410 | 超时长后修正 | — |
| 07_over_duration_infeasible | failed | 是 | search_materials -> estimate_duration -> check_rules -> estimate_duration -> estimate_duration -> report_failure | deepseek-v4.1-flash | 16108 | 超时长、明确失败 | — |
| 08_rule_conflict | completed | 是 | search_materials -> search_materials -> search_materials -> estimate_duration -> check_rules -> search_materials -> estimate_duration -> check_rules -> estimate_duration -> check_rules -> submit_script | deepseek-v4.1-flash | 49231 | 规则风险、不编造 | — |
| 09_query_rewrite | completed | 是 | search_materials -> search_materials -> search_materials -> estimate_duration -> check_rules -> estimate_duration -> check_rules -> estimate_duration -> check_rules -> submit_script | deepseek-v4.1-flash | 34376 | 改写查询 | — |
| 10_materials_changed | needs_input | 是 | search_materials -> search_materials -> search_materials -> ask_user | deepseek-v4.1-flash | 11130 | 改检索结果后动作变化 | — |
