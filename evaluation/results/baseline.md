# RAG 检索 Baseline

## 范围与复现条件

- 评测日期：2026-08-19
- 数据集：`evaluation/datasets/retrieval_eval.jsonl`（12 条人工标注问题；当前评测脚本使用内容相同的 `rag_cases.json` 执行）
- 知识文档：8 份涉水审批规则、填报说明、申请表和行业分类材料
- Embedding：`BAAI/bge-small-zh-v1.5`
- Chunk：700 / overlap 120
- Top-K：3
- 索引方式：独立临时 Chroma 集合，避免污染运行中的业务知识库

## 隔离索引基线（完整文档分块）

| 指标 | 结果 |
|---|---:|
| Hit@1 | 66.67% |
| Hit@3 | 100.00% |
| MRR | 0.8056 |
| 关键词召回率 | 86.11% |
| 文本块数 | 462 |
| 建库耗时 | 18.02 s |
| 平均查询延迟 | 8.75 ms |
| P95 查询延迟 | 11.11 ms |

## 线上持久化 BGE 索引复测

已将本地服务配置为 `USE_HF_EMBEDDINGS=1` 并重建知识库。运行时知识库状态为 8 份文档、106 个向量块、`BAAI/bge-small-zh-v1.5`；使用同一批 12 条标注问题复测得到：

| 指标 | 结果 |
|---|---:|
| Hit@1 | 66.67% |
| Hit@3 | 100.00% |
| MRR | 0.8056 |
| 关键词召回率 | 81.94% |
| 冷启动后的 11 条平均查询延迟 | 9.89 ms |

首次请求加载 BGE 模型耗时 1454.65 ms，因此整组 P95 为 1454.65 ms、整体均值为 130.29 ms。面试中应将模型冷启动和预热后的在线检索延迟分开说明，不能只报告其中较好的一项。

## 结论与待改进项

1. 12 条标注问题均在 Top-3 返回了至少一个正确来源；其中 8 条在首位命中。
2. RAG-001、RAG-002 在第 3 位才首次命中，RAG-005、RAG-006 在第 2 位命中；后续应优先分析这些问题的查询改写、词法召回和重排策略。
3. 该结果只反映当前 8 份文档和 12 条人工标注问题，不能外推为生产准确率。下一轮扩展到至少 50 条、并按文档类型和问题难度分层。
4. 线上持久化索引已切换为 512 维 BGE。`LocalHashEmbeddings` 仅保留为离线降级方案，不作为主项目的量化指标口径；切换 Embedding 时必须重建 Chroma 索引，不能混用向量维度。

## 复现命令

```powershell
cd C:\Users\20372\Desktop\direction-practice
$env:HF_HUB_OFFLINE='1'
.\python-ai-service\.venv310\Scripts\python.exe .\evaluation\ablate_chunks.py `
  --config 700/120 `
  --output-dir .\evaluation\results\baseline-run
```

该命令使用独立集合运行，输出完整的逐条排名与原始 JSON；不会修改当前业务服务的持久化索引。
