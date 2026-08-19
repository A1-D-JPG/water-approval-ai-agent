import pytest
from pydantic import ValidationError

from app.agents.review_agent import run_review_agent
from app.schemas.review import AgentResult


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