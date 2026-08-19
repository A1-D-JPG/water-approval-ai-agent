from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ToolCallRequest(BaseModel):
    name: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolCallResponse(BaseModel):
    result: dict[str, Any]


class RAGQueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    top_k: int = Field(default=3, ge=1, le=10)


class RAGQueryResponse(BaseModel):
    decision: Literal["ANSWERED", "REFUSED", "DEGRADED"]
    message: str
    retrieval_mode: str = "none"
    answer: str = ""
    answer_mode: str = "none"
    items: list[dict[str, Any]] = Field(default_factory=list)
    citations: list[dict[str, Any]] = Field(default_factory=list)
