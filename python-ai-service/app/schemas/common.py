from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    code: str = Field(examples=["VALIDATION_ERROR"])
    message: str
    request_id: str
    details: Any | None = None


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    service: str
    version: str
    knowledge_base: dict[str, Any]
