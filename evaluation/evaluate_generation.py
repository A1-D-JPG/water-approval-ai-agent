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

from app.rag.service import guarded_search  # noqa: E402


def load_cases(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def percentile(values: list[float], ratio: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = max(0, min(len(ordered) - 1, int(len(ordered) * ratio + 0.999999) - 1))
    return ordered[index]


def cited_ids(answer: str) -> set[str]:
    return set(re.findall(r"\[([^\[\]]+#chunk-\d+)\]", answer))


def evaluate(dataset: Path, top_k: int, case_ids: set[str] | None = None) -> dict[str, Any]:
    cases = load_cases(dataset)
    if case_ids:
        cases = [case for case in cases if case["id"] in case_ids]
        missing = case_ids - {case["id"] for case in cases}
        if missing:
            raise ValueError(f"Unknown case ids: {', '.join(sorted(missing))}")
    details: list[dict[str, Any]] = []
    latencies: list[float] = []

    for case in cases:
        started = time.perf_counter()
        result = guarded_search(case["query"], top_k=top_k)
        latency_ms = (time.perf_counter() - started) * 1000
        latencies.append(latency_ms)

        answer = result.get("answer", "")
        citations = cited_ids(answer)
        allowed = {item.get("citation_id", "") for item in result.get("citations", [])}
        expected_sources = set(case["expected_sources"])
        cited_sources = {citation.rsplit("#chunk-", 1)[0] for citation in citations}
        keywords = case.get("expected_keywords", [])
        matched_keywords = [keyword for keyword in keywords if keyword.lower() in answer.lower()]
        keyword_recall = len(matched_keywords) / len(keywords) if keywords else 1.0
        citation_valid = bool(citations) and citations.issubset(allowed)
        expected_source_cited = bool(cited_sources & expected_sources)
        passed = bool(answer) and citation_valid and expected_source_cited and keyword_recall >= 0.5

        details.append(
            {
                "id": case["id"],
                "query": case["query"],
                "answer_mode": result.get("answer_mode", "none"),
                "citation_valid": citation_valid,
                "expected_source_cited": expected_source_cited,
                "cited_sources": sorted(cited_sources),
                "matched_keywords": matched_keywords,
                "keyword_recall": round(keyword_recall, 4),
                "latency_ms": round(latency_ms, 2),
                "passed": passed,
                "answer": answer,
            }
        )

    total = len(details)
    llm_count = sum(item["answer_mode"] == "llm_grounded" for item in details)
    fallback_count = sum(item["answer_mode"] == "extractive_grounded_fallback" for item in details)
    return {
        "evaluation": "rag_generation",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "dataset": str(dataset),
        "case_count": total,
        "metrics": {
            "pass_rate": round(sum(item["passed"] for item in details) / total, 4) if total else 0.0,
            "citation_valid_rate": round(sum(item["citation_valid"] for item in details) / total, 4) if total else 0.0,
            "expected_source_citation_rate": round(sum(item["expected_source_cited"] for item in details) / total, 4) if total else 0.0,
            "keyword_recall": round(statistics.mean(item["keyword_recall"] for item in details), 4) if total else 0.0,
            "llm_generation_rate": round(llm_count / total, 4) if total else 0.0,
            "fallback_rate": round(fallback_count / total, 4) if total else 0.0,
            "latency_mean_ms": round(statistics.mean(latencies), 2) if total else 0.0,
            "latency_p95_ms": round(percentile(latencies, 0.95), 2),
        },
        "cases": details,
    }


def markdown_report(report: dict[str, Any]) -> str:
    metrics = report["metrics"]
    lines = [
        "# RAG 生成评测报告",
        "",
        f"- 评测时间：{report['generated_at']}",
        f"- 用例数量：{report['case_count']}",
        f"- 综合通过率：{metrics['pass_rate']:.2%}",
        f"- 引用格式有效率：{metrics['citation_valid_rate']:.2%}",
        f"- 期望来源引用率：{metrics['expected_source_citation_rate']:.2%}",
        f"- 答案关键词召回率：{metrics['keyword_recall']:.2%}",
        f"- LLM 生成率：{metrics['llm_generation_rate']:.2%}",
        f"- 降级率：{metrics['fallback_rate']:.2%}",
        f"- 平均延迟：{metrics['latency_mean_ms']:.2f} ms",
        f"- P95 延迟：{metrics['latency_p95_ms']:.2f} ms",
        "",
        "| 用例 | 模式 | 引用有效 | 引用期望来源 | 关键词召回 | 延迟(ms) | 结果 |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for case in report["cases"]:
        lines.append(
            f"| {case['id']} | {case['answer_mode']} | "
            f"{'是' if case['citation_valid'] else '否'} | "
            f"{'是' if case['expected_source_cited'] else '否'} | "
            f"{case['keyword_recall']:.2%} | {case['latency_ms']:.2f} | "
            f"{'PASS' if case['passed'] else 'FAIL'} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate grounded RAG generation and citations.")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=ROOT / "evaluation/datasets/generation_eval.jsonl",
    )
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument(
        "--case-id",
        action="append",
        dest="case_ids",
        help="Run only the selected case id; may be supplied more than once.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "evaluation/results/generation-01",
    )
    args = parser.parse_args()

    report = evaluate(args.dataset, args.top_k, set(args.case_ids or []))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "generation_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    markdown = markdown_report(report)
    (args.output_dir / "generation_report.md").write_text(markdown, encoding="utf-8")
    print(markdown)


if __name__ == "__main__":
    main()
