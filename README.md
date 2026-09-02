# 涉水审批材料 AI 合规初审系统

面向取水许可申请场景的 AI 辅助初审系统。项目采用 Vue 3、Spring Boot 与 FastAPI 双后端架构，实现角色权限、材料提交、文档解析、BGE 向量检索、证据约束生成、MCP 工具和 Agent 合规初审。

## 系统架构

```text
Vue 3 + Vite
      |
Spring Boot + MySQL
      | HTTP
FastAPI + LangChain + ChromaDB + MCP
```

- Vue：申请工作台、初审结果和法规知识检索页面。
- Spring Boot：认证授权、申请流程、审计日志以及 Python AI 服务代理。
- FastAPI：文档解析、RAG、规则检查、Agent 编排和引用校验。
- MySQL / ChromaDB：分别保存业务数据和向量化知识块。

## 核心能力

- PDF、DOC、DOCX 与图片材料解析，支持 OCR 降级。
- `BAAI/bge-small-zh-v1.5` 中文语义检索与精确文档标题加权。
- 可配置 BM25 + RRF 混合检索；经 A/B 评测后生产默认保持 `bge_only`。
- LLM 只能使用本次检索白名单中的 `citation_id`；非法引用或调用失败时自动降级为抽取式回答。
- 每条证据返回来源文件、分块编号、距离分数和可追溯引用。
- 领域路由拒绝无关问题，并放行取水许可、行业分类和材料审核问题。
- MCP 工具覆盖知识检索、完整性检查、行业类别校验、实体抽取和风险汇总。
- Agent 工具调用提供脱敏执行轨迹、耗时、状态和证据引用。
- 测试环境隔离外部模型，避免自动测试意外产生 API 费用。

## 量化评测

详细数据集、脚本和报告见 [evaluation](evaluation/README.md)。指标均来自本地人工标注回归集，不代表生产环境效果。

### 检索与路由

配置：8 份授权测试文档、30 条查询、Chunk `700/120`、Top-3。

| 指标 | 结果 |
|---|---:|
| Hit@1 | 96.67% |
| Hit@3 | 100.00% |
| MRR | 0.9833 |
| 关键词召回率 | 87.50% |
| 预热后 P95 查询延迟 | 14.04 ms |
| 领域路由准确率 | 100.00% |

BGE + BM25 + RRF 将关键词召回率提升至 88.89%，但 Hit@1 降至 93.33%、MRR 降至 0.9556，因此默认不启用混合检索。

### 证据约束生成

| 指标 | 结果 |
|---|---:|
| 综合通过率 | 100.00% |
| 引用格式有效率 | 100.00% |
| 期望来源引用率 | 100.00% |
| 答案关键词召回率 | 91.67% |
| LLM 生成率 | 100.00% |
| 降级率 | 0.00% |
| 平均端到端延迟 | 6565.61 ms |
| P95 端到端延迟 | 20216.06 ms |

生成评测只有 6 条本地用例。P95 长尾主要来自外部模型调用，当前不宣称满足生产实时性要求。

### LLM Agent 可观测性与真实评测

审核 Agent 采用“确定性预执行证据 + LLM 可选追加调用”的编排方式：每次 LLM 审核至少执行法规知识检索和风险汇总，避免模型直接跳过工具；前端初审结果页展示工具顺序、成功状态、脱敏摘要、耗时和引用编号。

3 组真实格式本地回归用例覆盖要件缺失、证照过期和合规通过。报告不保存申请字段、材料全文或 Agent 分析原文。

| 指标 | 结果 |
|---|---:|
| 综合通过率 | 100.00%（3/3） |
| 规则结论准确率 | 100.00% |
| Agent 结论一致率 | 100.00% |
| 必需工具覆盖率 | 100.00% |
| 工具调用成功率 | 100.00% |
| 引用有效率 | 100.00% |
| 轨迹脱敏通过率 | 100.00% |
| LLM 完成率 | 100.00% |
| 降级率 | 0.00% |
| 平均端到端延迟 | 9404.91 ms |
| P95 端到端延迟 | 11065.33 ms |
| 平均工具调用延迟 | 2.29 ms |

完整脱敏报告见 [LLM Agent 审核评测报告](evaluation/results/agent-llm-01/agent_llm_report.md)。指标仅描述当前小规模本地回归集，不代表生产环境效果。

## 快速启动

### Python AI 服务

建议使用 Python 3.10：

```powershell
cd python-ai-service
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload --port 8000
```

在 `.env` 中填写自己的 OpenAI 兼容 API 配置。正式检索建议保持：

```dotenv
USE_HF_EMBEDDINGS=1
RAG_HYBRID_ENABLED=0
RAG_LLM_GENERATION_ENABLED=1
```

将拥有合法使用权限的知识文档放入 `python-ai-service/knowledge_docs` 后，调用 `/kb/rebuild` 构建索引。

#### Docker 启动

Python AI 服务使用 CPU-only PyTorch 镜像，避免在仅使用 CPU 推理时安装 CUDA、cuDNN、NCCL 和 Triton：

```powershell
docker build -t policyflow-ai-service:0.1.0-rc1 .\python-ai-service
docker run --name policyflow-ai-service -d -p 8000:8000 `
  -e USE_HF_EMBEDDINGS=1 `
  -v policyflow-hf-cache:/root/.cache/huggingface `
  -v policyflow-chroma:/app/chroma_db `
  policyflow-ai-service:0.1.0-rc1
```

命名卷分别持久化 Hugging Face 模型缓存和 ChromaDB 向量索引。服务提供分层健康检查：

- `GET /health/live`：只检查 FastAPI 进程，供容器健康检查使用。
- `GET /health/ready`：要求知识库无错误且向量数量大于 0；未就绪时返回 HTTP 503。
- `GET /health`：保留原有综合状态接口，兼容已有调用方。

#### 增量知识库索引

服务使用 SHA-256 文件哈希跟踪知识文档版本。启动建库时只对新增或内容发生变化的文档执行分块与向量化，未变化文档直接复用 ChromaDB 中的向量；已删除文档的旧向量会同步清理。更新时先写入新哈希对应的向量块，再删除旧块，降低模型调用失败造成数据缺失的风险。

建库结果和启动日志包含 `added`、`updated`、`deleted`、`unchanged` 与 `embedded_chunks`，便于定位索引变化并观测重复向量化。首次升级已有向量库时，缺少哈希元数据的旧块会自动迁移；后续无变更启动的 `embedded_chunks` 应为 `0`。

本地实测中，CPU-only PyTorch 将镜像内容体积从 3.09 GB 降至 545 MB，减少约 82.4%；Docker 磁盘占用从 9.07 GB 降至 2.52 GB。复用命名卷后，新容器加载 BGE 并恢复 106 个向量的时间由约 25.9 秒降至约 17.5 秒。以上数据来自当前开发机，不代表生产环境性能。

### Spring Boot

```powershell
$env:DB_URL='jdbc:mysql://127.0.0.1:3306/water_approval?createDatabaseIfNotExist=true&useUnicode=true&characterEncoding=UTF-8&serverTimezone=Asia/Shanghai'
$env:DB_USERNAME='root'
$env:DB_PASSWORD='your-password'
cd spring-backend
mvn spring-boot:run
```

### Vue 前端

```powershell
cd frontend
npm install
npm run dev
```

默认地址：Vue `http://localhost:5173`、Spring `http://127.0.0.1:8080`、FastAPI 文档 `http://127.0.0.1:8000/docs`。

## 主要接口

| 服务 | 接口 | 说明 |
|---|---|---|
| Java | `POST /api/auth/login` | 登录 |
| Java | `POST /api/submit` | 提交申请与附件 |
| Java | `POST /api/review/{id}` | 发起 AI 初审 |
| Java | `POST /api/rag/query` | 鉴权后代理法规知识检索 |
| Python | `POST /review` | 执行初审流程 |
| Python | `POST /rag/query` | 证据检索与受约束生成 |
| Python | `POST /kb/rebuild` | 重建向量知识库 |
| Python | `POST /mcp/call` | 调用 MCP 工具 |

## 验证状态

- Python：26 项测试通过。
- Spring Boot：`mvn -DskipTests package` 通过。
- Vue：`npm run build` 通过。

## 安全与数据说明

- `.env`、API Key、数据库密码、上传材料、虚拟环境和向量索引不进入公开仓库。
- 公开仓库不包含课程原始资料、身份证件、营业执照或个人简历。
- 请仅使用合成数据、脱敏数据或已获得合法授权的数据进行复现。
- 本项目用于技术学习和项目展示，不可直接作为真实行政审批结论。
