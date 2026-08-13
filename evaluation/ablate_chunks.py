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
    SOURCE_DOCS_DIR,
    read_unstructured_text,
)

DEFAULT_CONFIGS = [(400, 80), (700, 120), (1000, 150)]


def percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(len(ordered) * ratio + 0.999999) - 1))
    return ordered[index]


def parse_configs(raw_configs: list[str]) -> list[tuple[int, int]]:
    if not raw_configs:
        return DEFAULT_CONFIGS
    configs: list[tuple[int, int]] = []
    for raw in raw_configs:
        try:
            size_text, overlap_text = raw.split("/", 1)
            size, overlap = int(size_text), int(overlap_text)
        except ValueError as exc:
            raise ValueError(f"Invalid chunk config '{raw}', expected SIZE/OVERLAP") from exc
        if size <= 0 or overlap < 0 or overlap >= size:
            raise ValueError(f"Invalid chunk config '{raw}': require 0 <= overlap < size")
        configs.append((size, overlap))
    return configs


def load_documents() -> list[dict[str, str]]:
    documents: list[dict[str, str]] = []
    seen_names: set[str] = set()
    for folder in (DOCS_DIR, SOURCE_DOCS_DIR):
        if not folder.exists():
            continue
        for path in folder.iterdir():
            file_key = path.name.lower()
            if (
                not path.is_file()
                or path.suffix.lower() not in {".pdf", ".doc", ".docx", ".txt", ".md"}
                or path.name in EXCLUDED_KB_NAMES
                or path.name.startswith("~$")
                or file_key in seen_names
            ):
                continue
            seen_names.add(file_key)
            try:
                text = read_unstructured_text(path)
            except Exception as exc:
                print(f"跳过无法解析的文档 {path.name}: {exc}", file=sys.stderr)
                continue
            if text.strip():
                documents.append({"source": path.name, "text": text})
    return documents


def split_documents(
    documents: list[dict[str, str]], chunk_size: int, chunk_overlap: int
) -> tuple[list[str], list[dict[str, Any]], dict[str, int]]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    texts: list[str] = []
    metadatas: list[dict[str, Any]] = []
    chunks_by_source: dict[str, int] = {}
    for document in documents:
        chunks = [chunk for chunk in splitter.split_text(document["text"]) if chunk.strip()]
        chunks_by_source[document["source"]] = len(chunks)
        for index, chunk in enumerate(chunks):
            texts.append(chunk)
            metadatas.append({"source": document["source"], "chunk": index})
    return texts, metadatas, chunks_by_source


def evaluate_config(
    embedding: Any,
    documents: list[dict[str, str]],
    cases: list[dict[str, Any]],
    chunk_size: int,
    chunk_overlap: int,
    top_k: int,
) -> dict[str, Any]:
    texts, metadatas, chunks_by_source = split_documents(
        documents, chunk_size, chunk_overlap
    )
    build_started = time.perf_counter()
    store = Chroma(
        collection_name=f"chunk-ablation-{uuid.uuid4().hex}",
        embedding_function=embedding,
    )
    store.add_texts(texts, metadatas=metadatas)
    build_seconds = time.perf_counter() - build_started

    # Exclude one-time model and collection initialization from latency metrics.
    store.similarity_search_with_score("取水许可", k=top_k)

    hit_at_1 = hit_at_k = 0
    reciprocal_rank_sum = keyword_recall_sum = 0.0
    latencies: list[float] = []
    details: list[dict[str, Any]] = []
    for case in cases:
        started = time.perf_counter()
        matches = store.similarity_search_with_score(case["query"], k=top_k)
        elapsed_ms = (time.perf_counter() - started) * 1000
        latencies.append(elapsed_ms)

        returned_sources = [doc.metadata.get("source", "") for doc, _ in matches]
        expected_sources = set(case["expected_sources"])
        relevant_ranks = [
            index + 1
            for index, source in enumerate(returned_sources)
            if source in expected_sources
        ]
        first_rank = min(relevant_ranks) if relevant_ranks else None
        hit_at_1 += int(first_rank == 1)
        hit_at_k += int(first_rank is not None)
        reciprocal_rank_sum += 1.0 / first_rank if first_rank else 0.0

        retrieved_text = "\n".join(doc.page_content for doc, _ in matches)
        keywords = case.get("expected_keywords", [])
        matched_keywords = [
            keyword for keyword in keywords if keyword.lower() in retrieved_text.lower()
        ]
        keyword_recall = len(matched_keywords) / len(keywords) if keywords else 1.0
        keyword_recall_sum += keyword_recall
        details.append(
            {
                "id": case["id"],
                "query": case["query"],
                "first_relevant_rank": first_rank,
                "returned_sources": returned_sources,
                "matched_keywords": matched_keywords,
                "keyword_recall": round(keyword_recall, 4),
                "latency_ms": round(elapsed_ms, 2),
            }
        )

    total = len(cases)
    store.delete_collection()
    return {
        "config": f"{chunk_size}/{chunk_overlap}",
        "chunk_size": chunk_size,
        "chunk_overlap": chunk_overlap,
        "chunk_count": len(texts),
        "chunks_by_source": chunks_by_source,
        "build_seconds": round(build_seconds, 2),
        "hit_at_1": round(hit_at_1 / total, 4),
        f"hit_at_{top_k}": round(hit_at_k / total, 4),
        "mrr": round(reciprocal_rank_sum / total, 4),
        "keyword_recall": round(keyword_recall_sum / total, 4),
        "query_latency_mean_ms": round(statistics.mean(latencies), 2),
        "query_latency_p95_ms": round(percentile(latencies, 0.95), 2),
        "cases": details,
    }


def select_recommended(results: list[dict[str, Any]], top_k: int) -> dict[str, Any]:
    hit_key = f"hit_at_{top_k}"
    # Retrieval quality comes first; fewer chunks and lower latency break quality ties.
    return max(
        results,
        key=lambda item: (
            item[hit_key],
            item["mrr"],
            item["keyword_recall"],
            -item["chunk_count"],
            -item["query_latency_p95_ms"],
        ),
    )


def markdown_report(report: dict[str, Any]) -> str:
    top_k = report["top_k"]
    hit_key = f"hit_at_{top_k}"
    lines = [
        "# Chunk 参数消融实验报告",
        "",
        f"- 评测时间：{report['generated_at']}",
        f"- 文档数量：{report['document_count']}",
        f"- 查询数量：{report['case_count']}",
        f"- 固定 Embedding：{report['embedding_model']}",
        f"- 固定检索参数：Top-{top_k}",
        f"- 推荐参数：{report['recommended_config']}",
        "",
        f"| Chunk/Overlap | 块数 | Hit@1 | Hit@{top_k} | MRR | 关键词召回 | 建库(s) | 查询均值(ms) | 查询P95(ms) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for result in report["results"]:
        marker = "（推荐）" if result["config"] == report["recommended_config"] else ""
        lines.append(
            f"| {result['config']}{marker} | {result['chunk_count']} | "
            f"{result['hit_at_1']:.2%} | {result[hit_key]:.2%} | {result['mrr']:.4f} | "
            f"{result['keyword_recall']:.2%} | {result['build_seconds']:.2f} | "
            f"{result['query_latency_mean_ms']:.2f} | {result['query_latency_p95_ms']:.2f} |"
        )

    lines.extend(
        [
            "",
            "## 单条查询排名",
            "",
            "| 用例 | " + " | ".join(result["config"] for result in report["results"]) + " |",
            "|---|" + "---:|" * len(report["results"]),
        ]
    )
    case_ids = [case["id"] for case in report["results"][0]["cases"]]
    for case_id in case_ids:
        ranks: list[str] = []
        for result in report["results"]:
            case = next(item for item in result["cases"] if item["id"] == case_id)
            ranks.append(str(case["first_relevant_rank"] or "未命中"))
        lines.append(f"| {case_id} | " + " | ".join(ranks) + " |")

    lines.extend(
        [
            "",
            "> 推荐参数按 Hit@K、MRR、关键词召回率依次优先，在质量相同时再选择块数更少、P95 更低的配置。",
            "> 为保证单变量实验，三组配置都索引完整文档，不使用业务建库中的单文件 80 块上限。结果只代表当前 12 条人工标注查询。",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ablate chunk size and overlap with fixed BGE, corpus, queries and Top-K."
    )
    parser.add_argument("--dataset", type=Path, default=ROOT / "evaluation/datasets/rag_cases.json")
    parser.add_argument("--config", action="append", default=[], help="Chunk config SIZE/OVERLAP; repeat for multiple configs.")
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "evaluation/results")
    args = parser.parse_args()
    if args.top_k < 1:
        parser.error("--top-k must be at least 1")
    try:
        configs = parse_configs(args.config)
    except ValueError as exc:
        parser.error(str(exc))

    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    cases = json.loads(args.dataset.read_text(encoding="utf-8"))
    documents = load_documents()
    if not documents:
        raise SystemExit("No knowledge documents were parsed.")
    embedding = HuggingFaceEmbeddings(model_name=EMBED_MODEL)
    results = [
        evaluate_config(embedding, documents, cases, size, overlap, args.top_k)
        for size, overlap in configs
    ]
    recommended = select_recommended(results, args.top_k)
    report = {
        "evaluation": "chunk_parameter_ablation",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "document_count": len(documents),
        "case_count": len(cases),
        "embedding_model": EMBED_MODEL,
        "embedding_dimensions": len(embedding.embed_query("取水许可")),
        "top_k": args.top_k,
        "recommended_config": recommended["config"],
        "selection_priority": [f"hit_at_{args.top_k}", "mrr", "keyword_recall", "chunk_count", "query_latency_p95_ms"],
        "results": results,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "chunk_ablation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (args.output_dir / "chunk_ablation.md").write_text(
        markdown_report(report), encoding="utf-8"
    )
    print(markdown_report(report))


if __name__ == "__main__":
    main()
