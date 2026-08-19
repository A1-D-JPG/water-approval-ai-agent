from __future__ import annotations

from typing import Any, Callable

from app.errors import AppError
from app.services import review_engine


def _completeness(arguments: dict[str, Any]) -> dict[str, Any]:
    return review_engine.check_completeness(
        material_text=str(arguments.get("material_text", "")),
        file_names=list(arguments.get("file_names", [])),
    )


TOOLS: dict[str, tuple[str, Callable[[dict[str, Any]], dict[str, Any]]]] = {
    "knowledge_search": (
        "检索 ChromaDB 知识库并返回内容、来源和距离分数",
        lambda args: review_engine.knowledge_search(str(args.get("query", "")), int(args.get("top_k", 3))),
    ),
    "check_completeness": ("检查必填字段和附件", _completeness),
    "industry_category_check": (
        "检查国民经济行业分类中类格式",
        lambda args: review_engine.industry_category_check(str(args.get("industry_category", ""))),
    ),
    "extract_key_entities": (
        "抽取材料中的关键实体",
        lambda args: review_engine.extract_key_entities(str(args.get("material_text", ""))),
    ),
    "risk_summary": (
        "按严重程度和类型汇总问题",
        lambda args: review_engine.risk_summary(args.get("issues", [])),
    ),
    "kb_status": ("返回知识库运行状态", lambda _: review_engine.kb_status()),
}


def list_tools() -> list[dict[str, str]]:
    return [{"name": name, "description": item[0]} for name, item in TOOLS.items()]


def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    item = TOOLS.get(name)
    if item is None:
        raise AppError("TOOL_NOT_FOUND", f"工具不存在：{name}", 404)
    try:
        return item[1](arguments)
    except AppError:
        raise
    except Exception as exc:
        raise AppError(
            "TOOL_EXECUTION_FAILED",
            f"工具 {name} 执行失败，请检查输入参数或依赖服务。",
            422,
            str(exc),
        ) from exc
