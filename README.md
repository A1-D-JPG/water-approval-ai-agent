# Water Approval AI Agent

An AI-assisted preliminary review system for water-use permit applications.
The project uses a Java + Python dual-service architecture with a Vue 3
frontend and demonstrates RAG, LangChain Agent, ChromaDB and MCP tool calling.

## Architecture

```text
Vue 3 + Vite
      |
Spring Boot + MySQL
      | HTTP
FastAPI + LangChain Agent + MCP + ChromaDB
```

- **Vue 3**: login, role-based workspaces, application submission and review results.
- **Spring Boot**: authentication, row-level authorization, application workflow,
  attachment metadata, audit logs and Python service orchestration.
- **FastAPI**: document parsing, RAG retrieval, deterministic checks, Agent review
  and MCP tools.
- **MySQL / ChromaDB**: structured business data and vectorized knowledge chunks.

## Highlights

- Applicant, reviewer and administrator roles with resource ownership checks.
- Multi-file upload for PDF, DOCX, JPG and PNG materials.
- PDF/DOCX parsing, recursive text splitting and BGE-compatible embeddings.
- Semantic Top-K retrieval with content, source and similarity score.
- MCP tools including `knowledge_search`, `check_completeness`,
  `industry_category_check`, `extract_key_entities` and `risk_summary`.
- LangChain Tool Calling with an OpenAI-compatible API such as DeepSeek.
- Deterministic rule checks for missing materials, inconsistent identities,
  required fields, document type mismatch and expired credentials.
- Reproducible RAG, Agent, cache and chunk-ablation evaluations.

## Evaluation snapshot

The repository includes evaluation datasets, scripts and generated reports in
[`evaluation`](evaluation/README.md). On the current small, manually labelled
course dataset, the selected BGE Top-3 configuration achieved Hit@3 100%, MRR
0.8056 and keyword recall 86.11%. These figures are a reproducible baseline,
not a production benchmark; a larger blind test set is the next step.

## Quick start

### 1. Python AI service

```powershell
cd python-ai-service
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn main:app --reload --port 8000
```

Configure `.env` with your own OpenAI-compatible API key. DeepSeek example:

```dotenv
OPENAI_API_KEY=your-api-key
OPENAI_MODEL=deepseek-chat
OPENAI_BASE_URL=https://api.deepseek.com/v1
```

Put your own legally distributable PDF/DOCX files in
`python-ai-service/knowledge_docs`. Original course materials and identity
samples are excluded from this public repository.

### 2. MySQL and Spring Boot

Create a MySQL database account, then set environment variables:

```powershell
$env:DB_URL='jdbc:mysql://127.0.0.1:3306/water_approval?createDatabaseIfNotExist=true&useUnicode=true&characterEncoding=UTF-8&serverTimezone=Asia/Shanghai'
$env:DB_USERNAME='root'
$env:DB_PASSWORD='your-password'
cd spring-backend
mvn spring-boot:run
```

### 3. Vue frontend

```powershell
cd frontend
npm install
npm run dev
```

Default addresses:

- Frontend: `http://localhost:5500`
- Java API: `http://127.0.0.1:8080`
- Python API and Swagger: `http://127.0.0.1:8000/docs`

## Main APIs

| Service | Endpoint | Purpose |
|---|---|---|
| Java | `POST /api/auth/register` | Applicant registration |
| Java | `POST /api/auth/login` | Login and token issuance |
| Java | `POST /api/submit` | Submit application and files |
| Java | `GET /api/list` | Role-filtered application list |
| Java | `POST /api/review/{id}` | Trigger AI preliminary review |
| Python | `POST /review` | Run the AI review workflow |
| Python | `POST /kb/rebuild` | Rebuild the vector knowledge base |
| Python | `GET /mcp/tools` | List exposed MCP tools |
| Python | `POST /mcp/call` | Invoke an MCP tool |

## Project structure

```text
frontend/            Vue 3 + Vite frontend
spring-backend/      Spring Boot business backend
python-ai-service/   FastAPI, LangChain, ChromaDB and MCP
evaluation/          RAG, Agent, cache and chunk-ablation evaluations
```

## Security and data notice

- `.env`, API keys, database passwords, uploaded files and vector indexes are ignored.
- Original government documents, course handouts and identity-card samples are
  not included in the public repository.
- Use synthetic or properly authorized data when reproducing OCR and review tests.

## License

This repository is provided for learning and portfolio demonstration. Verify
the redistribution rights of any knowledge documents before adding them.

