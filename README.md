# 涉水审批材料 AI 合规初审系统

面向取水许可申请场景的 AI 辅助初审系统。项目采用 Java + Python 双服务架构，配合 Vue 3 前端，实现申请材料提交、角色权限控制、文档解析、RAG 知识检索、MCP 工具调用和 Agent 合规初审。

## 系统架构

```text
Vue 3 + Vite
      |
Spring Boot + MySQL
      | HTTP
FastAPI + LangChain Agent + MCP + ChromaDB
```

- **Vue 3**：登录注册、角色工作台、申请提交、附件上传和初审结果展示。
- **Spring Boot**：认证授权、行级数据权限、申请流程、附件元数据、审计日志和 Python 服务调度。
- **FastAPI**：文档解析、RAG 检索、确定性规则检查、Agent 初审和 MCP 工具服务。
- **MySQL / ChromaDB**：分别存储结构化业务数据和向量化知识文本块。

## 核心功能

- 区分申请人、审核员和管理员三类角色，并进行资源归属校验。
- 支持上传 PDF、DOCX、JPG、PNG 等多种格式的申请材料。
- 支持 PDF/DOCX 文档解析、递归文本分块和 BGE Embedding 向量化。
- 基于 ChromaDB 进行 Top-K 语义检索，返回文档内容、来源和相似度分数。
- 实现 `knowledge_search`、`check_completeness`、`industry_category_check`、`extract_key_entities`、`risk_summary` 等 MCP 工具。
- 通过 LangChain Tool Calling 调用 DeepSeek 等 OpenAI 兼容模型。
- 结合 Agent 和确定性规则检查材料缺失、身份信息不一致、必填字段缺失、证件类型错误和证件过期等问题。
- 提供可重复执行的 RAG、Agent、缓存和 Chunk 参数消融评测。

## AI 初审流程

1. 申请人填写申请信息并上传附件。
2. Spring Boot 保存业务数据和附件信息。
3. Java 后端通过 HTTP 调用 FastAPI 的 `/review` 接口。
4. Python 服务解析 PDF、Word 和图片材料，并执行 OCR、实体抽取与规则校验。
5. Agent 调用 MCP 工具检索知识库、检查材料完整性并生成结构化问题清单。
6. Java 后端保存初审结论，前端展示问题位置、风险等级、法规依据和修改建议。

## 量化评测

仓库在 [`evaluation`](evaluation/README.md) 中提供评测数据集、执行脚本和结果报告。

当前小规模人工标注课程数据集的基线结果：

- 固定 BGE Embedding 和 Top-3，对比 `400/80`、`700/120`、`1000/150` 三组 Chunk 配置。
- `700/120` 在当前数据集取得 Hit@3 100%、MRR 0.8056、关键词召回率 86.11%。
- 10 组真实格式回归材料重复审核 3 次，预设问题类型 F1 和稳定一致率均为 100%。

以上指标仅代表当前小规模人工标注回归集，不等同于生产环境效果。后续可通过扩大盲测集、增加 Rerank 和引入真实脱敏数据进一步验证。

## 快速启动

### 1. 启动 Python AI 服务

建议使用 Python 3.10：

```powershell
cd python-ai-service
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn main:app --reload --port 8000
```

在 `.env` 中填写自己的 OpenAI 兼容 API 配置。DeepSeek 示例：

```dotenv
OPENAI_API_KEY=your-api-key
OPENAI_MODEL=deepseek-chat
OPENAI_BASE_URL=https://api.deepseek.com/v1
```

将拥有合法使用权限的 PDF/DOCX 知识文档放入 `python-ai-service/knowledge_docs`，再调用知识库重建接口。出于隐私和版权考虑，课程原始文档及证件样例未上传到公开仓库。

### 2. 启动 MySQL 和 Spring Boot

创建 MySQL 账号并设置环境变量：

```powershell
$env:DB_URL='jdbc:mysql://127.0.0.1:3306/water_approval?createDatabaseIfNotExist=true&useUnicode=true&characterEncoding=UTF-8&serverTimezone=Asia/Shanghai'
$env:DB_USERNAME='root'
$env:DB_PASSWORD='your-password'
cd spring-backend
mvn spring-boot:run
```

### 3. 启动 Vue 前端

```powershell
cd frontend
npm install
npm run dev
```

默认服务地址：

- Vue 前端：`http://localhost:5500`
- Java API：`http://127.0.0.1:8080`
- Python API 与 Swagger：`http://127.0.0.1:8000/docs`

## 主要接口

| 服务 | 接口 | 说明 |
|---|---|---|
| Java | `POST /api/auth/register` | 申请人注册 |
| Java | `POST /api/auth/login` | 登录并获取 Token |
| Java | `POST /api/submit` | 提交申请和附件 |
| Java | `GET /api/list` | 按角色和数据权限查询申请 |
| Java | `POST /api/review/{id}` | 调用 Python 发起 AI 初审 |
| Python | `POST /review` | 执行 AI 初审流程 |
| Python | `POST /kb/rebuild` | 重建 ChromaDB 知识库 |
| Python | `GET /mcp/tools` | 查看 MCP 工具列表 |
| Python | `POST /mcp/call` | 调用指定 MCP 工具 |

## 项目目录

```text
frontend/            Vue 3 + Vite 前端
spring-backend/      Spring Boot 业务后端
python-ai-service/   FastAPI、LangChain、ChromaDB 与 MCP 服务
evaluation/          RAG、Agent、缓存和 Chunk 消融评测
```

## 安全与数据说明

- `.env`、API Key、数据库密码、上传文件、虚拟环境和向量索引均已加入忽略规则。
- 公开仓库不包含课程原始资料、身份证件、营业执照、个人简历等敏感文件。
- 复现 OCR 和材料审查时，请使用合成数据、脱敏数据或已获得合法授权的数据。

## 项目定位

本项目用于课程实践、技术学习和个人项目展示，重点体现 Java + Python 双栈集成、RAG、Agent、MCP 和 AI 工程化评测能力，不可直接作为真实行政审批结论使用。

