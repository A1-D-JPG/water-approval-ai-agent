from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ReviewRequest(BaseModel):
    application_id: int = Field(gt=0)
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


class ReviewIssue(BaseModel):
    type: str
    severity: Literal["高", "中", "低"]
    message: str
    location: str
    legal_basis: str
    suggestion: str

class AgentToolTrace(BaseModel):
    """Agent 单次工具调用的安全摘要，不保存原始材料。"""

    model_config = ConfigDict(extra="forbid")

    tool_name: Literal[
        "knowledge_search",
        "check_completeness",
        "industry_category_check",
        "risk_summary",
    ]
    status: Literal["SUCCESS", "ERROR"]
    input_summary: str = Field(default="", max_length=200)
    output_summary: str = Field(default="", max_length=500)
    latency_ms: float = Field(ge=0)
    citation_ids: list[str] = Field(default_factory=list, max_length=10)


class AgentResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal[
        "langchain_agent",
        "langchain_agent_error_fallback",
        "deterministic_rule_agent",
    ]
    analysis: str
    decision: Literal["APPROVED", "REJECTED", "NEED_MANUAL_REVIEW"]
    tool_trace: list[AgentToolTrace] = Field(default_factory=list, max_length=10)


class ReviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    application_id: int
    applicant_name: str
    id_number: str
    ai_status: Literal["APPROVED", "REJECTED", "NEED_MANUAL_REVIEW"]
    issues: list[ReviewIssue]
    suggestions: list[str]
    completeness: dict[str, Any]
    content_check: dict[str, Any]
    risk_summary: dict[str, Any]
    knowledge_hits: list[dict[str, Any]]
    agent_result: AgentResult
    raw_length: int = Field(ge=0)
    files: list[dict[str, Any]]
