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

- Python：14 项测试通过。
- Spring Boot：`mvn -DskipTests package` 通过。
- Vue：`npm run build` 通过。

## 安全与数据说明

- `.env`、API Key、数据库密码、上传材料、虚拟环境和向量索引不进入公开仓库。
- 公开仓库不包含课程原始资料、身份证件、营业执照或个人简历。
- 请仅使用合成数据、脱敏数据或已获得合法授权的数据进行复现。
- 本项目用于技术学习和项目展示，不可直接作为真实行政审批结论。
