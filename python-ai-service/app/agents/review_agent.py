from __future__ import annotations

import json
import os
from typing import Any

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import Tool
from langchain_openai import ChatOpenAI

from app.schemas.review import AgentResult
from app.services import review_engine


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
    tools = [
        Tool(
            name="knowledge_search",
            description="检索取水许可、材料完整性和合规审查相关知识片段。",
            func=lambda query: json.dumps(review_engine.knowledge_search(query, 4), ensure_ascii=False),
        ),
        Tool(
            name="check_completeness",
            description="检查申请材料是否缺少关键字段和必备附件。",
            func=lambda text: json.dumps(review_engine.check_completeness(text), ensure_ascii=False),
        ),
        Tool(
            name="industry_category_check",
            description="检查行业类别是否符合国民经济行业分类中类格式。",
            func=lambda value: json.dumps(review_engine.industry_category_check(value), ensure_ascii=False),
        ),
        Tool(
            name="risk_summary",
            description="按严重程度和问题类型汇总初审发现。",
            func=lambda _: json.dumps(review_engine.risk_summary(rule_result.get("issues", [])), ensure_ascii=False),
        ),
    ]
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "你是取水许可材料初审 Agent。必须依据规则结果与工具证据回答；"
                "不得改变规则引擎结论；缺少证据时明确建议人工复核。",
            ),
            ("human", "规则引擎结果：{rule_result}\n\n申请材料文本：\n{input}"),
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
            }
        )
        return AgentResult(
            mode="langchain_agent",
            analysis=str(output.get("output", "")),
            decision=rule_result["decision"],
        )
    except Exception as exc:
        return AgentResult(
            mode="langchain_agent_error_fallback",
            analysis=f"大模型调用失败，已回退到稳定规则结果：{exc}",
            decision=rule_result["decision"],
        )
