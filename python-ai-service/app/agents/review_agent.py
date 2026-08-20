from __future__ import annotations

import json
import os
from collections.abc import Callable
from time import perf_counter
from typing import Any

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import Tool
from langchain_openai import ChatOpenAI

from app.schemas.review import AgentResult, AgentToolTrace
from app.services import review_engine

def _summarize_tool_result(
    tool_name: str,
    result: dict[str, Any],
) -> tuple[str, list[str]]:
    """生成不包含申请人原文的工具结果摘要。"""

    if tool_name == "knowledge_search":
        items = result.get("items", [])
        citations = result.get("citations", [])
        citation_ids = [
            str(item.get("citation_id"))
            for item in citations
            if item.get("citation_id")
        ][:10]
        return f"返回 {len(items)} 条知识片段", citation_ids

    if tool_name == "check_completeness":
        missing_fields = result.get("missing_fields", [])
        missing_attachments = result.get("missing_attachments", [])
        return (
            f"缺失字段 {len(missing_fields)} 个，"
            f"缺失附件 {len(missing_attachments)} 项",
            [],
        )

    if tool_name == "industry_category_check":
        passed = bool(result.get("valid"))
        return f"行业类别格式校验{'通过' if passed else '未通过'}", []

    if tool_name == "risk_summary":
        total = int(result.get("total", 0))
        high = int(result.get("by_severity", {}).get("高", 0))
        return f"汇总 {total} 个问题，其中高风险 {high} 个", []

    return "工具执行完成", []


def _build_traced_tool(
    *,
    name: str,
    description: str,
    handler: Callable[[str], dict[str, Any]],
    input_summary: str,
    trace: list[AgentToolTrace],
) -> Tool:
    """包装 LangChain Tool，记录耗时和脱敏摘要。"""

    def invoke(value: str) -> str:
        started = perf_counter()
        try:
            result = handler(value)
            output_summary, citation_ids = _summarize_tool_result(name, result)
            trace.append(
                AgentToolTrace(
                    tool_name=name,
                    status="SUCCESS",
                    input_summary=input_summary,
                    output_summary=output_summary,
                    latency_ms=round((perf_counter() - started) * 1000, 2),
                    citation_ids=citation_ids,
                )
            )
            return json.dumps(result, ensure_ascii=False)
        except Exception as exc:
            trace.append(
                AgentToolTrace(
                    tool_name=name,
                    status="ERROR",
                    input_summary=input_summary,
                    output_summary=f"工具调用失败：{type(exc).__name__}",
                    latency_ms=round((perf_counter() - started) * 1000, 2),
                    citation_ids=[],
                )
            )
            raise

    return Tool(name=name, description=description, func=invoke)


def _collect_baseline_evidence(tools: list[Tool]) -> dict[str, Any]:
    """Deterministically collect the minimum evidence required by every LLM review."""

    tools_by_name = {tool.name: tool for tool in tools}
    required_calls = [
        ("knowledge_search", "取水许可材料初审要求与补正依据"),
        ("risk_summary", "汇总规则问题"),
    ]
    evidence: dict[str, Any] = {}
    for tool_name, tool_input in required_calls:
        tool = tools_by_name[tool_name]
        try:
            evidence[tool_name] = json.loads(tool.run(tool_input))
        except Exception as exc:
            evidence[tool_name] = {
                "status": "ERROR",
                "error_type": type(exc).__name__,
            }
    return evidence


def run_review_agent(material_text: str, rule_result: dict[str, Any]) -> AgentResult:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return AgentResult(
            mode="deterministic_rule_agent",
            analysis="未配置大模型 API Key，系统已使用稳定规则完成初审。",
            decision=rule_result["decision"],
        )

    kwargs: dict[str, Any] = {
        "model": os.getenv("OPENAI_MODEL", "deepseek-chat"),
        "temperature": 0,
        "api_key": api_key,
        "timeout": float(os.getenv("LLM_TIMEOUT_SECONDS", "30")),
        "max_retries": 1,
    }
    if os.getenv("OPENAI_BASE_URL", "").strip():
        kwargs["base_url"] = os.getenv("OPENAI_BASE_URL", "").strip()

    llm = ChatOpenAI(**kwargs)
    tool_trace: list[AgentToolTrace] = []

    tools = [
        _build_traced_tool(
            name="knowledge_search",
            description="检索取水许可、材料完整性和合规审查相关知识片段。",
            handler=lambda query: review_engine.knowledge_search(query, 4),
            input_summary="涉水审批知识检索",
            trace=tool_trace,
        ),
        _build_traced_tool(
            name="check_completeness",
            description="检查申请材料是否缺少关键字段和必备附件。",
            handler=lambda text: review_engine.check_completeness(text),
            input_summary="申请材料完整性检查（原文未记录）",
            trace=tool_trace,
        ),
        _build_traced_tool(
            name="industry_category_check",
            description="检查行业类别是否符合国民经济行业分类中类格式。",
            handler=lambda value: review_engine.industry_category_check(value),
            input_summary="行业类别格式检查",
            trace=tool_trace,
        ),
        _build_traced_tool(
            name="risk_summary",
            description="按严重程度和问题类型汇总初审发现。",
            handler=lambda _: review_engine.risk_summary(
                rule_result.get("issues", [])
            ),
            input_summary="规则问题风险汇总",
            trace=tool_trace,
        ),
    ]
    baseline_evidence = _collect_baseline_evidence(tools)
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "你是取水许可材料初审 Agent。必须依据规则结果与工具证据回答；"
                "不得改变规则引擎结论；系统已预执行最低限度的法规检索与风险汇总，"
                "回答时必须使用这些证据；如证据仍不足，可以继续调用工具；"
                "缺少证据时明确建议人工复核。",
            ),
            (
                "human",
                "规则引擎结果：{rule_result}\n\n"
                "预执行工具证据：{baseline_evidence}\n\n"
                "申请材料文本：\n{input}",
            ),
            ("placeholder", "{agent_scratchpad}"),
        ]
    )
    executor = AgentExecutor(
        agent=create_tool_calling_agent(llm, tools, prompt),
        tools=tools,
        verbose=False,
        max_iterations=5,
        handle_parsing_errors=True,
    )
    try:
        output = executor.invoke(
            {
                "input": material_text[:6000],
                "rule_result": json.dumps(rule_result, ensure_ascii=False),
                "baseline_evidence": json.dumps(baseline_evidence, ensure_ascii=False),
            }
        )
        return AgentResult(
            mode="langchain_agent",
            analysis=str(output.get("output", "")),
            decision=rule_result["decision"],
            tool_trace=tool_trace,
        )
    except Exception as exc:
        return AgentResult(
            mode="langchain_agent_error_fallback",
            analysis=f"大模型调用失败，已回退到稳定规则结果：{exc}",
            decision=rule_result["decision"],
            tool_trace=tool_trace,
        )
