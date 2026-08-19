from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python-ai-service"))

from app.rag.service import guarded_search


def main() -> None:
    path = ROOT / "evaluation/datasets/domain_gate_cases.jsonl"
    cases = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    passed = 0
    refused_total = refused_ok = 0
    answered_total = answered_ok = 0

    print("| 用例 | 期望 | 实际 | 结果 |")
    print("|---|---|---|---|")

    for case in cases:
        result = guarded_search(case["query"])
        actual = result["decision"]
        ok = actual == case["expected_decision"]

        if case["expected_decision"] == "REFUSED":
            refused_total += 1
            refused_ok += ok
        else:
            answered_total += 1
            answered_ok += ok and bool(result["items"])

        passed += ok
        print(f"| {case['id']} | {case['expected_decision']} | {actual} | {'PASS' if ok else 'FAIL'} |")

    print(f"\n总体准确率：{passed / len(cases):.2%}")
    print(f"无关问题拒答率：{refused_ok / refused_total:.2%}")
    print(f"领域问题放行率：{answered_ok / answered_total:.2%}")


if __name__ == "__main__":
    main()