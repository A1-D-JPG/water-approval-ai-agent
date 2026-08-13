from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python-ai-service"))

from langchain.text_splitter import RecursiveCharacterTextSplitter  # noqa: E402
from langchain_chroma import Chroma  # noqa: E402
from langchain_huggingface import HuggingFaceEmbeddings  # noqa: E402

from ai_core import (  # noqa: E402
    DOCS_DIR,
    EMBED_MODEL,
    EXCLUDED_KB_NAMES,
    MAX_CHUNKS_PER_FILE,
    SOURCE_DOCS_DIR,
    LocalHashEmbeddings,
    read_unstructured_text,
)


def load_corpus() -> tuple[list[str], list[dict[str, Any]]]:
    files: list[Path] = []
    seen: set[str] = set()
    for folder in (DOCS_DIR, SOURCE_DOCS_DIR):
        if not folder.exists():
            continue
        for path in folder.iterdir():
            key = path.name.lower()
            if (
                not path.is_file()
                or path.suffix.lower() not in {".pdf", ".doc", ".docx", ".txt", ".md"}
                or path.name in EXCLUDED_KB_NAMES
                or path.name.startswith("~$")
                or key in seen
            ):
                continue
            seen.add(key)
            files.append(path)

    splitter = RecursiveCharacterTextSplitter(chunk_size=700, chunk_overlap=120)
    texts: list[str] = []
    metadatas: list[dict[str, Any]] = []
    for path in files:
        try:
            content = read_unstructured_text(path)
        except Exception:
            continue
        for index, chunk in enumerate(splitter.split_text(content)):
            if index >= MAX_CHUNKS_PER_FILE:
                break
            if chunk.strip():
                texts.append(chunk)
                metadatas.append({"source": path.name, "chunk": index})
    return texts, metadatas


def evaluate_model(
    model_name: str,
    embedding: Any,
    texts: list[str],
    metadatas: list[dict[str, Any]],
    cases: list[dict[str, Any]],
    top_k: int,
) -> dict[str, Any]:
    build_started = time.perf_counter()
    store = Chroma(
        collection_name=f"embedding-eval-{uuid.uuid4().hex}",
        embedding_function=embedding,
    )
    store.add_texts(texts, metadatas=metadatas)
    build_seconds = time.perf_counter() - build_started

    hit_at_1 = hit_at_k = 0
    reciprocal_rank_sum = keyword_recall_sum = 0.0
    latencies: list[float] = []
    details: list[dict[str, Any]] = []
    for case in cases:
        started = time.perf_counter()
        matches = store.similarity_search_with_score(case["query"], k=top_k)
        latency_ms = (time.perf_counter() - started) * 1000
        latencies.append(latency_ms)
        sources = [doc.metadata.get("source", "") for doc, _ in matches]
        expected = set(case["expected_sources"])
        ranks = [index + 1 for index, source in enumerate(sources) if source in expected]
        first_rank = min(ranks) if ranks else None
        hit_at_1 += int(first_rank == 1)
        hit_at_k += int(first_rank is not None)
        reciprocal_rank_sum += 1.0 / first_rank if first_rank else 0.0
        retrieved_text = "\n".join(doc.page_content for doc, _ in matches)
        keywords = case.get("expected_keywords", [])
        matched_keywords = [keyword for keyword in keywords if keyword.lower() in retrieved_text.lower()]
        keyword_recall = len(matched_keywords) / len(keywords) if keywords else 1.0
        keyword_recall_sum += keyword_recall
        details.append(
            {
                "id": case["id"],
                "first_relevant_rank": first_rank,
                "returned_sources": sources,
                "keyword_recall": round(keyword_recall, 4),
                "latency_ms": round(latency_ms, 2),
            }
        )

    total = len(cases)
    store.delete_collection()
    return {
        "model": model_name,
        "dimensions": len(embedding.embed_query("取水许可")),
        "chunk_count": len(texts),
        "build_seconds": round(build_seconds, 2),
        "hit_at_1": round(hit_at_1 / total, 4),
        f"hit_at_{top_k}": round(hit_at_k / total, 4),
        "mrr": round(reciprocal_rank_sum / total, 4),
        "keyword_recall": round(keyword_recall_sum / total, 4),
        "query_latency_mean_ms": round(statistics.mean(latencies), 2),
        "cases": details,
    }


def markdown_report(report: dict[str, Any]) -> str:
    top_k = report["top_k"]
    hit_k_name = f"hit_at_{top_k}"
    lines = [
        "# Embedding A/B 对照报告",
        "",
        f"- 评测时间：{report['generated_at']}",
        f"- 查询数量：{report['case_count']}",
        f"- 文本块数量：{report['chunk_count']}",
        f"- Chunk 参数：{report['chunk_size']} / overlap {report['chunk_overlap']}",
        "",
        "| Embedding | 维度 | Hit@1 | Hit@K | MRR | 关键词召回 | 建库耗时(s) | 平均查询(ms) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for result in report["models"]:
        lines.append(
            f"| {result['model']} | {result['dimensions']} | {result['hit_at_1']:.2%} | "
            f"{result[hit_k_name]:.2%} | {result['mrr']:.4f} | {result['keyword_recall']:.2%} | "
            f"{result['build_seconds']:.2f} | {result['query_latency_mean_ms']:.2f} |"
        )
    if len(report["models"]) == 2:
        baseline, optimized = report["models"]
        lines.extend(
            [
                "",
                f"- Hit@{top_k} 绝对提升：{optimized[hit_k_name] - baseline[hit_k_name]:.2%}",
                f"- MRR 绝对提升：{optimized['mrr'] - baseline['mrr']:.4f}",
                "",
                "> 两个模型使用完全相同的文档、分块参数、查询和人工标注，仅替换 Embedding。",
            ]
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare LocalHash and BGE embeddings in isolated stores.")
    parser.add_argument("--dataset", type=Path, default=ROOT / "evaluation/datasets/rag_cases.json")
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "evaluation/results")
    parser.add_argument("--skip-bge", action="store_true")
    args = parser.parse_args()

    cases = json.loads(args.dataset.read_text(encoding="utf-8"))
    texts, metadatas = load_corpus()
    models: list[tuple[str, Any]] = [("LocalHashEmbeddings", LocalHashEmbeddings())]
    if not args.skip_bge:
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        models.append((EMBED_MODEL, HuggingFaceEmbeddings(model_name=EMBED_MODEL)))

    results = [
        evaluate_model(name, embedding, texts, metadatas, cases, args.top_k)
        for name, embedding in models
    ]
    report = {
        "evaluation": "embedding_ab_comparison",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "case_count": len(cases),
        "chunk_count": len(texts),
        "chunk_size": 700,
        "chunk_overlap": 120,
        "top_k": args.top_k,
        "models": results,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "embedding_comparison.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (args.output_dir / "embedding_comparison.md").write_text(
        markdown_report(report), encoding="utf-8"
    )
    print(markdown_report(report))


if __name__ == "__main__":
    main()
