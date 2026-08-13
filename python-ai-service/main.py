from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import Tool
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from ai_core import (
    CHROMA_DIR,
    build_knowledge_base,
    check_completeness,
    deterministic_review,
    extract_key_entities,
    industry_category_check,
    kb_status,
    knowledge_search,
    load_materials,
    risk_summary,
)

ENV_PATH = Path(__file__).resolve().parent / ".env"


def load_env_file() -> None:
    """Load local .env values without adding an extra runtime dependency."""
    if not ENV_PATH.exists():
        return
    for raw_line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    alias_map = {
        "API_KEY": "OPENAI_API_KEY",
        "AI_MODEL": "OPENAI_MODEL",
        "AI_BASE_URL": "OPENAI_BASE_URL",
    }
    for source, target in alias_map.items():
        if os.getenv(source) and not os.getenv(target):
            os.environ[target] = os.getenv(source, "")


load_env_file()

app = FastAPI(title="Water Approval AI Service", version="1.0.0")


class ReviewRequest(BaseModel):
    application_id: int
    applicant_name: str = ""
    id_number: str = ""
    project_name: str = ""
    water_location: str = ""
    water_use: str = ""
    industry_category: str = ""
    contact_phone: str = ""
    credit_code: str = ""
    file_path: str | None = None
    file_paths: list[str] = Field(default_factory=list)


class ToolCallRequest(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


def _run_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name == "knowledge_search":
        return knowledge_search(query=str(arguments.get("query", "")), top_k=int(arguments.get("top_k", 3)))
    if name == "check_completeness":
        return check_completeness(
            material_text=str(arguments.get("material_text", "")),
            file_names=list(arguments.get("file_names", [])),
        )
    if name == "industry_category_check":
        return industry_category_check(str(arguments.get("industry_category", "")))
    if name == "extract_key_entities":
        return extract_key_entities(str(arguments.get("material_text", "")))
    if name == "risk_summary":
        issues = arguments.get("issues", [])
        return risk_summary(issues if isinstance(issues, list) else [])
    if name == "kb_status":
        return kb_status()
    raise ValueError(f"unknown tool: {name}")


def _run_agent(material_text: str, rule_result: dict[str, Any]) -> dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {
            "mode": "deterministic_rule_agent",
            "analysis": "未配置 OPENAI_API_KEY，系统使用稳定规则 Agent 完成初审。",
            "decision": rule_result["decision"],
        }

    llm_kwargs = {
        "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        "temperature": 0,
        "api_key": api_key,
    }
    api_base = os.getenv("OPENAI_BASE_URL", "").strip()
    if api_base:
        llm_kwargs["base_url"] = api_base
    llm = ChatOpenAI(**llm_kwargs)

    tools = [
        Tool(
            name="knowledge_search",
            description="检索取水许可、材料完整性、合规审查相关知识库片段。",
            func=lambda q: json.dumps(knowledge_search(q, 4), ensure_ascii=False),
        ),
        Tool(
            name="check_completeness",
            description="检查申请材料是否缺少关键字段和必备附件。",
            func=lambda t: json.dumps(check_completeness(t), ensure_ascii=False),
        ),
        Tool(
            name="industry_category_check",
            description="检查行业类别是否符合国民经济行业分类中类格式。",
            func=lambda value: json.dumps(industry_category_check(value), ensure_ascii=False),
        ),
        Tool(
            name="risk_summary",
            description="按严重程度和问题类型汇总初审发现。",
            func=lambda _: json.dumps(risk_summary(rule_result.get("issues", [])), ensure_ascii=False),
        ),
    ]
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", "你是取水许可材料初审 Agent。必须先参考知识库和完整性检查结果，再给出稳定、可复核的结论。"),
            ("human", "规则引擎结果：{rule_result}\n\n申请材料文本：\n{input}"),
            ("placeholder", "{agent_scratchpad}"),
        ]
    )
    agent = create_tool_calling_agent(llm, tools, prompt)
    executor = AgentExecutor(agent=agent, tools=tools, verbose=False)
    try:
        result = executor.invoke({"input": material_text[:6000], "rule_result": json.dumps(rule_result, ensure_ascii=False)})
        return {"mode": "langchain_agent", "analysis": str(result.get("output", "")), "decision": rule_result["decision"]}
    except Exception as exc:
        return {
            "mode": "langchain_agent_error_fallback",
            "analysis": f"LangChain Agent 调用失败，已回退到稳定规则结果。错误信息：{exc}",
            "decision": rule_result["decision"],
        }


@app.on_event("startup")
def startup() -> None:
    build_knowledge_base(reset=False)


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "service": "python-ai-service", "chroma_dir": str(CHROMA_DIR), "knowledge_base": kb_status()}


@app.get("/kb/status")
def knowledge_base_status() -> dict[str, Any]:
    return kb_status()


@app.post("/kb/rebuild")
def rebuild_knowledge_base() -> dict[str, Any]:
    return build_knowledge_base(reset=True)


@app.post("/review")
def review(req: ReviewRequest) -> dict[str, Any]:
    paths = req.file_paths or ([req.file_path] if req.file_path else [])
    materials = load_materials(paths)
    if paths and not materials:
        raise HTTPException(status_code=404, detail="未找到可审查的附件")

    rule_result = deterministic_review(
        materials,
        {
            "applicant_name": req.applicant_name,
            "id_number": req.id_number,
            "project_name": req.project_name,
            "water_location": req.water_location,
            "water_use": req.water_use,
            "industry_category": req.industry_category,
            "contact_phone": req.contact_phone,
            "credit_code": req.credit_code,
        },
    )
    combined_text = "\n\n".join(item.text for item in materials)
    agent_result = _run_agent(combined_text, rule_result)
    return {
        "application_id": req.application_id,
        "applicant_name": req.applicant_name,
        "id_number": req.id_number,
        "ai_status": rule_result["decision"],
        "issues": rule_result["issues"],
        "suggestions": rule_result["suggestions"],
        "completeness": rule_result["completeness"],
        "content_check": rule_result["content_check"],
        "risk_summary": rule_result["risk_summary"],
        "knowledge_hits": rule_result["knowledge_hits"],
        "agent_result": agent_result,
        "raw_length": rule_result["raw_length"],
        "files": rule_result["files"],
    }


@app.get("/mcp/tools")
def mcp_tools() -> dict[str, Any]:
    return {
        "tools": [
            {"name": "knowledge_search", "description": "Search ChromaDB knowledge base"},
            {"name": "check_completeness", "description": "Check required fields and attachments"},
            {"name": "industry_category_check", "description": "Check GB/T 4754 industry category format"},
            {"name": "extract_key_entities", "description": "Extract names, ID numbers, credit codes, phones and dates"},
            {"name": "risk_summary", "description": "Summarize review issues by severity and type"},
            {"name": "kb_status", "description": "Return ChromaDB and knowledge document status"},
        ]
    }


@app.post("/mcp/call")
def mcp_call(req: ToolCallRequest) -> dict[str, Any]:
    try:
        return {"result": _run_tool(req.name, req.arguments)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
