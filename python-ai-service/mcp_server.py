from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from app.services.review_engine import (
    check_completeness,
    extract_key_entities,
    industry_category_check,
    kb_status,
    knowledge_search,
    risk_summary,
)

mcp = FastMCP("water-approval-mcp")


@mcp.tool(name="knowledge_search")
def knowledge_search_tool(query: str, top_k: int = 3) -> dict:
    """Search the water-approval knowledge base and return content, source and score."""
    return knowledge_search(query=query, top_k=top_k)


@mcp.tool(name="check_completeness")
def check_completeness_tool(material_text: str, file_names: list[str] | None = None) -> dict:
    """Check whether materials miss required fields or attachments."""
    return check_completeness(material_text=material_text, file_names=file_names or [])


@mcp.tool(name="industry_category_check")
def industry_category_check_tool(industry_category: str) -> dict:
    """Validate a GB/T 4754 industry category value."""
    return industry_category_check(industry_category=industry_category)


@mcp.tool(name="extract_key_entities")
def extract_key_entities_tool(material_text: str) -> dict:
    """Extract key entities from material text."""
    return extract_key_entities(material_text=material_text)


@mcp.tool(name="risk_summary")
def risk_summary_tool(issues: list[dict] | None = None) -> dict:
    """Summarize review issues by severity and type."""
    return risk_summary(issues=issues or [])


@mcp.tool(name="kb_status")
def kb_status_tool() -> dict:
    """Return ChromaDB and knowledge document status."""
    return kb_status()


if __name__ == "__main__":
    mcp.run(transport="stdio")
