import json

import pytest
from pydantic import ValidationError

from app.agents.review_agent import (
    _build_traced_tool,
    _collect_baseline_evidence,
    run_review_agent,
)
from app.schemas.review import AgentResult, AgentToolTrace


def test_agent_fallback_output_matches_json_schema(monkeypatch):
    """未配置 API Key 时，规则 Agent 输出仍必须满足 JSON Schema。"""

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    rule_result = {
        "decision": "REJECTED",
    }

    result = run_review_agent(
        material_text="申请材料缺少身份证附件。",
        rule_result=rule_result,
    )

    # 模拟接口传输：Pydantic 对象 -> JSON -> Pydantic 对象。
    json_text = result.model_dump_json()
    validated = AgentResult.model_validate_json(json_text)

    assert validated.mode == "deterministic_rule_agent"
    assert validated.decision == "REJECTED"
    assert validated.analysis
    assert validated.tool_trace == []

    schema = AgentResult.model_json_schema()
    assert schema["additionalProperties"] is False
    assert set(schema["properties"]["decision"]["enum"]) == {
        "APPROVED",
        "REJECTED",
        "NEED_MANUAL_REVIEW",
    }


def test_agent_schema_rejects_invalid_decision():
    """不在枚举范围内的审核结论必须被拒绝。"""

    with pytest.raises(ValidationError):
        AgentResult.model_validate(
            {
                "mode": "langchain_agent",
                "analysis": "审核完成",
                "decision": "PASS",
            }
        )


def test_agent_schema_rejects_unknown_fields():
    """大模型输出额外字段时必须被拒绝，避免结构漂移。"""

    with pytest.raises(ValidationError):
        AgentResult.model_validate(
            {
                "mode": "langchain_agent",
                "analysis": "审核完成",
                "decision": "APPROVED",
                "confidence": 0.99,
            }
        )
def test_agent_tool_trace_accepts_safe_summary():
    """合法的工具轨迹应通过校验，且禁止额外字段。"""

    trace = AgentToolTrace(
        tool_name="knowledge_search",
        status="SUCCESS",
        input_summary="检索取水许可申请材料要求",
        output_summary="返回 3 条相关知识片段",
        latency_ms=12.5,
        citation_ids=["取水许可证申领表（2022）.docx#chunk-1"],
    )

    assert trace.tool_name == "knowledge_search"
    assert trace.status == "SUCCESS"
    assert trace.latency_ms == 12.5
    assert len(trace.citation_ids) == 1
    assert AgentToolTrace.model_json_schema()["additionalProperties"] is False


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("tool_name", "unknown_tool"),
        ("status", "UNKNOWN"),
        ("latency_ms", -1),
    ],
)
def test_agent_tool_trace_rejects_invalid_values(field, value):
    """未知工具、未知状态和负延迟都必须被拒绝。"""

    payload = {
        "tool_name": "knowledge_search",
        "status": "SUCCESS",
        "input_summary": "安全输入摘要",
        "output_summary": "安全输出摘要",
        "latency_ms": 10,
        "citation_ids": [],
    }
    payload[field] = value

    with pytest.raises(ValidationError):
        AgentToolTrace.model_validate(payload)


def test_agent_tool_trace_rejects_unknown_fields():
    """工具轨迹不允许模型任意增加字段。"""

    with pytest.raises(ValidationError):
        AgentToolTrace.model_validate(
            {
                "tool_name": "risk_summary",
                "status": "SUCCESS",
                "input_summary": "风险汇总",
                "output_summary": "发现 1 个高风险问题",
                "latency_ms": 5,
                "citation_ids": [],
                "raw_output": "不应暴露的完整工具输出",
            }
        )


def test_traced_tool_records_safe_success_summary():
    """成功调用只记录安全摘要、耗时和允许的引用编号。"""

    trace: list[AgentToolTrace] = []
    sensitive_input = "申请人测试用户甲，身份证号 TEST-ID-0001"
    tool = _build_traced_tool(
        name="knowledge_search",
        description="测试知识检索",
        handler=lambda _: {
            "items": [{"content": "证据一"}, {"content": "证据二"}],
            "citations": [
                {"citation_id": "取水许可证申领表（2022）.docx#chunk-1"}
            ],
        },
        input_summary="涉水审批知识检索",
        trace=trace,
    )

    result = json.loads(tool.run(sensitive_input))

    assert len(result["items"]) == 2
    assert len(trace) == 1
    assert trace[0].status == "SUCCESS"
    assert trace[0].output_summary == "返回 2 条知识片段"
    assert trace[0].latency_ms >= 0
    assert trace[0].citation_ids == [
        "取水许可证申领表（2022）.docx#chunk-1"
    ]
    assert sensitive_input not in trace[0].input_summary
    assert sensitive_input not in trace[0].output_summary


def test_traced_tool_records_sanitized_error_summary():
    """失败调用不得把输入原文或异常中的敏感内容写入轨迹。"""

    trace: list[AgentToolTrace] = []
    sensitive_input = "申请人测试用户甲，手机号 TEST-PHONE-0001"

    def failing_handler(_: str) -> dict:
        raise RuntimeError("TEST-PHONE-0001 调用失败")

    tool = _build_traced_tool(
        name="check_completeness",
        description="测试完整性检查",
        handler=failing_handler,
        input_summary="申请材料完整性检查（原文未记录）",
        trace=trace,
    )

    with pytest.raises(RuntimeError):
        tool.run(sensitive_input)

    assert len(trace) == 1
    assert trace[0].status == "ERROR"
    assert trace[0].output_summary == "工具调用失败：RuntimeError"
    assert trace[0].latency_ms >= 0
    assert trace[0].citation_ids == []
    assert sensitive_input not in trace[0].input_summary
    assert "TEST-PHONE-0001" not in trace[0].output_summary


def test_baseline_evidence_always_runs_search_and_risk_summary():
    """LLM 审核前必须确定性执行法规检索和风险汇总。"""

    trace: list[AgentToolTrace] = []
    knowledge_tool = _build_traced_tool(
        name="knowledge_search",
        description="测试知识检索",
        handler=lambda _: {
            "items": [{"content": "证据"}],
            "citations": [{"citation_id": "规则.docx#chunk-1"}],
        },
        input_summary="涉水审批知识检索",
        trace=trace,
    )
    risk_tool = _build_traced_tool(
        name="risk_summary",
        description="测试风险汇总",
        handler=lambda _: {
            "total": 2,
            "by_severity": {"高": 1, "中": 1, "低": 0},
        },
        input_summary="规则问题风险汇总",
        trace=trace,
    )

    evidence = _collect_baseline_evidence([knowledge_tool, risk_tool])

    assert set(evidence) == {"knowledge_search", "risk_summary"}
    assert [item.tool_name for item in trace] == [
        "knowledge_search",
        "risk_summary",
    ]
    assert all(item.status == "SUCCESS" for item in trace)
    assert trace[0].citation_ids == ["规则.docx#chunk-1"]
