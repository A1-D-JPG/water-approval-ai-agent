from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python-ai-service"))

from app.schemas.review import ReviewRequest  # noqa: E402
from app.services import review_engine  # noqa: E402
from app.services.review_service import review_application  # noqa: E402
from evaluate_agent import SUPPORTED_SUFFIXES, application_for_case  # noqa: E402

CITATION_PATTERN = re.compile(r"^.+#chunk-\d+$")


def load_cases(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def safe_ratio(numerator: int | float, denominator: int | float) -> float:
    return numerator / denominator if denominator else 0.0


def percentile(values: list[float], ratio: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = max(0, min(len(ordered) - 1, int(len(ordered) * ratio + 0.999999) - 1))
    return ordered[index]


def find_case_folder(cases_root: Path, prefix: str) -> Path:
    folder = next(
        (
            path
            for path in cases_root.iterdir()
            if path.is_dir() and path.name.startswith(prefix)
        ),
        None,
    )
    if folder is None:
        raise FileNotFoundError(f"No test case folder starts with {prefix}")
    return folder


def citation_is_valid(citation_id: str, knowledge_files: set[str]) -> bool:
    if not CITATION_PATTERN.fullmatch(citation_id):
        return False
    source = citation_id.rsplit("#chunk-", 1)[0]
    return source in knowledge_files


def evaluate(
    dataset: Path,
    cases_root: Path,
    case_ids: set[str] | None = None,
) -> dict[str, Any]:
    cases = load_cases(dataset)
    if case_ids:
        cases = [case for case in cases if case["id"] in case_ids]
        missing = case_ids - {case["id"] for case in cases}
        if missing:
            raise ValueError(f"Unknown case ids: {', '.join(sorted(missing))}")

    knowledge_files = set(review_engine.kb_status().get("knowledge_files", []))
    details: list[dict[str, Any]] = []
    latencies: list[float] = []
    tool_latencies: list[float] = []
    successful_tool_calls = 0
    total_tool_calls = 0

    for index, case in enumerate(cases, start=1):
        folder = find_case_folder(cases_root, case["folder_prefix"])
        file_paths = [
            str(path)
            for path in folder.iterdir()
            if path.suffix.lower() in SUPPORTED_SUFFIXES
        ]
        application = application_for_case(case["folder_prefix"])
        request = ReviewRequest(
            application_id=9000 + index,
            file_paths=file_paths,
            **application,
        )

        started = time.perf_counter()
        response = review_application(request)
        latency_ms = (time.perf_counter() - started) * 1000
        latencies.append(latency_ms)

        agent = response.agent_result
        trace = agent.tool_trace
        tool_names = [item.tool_name for item in trace]
        required_tools = set(case.get("required_tools", []))
        required_tools_covered = required_tools.issubset(set(tool_names))
        successful_calls = sum(item.status == "SUCCESS" for item in trace)
        successful_tool_calls += successful_calls
        total_tool_calls += len(trace)
        tool_latencies.extend(item.latency_ms for item in trace)

        citation_ids = [
            citation_id
            for item in trace
            for citation_id in item.citation_ids
        ]
        min_citations = int(case.get("min_citations", 0))
        citations_valid = (
            len(citation_ids) >= min_citations
            and all(citation_is_valid(item, knowledge_files) for item in citation_ids)
        )

        trace_text = json.dumps(
            [item.model_dump() for item in trace],
            ensure_ascii=False,
        )
        sensitive_values = [
            application.get("applicant_name", ""),
            application.get("id_number", ""),
            application.get("contact_phone", ""),
            application.get("credit_code", ""),
        ]
        trace_privacy_passed = not any(
            value and value in trace_text for value in sensitive_values
        )

        rule_decision_correct = response.ai_status == case["expected_decision"]
        agent_decision_consistent = agent.decision == response.ai_status
        llm_completed = agent.mode == "langchain_agent"
        all_tools_succeeded = bool(trace) and successful_calls == len(trace)
        passed = all(
            [
                rule_decision_correct,
                agent_decision_consistent,
                llm_completed,
                required_tools_covered,
                all_tools_succeeded,
                citations_valid,
                trace_privacy_passed,
            ]
        )

        details.append(
            {
                "id": case["id"],
                "expected_decision": case["expected_decision"],
                "rule_decision": response.ai_status,
                "agent_decision": agent.decision,
                "agent_mode": agent.mode,
                "tool_names": tool_names,
                "required_tools_covered": required_tools_covered,
                "tool_call_count": len(trace),
                "successful_tool_call_count": successful_calls,
                "citation_ids": citation_ids,
                "citations_valid": citations_valid,
                "trace_privacy_passed": trace_privacy_passed,
                "latency_ms": round(latency_ms, 2),
                "passed": passed,
            }
        )

    total = len(details)
    llm_count = sum(item["agent_mode"] == "langchain_agent" for item in details)
    fallback_count = total - llm_count
    return {
        "evaluation": "llm_agent_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "dataset": str(dataset),
        "case_count": total,
        "privacy_note": "报告不保存申请字段、材料全文或 Agent 分析原文。",
        "metrics": {
            "pass_rate": round(safe_ratio(sum(item["passed"] for item in details), total), 4),
            "rule_decision_accuracy": round(
                safe_ratio(
                    sum(item["rule_decision"] == item["expected_decision"] for item in details),
                    total,
                ),
                4,
            ),
            "agent_decision_consistency": round(
                safe_ratio(
                    sum(item["agent_decision"] == item["rule_decision"] for item in details),
                    total,
                ),
                4,
            ),
            "required_tool_coverage_rate": round(
                safe_ratio(sum(item["required_tools_covered"] for item in details), total),
                4,
            ),
            "tool_success_rate": round(
                safe_ratio(successful_tool_calls, total_tool_calls),
                4,
            ),
            "citation_valid_rate": round(
                safe_ratio(sum(item["citations_valid"] for item in details), total),
                4,
            ),
            "trace_privacy_rate": round(
                safe_ratio(sum(item["trace_privacy_passed"] for item in details), total),
                4,
            ),
            "llm_completion_rate": round(safe_ratio(llm_count, total), 4),
            "fallback_rate": round(safe_ratio(fallback_count, total), 4),
            "latency_mean_ms": round(statistics.mean(latencies), 2) if latencies else 0.0,
            "latency_p95_ms": round(percentile(latencies, 0.95), 2),
            "tool_latency_mean_ms": round(statistics.mean(tool_latencies), 2)
            if tool_latencies
            else 0.0,
        },
        "cases": details,
    }


def markdown_report(report: dict[str, Any]) -> str:
    metrics = report["metrics"]
    lines = [
        "# LLM Agent 审核评测报告",
        "",
        f"- 评测时间：{report['generated_at']}",
        f"- 用例数量：{report['case_count']}",
        f"- 综合通过率：{metrics['pass_rate']:.2%}",
        f"- 规则结论准确率：{metrics['rule_decision_accuracy']:.2%}",
        f"- Agent 结论一致率：{metrics['agent_decision_consistency']:.2%}",
        f"- 必需工具覆盖率：{metrics['required_tool_coverage_rate']:.2%}",
        f"- 工具调用成功率：{metrics['tool_success_rate']:.2%}",
        f"- 引用有效率：{metrics['citation_valid_rate']:.2%}",
        f"- 轨迹脱敏通过率：{metrics['trace_privacy_rate']:.2%}",
        f"- LLM 完成率：{metrics['llm_completion_rate']:.2%}",
        f"- 降级率：{metrics['fallback_rate']:.2%}",
        f"- 平均端到端延迟：{metrics['latency_mean_ms']:.2f} ms",
        f"- P95 端到端延迟：{metrics['latency_p95_ms']:.2f} ms",
        f"- 平均工具调用延迟：{metrics['tool_latency_mean_ms']:.2f} ms",
        "",
        "| 用例 | 期望/规则/Agent 结论 | 模式 | 工具 | 引用有效 | 轨迹脱敏 | 延迟(ms) | 结果 |",
        "|---|---|---|---|---:|---:|---:|---|",
    ]
    for case in report["cases"]:
        decisions = "/".join(
            [case["expected_decision"], case["rule_decision"], case["agent_decision"]]
        )
        lines.append(
            f"| {case['id']} | {decisions} | {case['agent_mode']} | "
            f"{' / '.join(case['tool_names']) or '-'} | "
            f"{'是' if case['citations_valid'] else '否'} | "
            f"{'是' if case['trace_privacy_passed'] else '否'} | "
            f"{case['latency_ms']:.2f} | {'PASS' if case['passed'] else 'FAIL'} |"
        )
    lines.extend(
        [
            "",
            "> 本报告不保存申请字段、材料全文或 Agent 分析原文。指标来自本地小规模回归集，不代表生产环境总体效果。",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate real LLM Agent decisions, tool traces, citations and privacy."
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=ROOT / "evaluation/datasets/agent_llm_eval.jsonl",
    )
    parser.add_argument(
        "--cases-root",
        type=Path,
        default=ROOT / "测试用例_真实格式",
    )
    parser.add_argument(
        "--case-id",
        action="append",
        dest="case_ids",
        help="Run only the selected case id; may be supplied more than once.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "evaluation/results/agent-llm-01",
    )
    args = parser.parse_args()

    report = evaluate(args.dataset, args.cases_root, set(args.case_ids or []))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "agent_llm_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    markdown = markdown_report(report)
    (args.output_dir / "agent_llm_report.md").write_text(markdown, encoding="utf-8")
    print(markdown)


if __name__ == "__main__":
    main()
