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

from ai_core import deterministic_review, load_materials  # noqa: E402

SUPPORTED_SUFFIXES = {".docx", ".doc", ".pdf", ".png", ".jpg", ".jpeg"}


def application_for_case(prefix: str) -> dict[str, str]:
    application = {
        "applicant_name": "王世杰",
        "id_number": "110101199003070013",
        "project_name": "农业灌溉取水项目",
        "water_location": "浙江省杭州市钱塘区",
        "water_use": "农业灌溉用水",
        "industry_category": "011谷物种植",
        "contact_phone": "13812345678",
    }
    if prefix == "06":
        application.update({"project_name": "", "water_location": "", "contact_phone": ""})
    if prefix == "07":
        application["water_use"] = "其他"
    if prefix == "09":
        application.update(
            {"project_name": "", "water_location": "", "contact_phone": "", "water_use": "其他"}
        )
    return application


def issue_fingerprint(result: dict[str, Any]) -> tuple[Any, ...]:
    issues = sorted(
        (item.get("type", ""), item.get("severity", ""), item.get("location", ""), item.get("message", ""))
        for item in result.get("issues", [])
    )
    return result.get("decision"), tuple(issues)


def safe_ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def evaluate(dataset_path: Path, cases_root: Path, repeats: int) -> dict[str, Any]:
    labels = json.loads(dataset_path.read_text(encoding="utf-8"))
    folders = [path for path in cases_root.iterdir() if path.is_dir()]
    details: list[dict[str, Any]] = []
    decision_correct = 0
    exact_issue_set_correct = 0
    stable_cases = 0
    true_positive = false_positive = false_negative = 0
    all_latencies: list[float] = []

    for label in labels:
        prefix = label["folder_prefix"]
        folder = next((path for path in folders if path.name.startswith(prefix)), None)
        if folder is None:
            raise FileNotFoundError(f"No test case folder starts with {prefix}")
        file_paths = [str(path) for path in folder.iterdir() if path.suffix.lower() in SUPPORTED_SUFFIXES]
        materials = load_materials(file_paths)
        results: list[dict[str, Any]] = []
        latencies: list[float] = []
        for _ in range(repeats):
            started = time.perf_counter()
            result = deterministic_review(materials, application_for_case(prefix))
            latencies.append((time.perf_counter() - started) * 1000)
            results.append(result)
        all_latencies.extend(latencies)

        first = results[0]
        actual_types = {item.get("type", "") for item in first.get("issues", [])}
        expected_types = set(label["expected_issue_types"])
        decision_match = first["decision"] == label["expected_decision"]
        issue_set_match = actual_types == expected_types
        stable = len({issue_fingerprint(result) for result in results}) == 1
        decision_correct += int(decision_match)
        exact_issue_set_correct += int(issue_set_match)
        stable_cases += int(stable)
        true_positive += len(actual_types & expected_types)
        false_positive += len(actual_types - expected_types)
        false_negative += len(expected_types - actual_types)

        details.append(
            {
                "case": folder.name,
                "expected_decision": label["expected_decision"],
                "actual_decision": first["decision"],
                "decision_match": decision_match,
                "expected_issue_types": sorted(expected_types),
                "actual_issue_types": sorted(actual_types),
                "issue_set_match": issue_set_match,
                "stable": stable,
                "repeat_count": repeats,
                "latency_mean_ms": round(statistics.mean(latencies), 2),
                "issue_count": len(first.get("issues", [])),
                "issues": first.get("issues", []),
            }
        )

    precision = safe_ratio(true_positive, true_positive + false_positive)
    recall = safe_ratio(true_positive, true_positive + false_negative)
    f1 = safe_ratio(2 * precision * recall, precision + recall)
    total = len(labels)
    return {
        "evaluation": "agent_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "dataset": str(dataset_path),
        "case_count": total,
        "repeats_per_case": repeats,
        "metrics": {
            "decision_accuracy": round(safe_ratio(decision_correct, total), 4),
            "exact_issue_set_accuracy": round(safe_ratio(exact_issue_set_correct, total), 4),
            "issue_type_precision": round(precision, 4),
            "issue_type_recall": round(recall, 4),
            "issue_type_f1": round(f1, 4),
            "stability_rate": round(safe_ratio(stable_cases, total), 4),
            "rule_review_latency_mean_ms": round(statistics.mean(all_latencies), 2) if all_latencies else 0.0,
        },
        "cases": details,
    }


def markdown_report(report: dict[str, Any]) -> str:
    metrics = report["metrics"]
    lines = [
        "# Agent 审核评测报告",
        "",
        f"- 评测时间：{report['generated_at']}",
        f"- 用例数量：{report['case_count']}",
        f"- 每例重复次数：{report['repeats_per_case']}",
        f"- 审核结论准确率：{metrics['decision_accuracy']:.2%}",
        f"- 问题类型集合完全匹配率：{metrics['exact_issue_set_accuracy']:.2%}",
        f"- 问题类型 Precision：{metrics['issue_type_precision']:.2%}",
        f"- 问题类型 Recall：{metrics['issue_type_recall']:.2%}",
        f"- 问题类型 F1：{metrics['issue_type_f1']:.2%}",
        f"- 多次审核稳定一致率：{metrics['stability_rate']:.2%}",
        f"- 核心规则审查平均延迟：{metrics['rule_review_latency_mean_ms']:.2f} ms",
        "",
        "| 用例 | 期望结论 | 实际结论 | 期望问题类型 | 实际问题类型 | 稳定 |",
        "|---|---|---|---|---|---|",
    ]
    for case in report["cases"]:
        lines.append(
            f"| {case['case']} | {case['expected_decision']} | {case['actual_decision']} | "
            f"{' / '.join(case['expected_issue_types']) or '-'} | "
            f"{' / '.join(case['actual_issue_types']) or '-'} | {'是' if case['stable'] else '否'} |"
        )
    lines.extend(
        [
            "",
            "> 这些指标只描述当前人工标注回归集，不代表真实生产材料上的总体准确率。延迟仅统计材料解析完成后的规则审查，不包含 Word/PDF/OCR 解析和大模型网络调用。",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate deterministic Agent review results.")
    parser.add_argument("--dataset", type=Path, default=ROOT / "evaluation/datasets/agent_cases.json")
    parser.add_argument("--cases-root", type=Path, default=ROOT / "测试用例_真实格式")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "evaluation/results")
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be at least 1")

    report = evaluate(args.dataset, args.cases_root, args.repeats)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "agent_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (args.output_dir / "agent_report.md").write_text(markdown_report(report), encoding="utf-8")
    print(markdown_report(report))


if __name__ == "__main__":
    main()
