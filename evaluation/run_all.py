from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVALUATION_DIR = ROOT / "evaluation"


def run(script: str, *arguments: str) -> None:
    command = [sys.executable, str(EVALUATION_DIR / script), *arguments]
    print(f"\n=== {script} ===")
    subprocess.run(command, check=True, cwd=ROOT)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run project evaluation suites.")
    parser.add_argument("--compare-embeddings", action="store_true", help="Compare LocalHash and local BGE in isolated stores.")
    parser.add_argument("--ablate-chunks", action="store_true", help="Compare chunk size/overlap with fixed local BGE.")
    parser.add_argument("--include-cache", action="store_true", help="Also benchmark a running OfferPilot service.")
    parser.add_argument("--agent-repeats", type=int, default=3)
    parser.add_argument("--cache-requests", type=int, default=30)
    parser.add_argument("--cache-url", default="http://127.0.0.1:8080/api/job/hot")
    args = parser.parse_args()

    run("evaluate_rag.py")
    if args.compare_embeddings:
        run("compare_embeddings.py")
    if args.ablate_chunks:
        run("ablate_chunks.py")
    run("evaluate_agent.py", "--repeats", str(args.agent_repeats))
    if args.include_cache:
        run(
            "evaluate_cache.py",
            "--requests",
            str(args.cache_requests),
            "--url",
            args.cache_url,
        )


if __name__ == "__main__":
    main()
