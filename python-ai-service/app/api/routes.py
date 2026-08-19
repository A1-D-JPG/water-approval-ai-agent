from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.rag.service import guarded_search
from app.schemas import HealthResponse, RAGQueryRequest, RAGQueryResponse, ReviewRequest, ReviewResponse, ToolCallRequest, ToolCallResponse
from app.services import review_engine
from app.services.review_service import review_application
from app.services.tool_service import call_tool, list_tools

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    kb = review_engine.kb_status()
    status = "ok" if not kb.get("vector_error") else "degraded"
    return HealthResponse(status=status, service="python-ai-service", version="2.0.0", knowledge_base=kb)


@router.get("/kb/status", response_model=dict[str, Any], tags=["knowledge-base"])
def knowledge_base_status() -> dict[str, Any]:
    return review_engine.kb_status()


@router.post("/kb/rebuild", response_model=dict[str, Any], tags=["knowledge-base"])
def rebuild_knowledge_base() -> dict[str, Any]:
    return review_engine.build_knowledge_base(reset=True)


@router.post("/rag/query", response_model=RAGQueryResponse, tags=["rag"])
def rag_query(request: RAGQueryRequest) -> RAGQueryResponse:
    return RAGQueryResponse.model_validate(guarded_search(request.query, request.top_k))


@router.post("/review", response_model=ReviewResponse, tags=["review"])
def review(request: ReviewRequest) -> ReviewResponse:
    return review_application(request)


@router.get("/mcp/tools", response_model=dict[str, list[dict[str, str]]], tags=["mcp"])
def mcp_tools() -> dict[str, list[dict[str, str]]]:
    return {"tools": list_tools()}


@router.post("/mcp/call", response_model=ToolCallResponse, tags=["mcp"])
def mcp_call(request: ToolCallRequest) -> ToolCallResponse:
    return ToolCallResponse(result=call_tool(request.name, request.arguments))
