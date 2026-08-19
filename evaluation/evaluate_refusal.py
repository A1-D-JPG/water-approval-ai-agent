from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python-ai-service"))

from app.rag.service import guarded_search


def main() -> None:
    dataset = ROOT / "evaluation/datasets/refusal_cases.jsonl"
    cases = [
        json.loads(line)
        for line in dataset.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    passed = 0
    print("| 用例 | 期望 | 实际 | 结果 |")
    print("|---|---|---|---|")

    for case in cases:
        result = guarded_search(case["query"])
        actual = result["decision"]
        ok = actual == case["expected_decision"]
        passed += ok
        print(
            f"| {case['id']} | {case['expected_decision']} | "
            f"{actual} | {'PASS' if ok else 'FAIL'} |"
        )

    rate = passed / len(cases) if cases else 0
    print(f"\n拒答准确率：{rate:.2%}（{passed}/{len(cases)}）")


if __name__ == "__main__":
    main()