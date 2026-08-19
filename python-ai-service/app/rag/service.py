from __future__ import annotations

import logging
import os
import re

from langchain_openai import ChatOpenAI

from app.config import env_flag
from app.errors import AppError
from app.services import review_engine

logger = logging.getLogger(__name__)

DOMAIN_TERMS = {
    "取水", "水资源", "审批", "申请材料", "身份证", "营业执照", "行业类别",
    "行业分类", "国民经济", "行业代码", "水法", "河道", "许可证", "水源",
    "论证报告", "用水", "法规", "完整性",
}


def search_knowledge(query: str, top_k: int = 3) -> dict:
    try:
        return review_engine.knowledge_search(query=query, top_k=top_k)
    except Exception as exc:
        raise AppError(
            "RAG_SEARCH_FAILED",
            "知识库检索失败，请检查向量库是否已构建。",
            status_code=503,
            details=str(exc),
        ) from exc


def _extractive_grounded_answer(items: list[dict]) -> str:
    """Create a deterministic answer from the highest-ranked evidence chunk."""
    if not items:
        return ""
    primary = items[0]
    content = str(primary.get("content", "")).strip()
    marker = re.search(r"(?:^|\n)(?:填表说明|说明)(?:\n|$)", content)
    if marker and content[marker.end():].strip():
        content = content[marker.end():].strip()
    citation_id = str(primary.get("citation_id") or primary.get("source") or "知识库证据")
    return f"{content}\n\n依据：[{citation_id}]" if content else ""


def _generate_grounded_answer(query: str, items: list[dict]) -> tuple[str, str]:
    fallback = _extractive_grounded_answer(items)
    if not fallback:
        return "", "none"
    if not env_flag("RAG_LLM_GENERATION_ENABLED", False):
        return fallback, "extractive_grounded"

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return fallback, "extractive_grounded_fallback"

    allowed_citations = {str(item.get("citation_id", "")) for item in items}
    allowed_citation_text = "、".join(f"[{citation}]" for citation in sorted(allowed_citations))
    evidence = "\n\n".join(
        f"[{item.get('citation_id')}]\n{item.get('content', '')}"
        for item in items
    )
    try:
        kwargs = {
            "model": os.getenv("OPENAI_MODEL", "deepseek-chat"),
            "temperature": 0,
            "api_key": api_key,
            "timeout": float(os.getenv("LLM_TIMEOUT_SECONDS", "30")),
            "max_retries": 1,
        }
        if os.getenv("OPENAI_BASE_URL", "").strip():
            kwargs["base_url"] = os.getenv("OPENAI_BASE_URL", "").strip()
        llm = ChatOpenAI(**kwargs)
        response = llm.invoke(
            [
                (
                    "system",
                    "你是涉水审批知识助手。只能依据用户提供的证据回答，不得使用证据外信息。"
                    "答案应直接、简洁；每个关键结论后必须使用原样引用编号。"
                    f"本次回答只允许使用以下引用编号：{allowed_citation_text}。"
                    "不得缩写、改写或自行创造引用编号。"
                    "如果证据不足，明确回答证据不足并建议人工复核。",
                ),
                ("human", f"问题：{query}\n\n证据：\n{evidence}"),
            ]
        )
        answer = str(response.content).strip()
        cited = set(re.findall(r"\[([^\[\]]+#chunk-\d+)\]", answer))
        if not answer or not cited or not cited.issubset(allowed_citations):
            logger.warning("rag_generation_invalid_citations cited=%s allowed=%s", cited, allowed_citations)
            return fallback, "extractive_grounded_fallback"
        return answer, "llm_grounded"
    except Exception:
        logger.exception("rag_generation_failed")
        return fallback, "extractive_grounded_fallback"


def guarded_search(query: str, top_k: int = 3) -> dict:
    normalized = query.strip().lower()
    if not any(term.lower() in normalized for term in DOMAIN_TERMS):
        return {
            "decision": "REFUSED",
            "message": "该问题与涉水审批材料审核无关，系统仅回答取水许可、材料完整性和相关法规问题。",
            "retrieval_mode": "none",
            "answer": "",
            "answer_mode": "none",
            "items": [],
            "citations": [],
        }
    result = search_knowledge(query, top_k)
    items = result.get("items", [])
    answer, answer_mode = _generate_grounded_answer(query, items)
    return {
        "decision": "ANSWERED" if items else "DEGRADED",
        "message": "已返回相关知识片段。" if items else "知识库中未检索到可靠依据，建议人工复核。",
        "retrieval_mode": result.get("retrieval_mode", "unknown"),
        "answer": answer,
        "answer_mode": answer_mode,
        "items": items,
        "citations": result.get("citations", []),
    }
