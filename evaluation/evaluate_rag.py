from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python-ai-service"))

from ai_core import embeddings, knowledge_search  # noqa: E402


def load_cases(dataset_path: Path) -> list[dict[str, Any]]:
    """Load either a JSON array or a line-delimited JSON evaluation dataset."""
    raw = dataset_path.read_text(encoding="utf-8")
    if dataset_path.suffix.lower() == ".jsonl":
        cases = [json.loads(line) for line in raw.splitlines() if line.strip()]
    else:
        cases = json.loads(raw)

    if not isinstance(cases, list):
        raise ValueError("Evaluation dataset must contain a list of cases.")

    normalized: list[dict[str, Any]] = []
    required = {"id", "expected_sources"}
    for index, case in enumerate(cases, start=1):
        if not isinstance(case, dict):
            raise ValueError(f"Case {index} must be a JSON object.")
        missing = required - set(case)
        query = case.get("query") or case.get("question")
        if missing or not isinstance(query, str) or not query.strip():
            raise ValueError(
                f"Case {index} requires id, query/question and expected_sources."
            )
        if not isinstance(case["expected_sources"], list) or not case["expected_sources"]:
            raise ValueError(f"Case {case['id']} expected_sources must be a non-empty list.")
        normalized.append({**case, "query": query.strip()})
    return normalized


def percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(len(ordered) * ratio + 0.999999) - 1))
    return ordered[index]


def evaluate(dataset_path: Path, top_k: int) -> dict[str, Any]:
    cases = load_cases(dataset_path)
    details: list[dict[str, Any]] = []
    latencies: list[float] = []
    hit_at_1 = 0
    hit_at_k = 0
    reciprocal_rank_sum = 0.0
    keyword_recall_sum = 0.0

    for case in cases:
        started = time.perf_counter()
        result = knowledge_search(case["query"], top_k=top_k)
        elapsed_ms = (time.perf_counter() - started) * 1000
        latencies.append(elapsed_ms)

        expected_sources = set(case["expected_sources"])
        returned_sources = [item.get("source", "") for item in result["items"]]
        relevant_ranks = [
            index + 1 for index, source in enumerate(returned_sources) if source in expected_sources
        ]
        first_rank = min(relevant_ranks) if relevant_ranks else None
        hit_at_1 += int(first_rank == 1)
        hit_at_k += int(first_rank is not None)
        reciprocal_rank_sum += 1.0 / first_rank if first_rank else 0.0

        retrieved_text = "\n".join(item.get("content", "") for item in result["items"])
        keywords = case.get("expected_keywords", [])
        matched_keywords = [keyword for keyword in keywords if keyword.lower() in retrieved_text.lower()]
        keyword_recall = len(matched_keywords) / len(keywords) if keywords else 1.0
        keyword_recall_sum += keyword_recall
        details.append(
            {
                "id": case["id"],
                "query": case["query"],
                "retrieval_mode": result.get("retrieval_mode", "unknown"),
                "expected_sources": sorted(expected_sources),
                "returned_sources": returned_sources,
                "first_relevant_rank": first_rank,
                "source_hit": first_rank is not None,
                "matched_keywords": matched_keywords,
                "keyword_recall": round(keyword_recall, 4),
                "latency_ms": round(elapsed_ms, 2),
                "items": result["items"],
            }
        )

    total = len(cases)
    retrieval_modes = sorted({case["retrieval_mode"] for case in details})
    return {
        "evaluation": "rag_retrieval",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "dataset": str(dataset_path),
        "case_count": total,
        "top_k": top_k,
        "embedding_model": type(embeddings()).__name__,
        "retrieval_mode": ", ".join(retrieval_modes),
        "metrics": {
            "hit_at_1": round(hit_at_1 / total, 4) if total else 0.0,
            f"hit_at_{top_k}": round(hit_at_k / total, 4) if total else 0.0,
            "mrr": round(reciprocal_rank_sum / total, 4) if total else 0.0,
            "keyword_recall": round(keyword_recall_sum / total, 4) if total else 0.0,
            "latency_mean_ms": round(statistics.mean(latencies), 2) if latencies else 0.0,
            "latency_p95_ms": round(percentile(latencies, 0.95), 2),
        },
        "cases": details,
    }


def markdown_report(report: dict[str, Any]) -> str:
    metrics = report["metrics"]
    hit_k_name = f"hit_at_{report['top_k']}"
    lines = [
        "# RAG 检索评测报告",
        "",
        f"- 评测时间：{report['generated_at']}",
        f"- 查询数量：{report['case_count']}",
        f"- Embedding：{report['embedding_model']}",
        f"- 检索模式：{report['retrieval_mode']}",
        f"- Hit@1：{metrics['hit_at_1']:.2%}",
        f"- Hit@{report['top_k']}：{metrics[hit_k_name]:.2%}",
        f"- MRR：{metrics['mrr']:.4f}",
        f"- 关键词召回率：{metrics['keyword_recall']:.2%}",
        f"- 平均延迟：{metrics['latency_mean_ms']:.2f} ms",
        f"- P95 延迟：{metrics['latency_p95_ms']:.2f} ms",
        "",
        "| 用例 | 期望来源 | 返回来源 | 首个相关排名 | 关键词召回 | 延迟(ms) |",
        "|---|---|---|---:|---:|---:|",
    ]
    for case in report["cases"]:
        lines.append(
            f"| {case['id']} | {' / '.join(case['expected_sources'])} | "
            f"{' / '.join(case['returned_sources'])} | {case['first_relevant_rank'] or '-'} | "
            f"{case['keyword_recall']:.2%} | {case['latency_ms']:.2f} |"
        )
    lines.extend(
        [
            "",
            "> Hit@K 表示前 K 个结果是否至少包含一个人工标注的正确来源；MRR 同时考虑正确来源出现的位置。",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate RAG retrieval with a labeled dataset.")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=ROOT / "evaluation/datasets/retrieval_eval.jsonl",
        help="JSON array or JSONL dataset; defaults to the versioned JSONL regression set.",
    )
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "evaluation/results")
    args = parser.parse_args()

    report = evaluate(args.dataset, args.top_k)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "rag_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (args.output_dir / "rag_report.md").write_text(markdown_report(report), encoding="utf-8")
    print(markdown_report(report))


if __name__ == "__main__":
    main()
