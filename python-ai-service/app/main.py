from __future__ import annotations

import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.config import env_flag, load_env_file
from app.errors import AppError
from app.services import review_engine

load_env_file()
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper(), format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("water_approval_ai")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    if not env_flag("SKIP_KB_STARTUP", False):
        try:
            result = review_engine.build_knowledge_base(reset=False)
            logger.info("knowledge_base_ready files=%s chunks=%s", result["files"], result["chunks"])
        except Exception:
            logger.exception("knowledge_base_startup_failed")
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Water Approval AI Service",
        version="2.0.0",
        description="RAG、规则引擎与 LangChain Agent 驱动的涉水审批材料初审服务。",
        lifespan=lifespan,
    )
    app.include_router(router)

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("X-Request-Id", str(uuid.uuid4()))
        request.state.request_id = request_id
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        logger.info(
            "request_complete request_id=%s method=%s path=%s status=%s elapsed_ms=%.2f",
            request_id, request.method, request.url.path, response.status_code,
            (time.perf_counter() - started) * 1000,
        )
        return response

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        logger.warning("app_error request_id=%s code=%s message=%s", _request_id(request), exc.code, exc.message)
        return JSONResponse(status_code=exc.status_code, content={
            "code": exc.code, "message": exc.message, "request_id": _request_id(request), "details": exc.details,
        })

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={
            "code": "VALIDATION_ERROR", "message": "请求参数校验失败。",
            "request_id": _request_id(request), "details": exc.errors(),
        })

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unexpected_error request_id=%s", _request_id(request))
        return JSONResponse(status_code=500, content={
            "code": "INTERNAL_ERROR", "message": "服务内部错误，请携带 request_id 联系管理员。",
            "request_id": _request_id(request), "details": None,
        })

    return app


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


app = create_app()
