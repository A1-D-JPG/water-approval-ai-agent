# 项目量化评测

本目录提供三套可重复执行的评测，所有指标都基于明确的数据集和脚本生成，避免把少量演示请求表述为生产性能。

## 1. RAG 检索评测

数据集 `datasets/rag_cases.json` 包含 12 条人工标注查询，每条记录提供期望来源文档和关键内容。评测指标包括：

- `Hit@1`、`Hit@3`：前 1/3 个结果是否包含正确来源。
- `MRR`：正确来源出现得越靠前，分数越高。
- 关键词召回率：返回片段覆盖人工标注关键词的比例。
- 平均延迟和 P95 延迟。

```powershell
cd water-approval-ai-agent
.\python-ai-service\.venv\Scripts\python.exe .\evaluation\evaluate_rag.py
```

当前默认使用 `LocalHashEmbeddings` 离线降级模型。切换 BGE 后应使用同一数据集重新评测，才能客观比较效果：

```powershell
$env:USE_HF_EMBEDDINGS='1'
.\python-ai-service\.venv\Scripts\python.exe .\evaluation\evaluate_rag.py
```

注意：切换 Embedding 模型前需要用对应模型重建 ChromaDB，不能让新查询向量与旧文档向量混用。

也可以运行隔离的 A/B 对照。该脚本为两个模型分别创建内存 Chroma 集合，不覆盖业务知识库：

```powershell
.\python-ai-service\.venv\Scripts\python.exe .\evaluation\compare_embeddings.py
```

### Chunk 参数消融实验

消融实验固定 `BAAI/bge-small-zh-v1.5`、12 条人工标注查询和 `Top-3`，默认只改变以下分块参数：

- `400/80`
- `700/120`
- `1000/150`

指标包括块数量、Hit@1、Hit@3、MRR、关键词召回率、建库耗时、平均查询延迟和 P95。为保证单变量原则，实验索引完整文档，不使用业务建库的单文件 80 块上限；使用独立内存 Chroma 集合，不覆盖业务知识库。

```powershell
$env:HF_HUB_OFFLINE='1'
.\python-ai-service\.venv\Scripts\python.exe .\evaluation\ablate_chunks.py
```

当前 12 条标注查询上的实测结果：

| Chunk/Overlap | 块数 | Hit@1 | Hit@3 | MRR | 关键词召回率 |
|---|---:|---:|---:|---:|---:|
| `400/80` | 835 | 58.33% | 91.67% | 0.7361 | 80.56% |
| `700/120` | 462 | 66.67% | 100.00% | 0.8056 | 86.11% |
| `1000/150` | 317 | 58.33% | 83.33% | 0.6806 | 83.33% |

因此当前评测集推荐 `700/120`：它的 Hit@3、MRR 和关键词召回率均为三组最高。该结论只适用于当前 8 份文档和 12 条标注查询，扩大知识库或更换文档类型后需要重新评测。

也可以传入自定义参数：

```powershell
.\python-ai-service\.venv\Scripts\python.exe .\evaluation\ablate_chunks.py `
  --config 300/60 --config 500/100 --config 800/120
```

## 2. Agent 审核评测

数据集 `datasets/agent_cases.json` 为 10 组真实格式材料定义期望审核结论和问题类型。评测指标包括：

- 审核结论准确率。
- 问题类型集合完全匹配率。
- 问题类型 Precision、Recall、F1。
- 同一材料多次审核的稳定一致率。
- 平均审核延迟。

```powershell
.\python-ai-service\.venv\Scripts\python.exe .\evaluation\evaluate_agent.py --repeats 3
```

评测默认调用确定性规则审查核心，因为最终 `APPROVED/REJECTED` 和结构化问题清单由它产生。DeepSeek Agent 用于解释和工具编排时，可另行增加模型输出格式与引用正确性评测。

## 3. Redis 缓存冷热对照

缓存评测针对 OfferPilot 的 `GET /api/job/hot`，使用 Redis RESP 协议自动删除和检查 `offerpilot:job:hot`，不依赖额外 Python Redis 包：

1. 冷缓存组：每次请求前删除缓存键，包含 MySQL 查询和 Redis 写入。
2. 热缓存组：先预热一次，之后持续从 Redis 读取。
3. 输出平均值、P50、P95、最小值、最大值、加速比和响应内容一致性。

先启动 OfferPilot、MySQL 和 Redis，再执行：

```powershell
.\python-ai-service\.venv\Scripts\python.exe .\evaluation\evaluate_cache.py --requests 30
```

如果 OfferPilot 不在默认端口：

```powershell
.\python-ai-service\.venv\Scripts\python.exe .\evaluation\evaluate_cache.py `
  --url http://127.0.0.1:8081/api/job/hot `
  --requests 30
```

## 统一执行

只运行当前涉水审批项目的 RAG 与 Agent 评测：

```powershell
.\python-ai-service\.venv\Scripts\python.exe .\evaluation\run_all.py
```

同时生成 LocalHash 与 BGE 的隔离 A/B 对照：

```powershell
.\python-ai-service\.venv\Scripts\python.exe .\evaluation\run_all.py --compare-embeddings
```

同时运行 Chunk 参数消融：

```powershell
.\python-ai-service\.venv\Scripts\python.exe .\evaluation\run_all.py --ablate-chunks
```

OfferPilot 同时运行时加入缓存评测：

```powershell
.\python-ai-service\.venv\Scripts\python.exe .\evaluation\run_all.py --include-cache
```

结果写入 `evaluation/results`，其中 JSON 保存完整原始结果，Markdown 可直接用于答辩和面试说明。

## 简历指标使用原则

- 只引用最近一次报告中的真实结果。
- 明确写“人工标注回归集”或“本地测试环境”，不外推为生产准确率。
- 更换 Embedding、Chunk、Top-K、Prompt 或规则后重新运行评测。
- 缓存性能应同时给出冷/热两组和 P95，不只写少量请求的平均值。
