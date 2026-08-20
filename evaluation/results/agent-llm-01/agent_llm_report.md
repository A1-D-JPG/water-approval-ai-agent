# LLM Agent 审核评测报告

- 评测时间：2026-08-20T13:56:55
- 用例数量：3
- 综合通过率：100.00%
- 规则结论准确率：100.00%
- Agent 结论一致率：100.00%
- 必需工具覆盖率：100.00%
- 工具调用成功率：100.00%
- 引用有效率：100.00%
- 轨迹脱敏通过率：100.00%
- LLM 完成率：100.00%
- 降级率：0.00%
- 平均端到端延迟：9404.91 ms
- P95 端到端延迟：11065.33 ms
- 平均工具调用延迟：2.29 ms

| 用例 | 期望/规则/Agent 结论 | 模式 | 工具 | 引用有效 | 轨迹脱敏 | 延迟(ms) | 结果 |
|---|---|---|---|---:|---:|---:|---|
| AGENT-LLM-001 | REJECTED/REJECTED/REJECTED | langchain_agent | knowledge_search / risk_summary / check_completeness / industry_category_check / risk_summary | 是 | 是 | 9511.83 | PASS |
| AGENT-LLM-002 | REJECTED/REJECTED/REJECTED | langchain_agent | knowledge_search / risk_summary / check_completeness / industry_category_check / risk_summary | 是 | 是 | 7637.58 | PASS |
| AGENT-LLM-003 | APPROVED/APPROVED/APPROVED | langchain_agent | knowledge_search / risk_summary / check_completeness / industry_category_check / risk_summary | 是 | 是 | 11065.33 | PASS |

> 本报告不保存申请字段、材料全文或 Agent 分析原文。指标来自本地小规模回归集，不代表生产环境总体效果。
