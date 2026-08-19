# 项目量化评测

本目录保存人工标注数据集、可重复执行脚本和代表性报告。所有结果仅用于本地项目回归，不外推为生产准确率。

## 1. RAG 检索评测

`datasets/retrieval_eval.jsonl` 包含 30 条查询及期望来源、关键词和回答要点。

```powershell
.\python-ai-service\.venv310\Scripts\python.exe .\evaluation\evaluate_rag.py `
  --output-dir .\evaluation\results\rag-current
```

指标包括 Hit@1、Hit@3、MRR、关键词召回率、平均延迟和 P95。正式指标使用 `BAAI/bge-small-zh-v1.5`；`LocalHashEmbeddings` 仅作为离线降级，不作为主要量化模型。

## 2. Embedding 与 Chunk 消融

```powershell
.\python-ai-service\.venv310\Scripts\python.exe .\evaluation\compare_embeddings.py
.\python-ai-service\.venv310\Scripts\python.exe .\evaluation\ablate_chunks.py
```

Chunk 实验固定 BGE 和 Top-3，对比 `400/80`、`700/120` 与 `1000/150`，当前小规模集合推荐 `700/120`。

## 3. 领域路由与拒答

```powershell
.\python-ai-service\.venv310\Scripts\python.exe .\evaluation\evaluate_domain_gate.py
.\python-ai-service\.venv310\Scripts\python.exe .\evaluation\evaluate_refusal.py
```

路由集同时检查无关问题拒答和领域问题放行；独立拒答集用于防止系统对领域外问题生成看似可信的答案。

## 4. 证据约束生成

`datasets/generation_eval.jsonl` 包含 6 条生成问题，评测引用有效性、期望来源引用、关键词覆盖、生成/降级比例和端到端延迟。

```powershell
.\python-ai-service\.venv310\Scripts\python.exe .\evaluation\evaluate_generation.py `
  --output-dir .\evaluation\results\generation-current
```

使用 `--case-id GEN-004` 可只运行单条。该脚本会真实调用 `.env` 中配置的模型 API，可能产生费用，因此不会加入默认批量测试。

## 5. Agent 审核

```powershell
.\python-ai-service\.venv310\Scripts\python.exe .\evaluation\evaluate_agent.py --repeats 3
```

Agent 评测关注审核结论、问题类型 Precision/Recall/F1、重复运行稳定性和延迟。

## 使用原则

- 只引用最近一次同代码版本报告中的结果。
- 更换 Embedding、Chunk、Top-K、Prompt、文档或规则后重新评测。
- 同时报告准确率、失败样例和 P95，不只展示最好结果。
- 不把小规模本地回归数据描述为生产指标。
