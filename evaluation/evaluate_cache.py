from __future__ import annotations

import argparse
import hashlib
import json
import socket
import statistics
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def redis_command(host: str, port: int, *parts: str) -> Any:
    encoded = [part.encode("utf-8") for part in parts]
    payload = f"*{len(encoded)}\r\n".encode()
    payload += b"".join(f"${len(part)}\r\n".encode() + part + b"\r\n" for part in encoded)
    with socket.create_connection((host, port), timeout=3) as connection:
        connection.sendall(payload)
        stream = connection.makefile("rb")
        marker = stream.read(1)
        line = stream.readline().rstrip(b"\r\n")
        if marker == b"+":
            return line.decode("utf-8")
        if marker == b":":
            return int(line)
        if marker == b"$":
            length = int(line)
            if length == -1:
                return None
            value = stream.read(length)
            stream.read(2)
            return value.decode("utf-8")
        if marker == b"-":
            raise RuntimeError(f"Redis error: {line.decode('utf-8', errors='replace')}")
        raise RuntimeError("Unsupported Redis response")


def request_once(url: str, timeout: float) -> tuple[float, bytes]:
    started = time.perf_counter()
    with urllib.request.urlopen(url, timeout=timeout) as response:
        body = response.read()
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status}")
    return (time.perf_counter() - started) * 1000, body


def percentile(values: list[float], ratio: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(len(ordered) * ratio + 0.999999) - 1))
    return ordered[index]


def summarize(values: list[float]) -> dict[str, float]:
    return {
        "count": len(values),
        "mean_ms": round(statistics.mean(values), 2),
        "p50_ms": round(statistics.median(values), 2),
        "p95_ms": round(percentile(values, 0.95), 2),
        "min_ms": round(min(values), 2),
        "max_ms": round(max(values), 2),
    }


def evaluate(url: str, requests: int, redis_host: str, redis_port: int, cache_key: str, timeout: float) -> dict[str, Any]:
    cold_latencies: list[float] = []
    warm_latencies: list[float] = []
    response_hashes: set[str] = set()

    redis_command(redis_host, redis_port, "PING")
    for _ in range(requests):
        redis_command(redis_host, redis_port, "DEL", cache_key)
        latency, body = request_once(url, timeout)
        cold_latencies.append(latency)
        response_hashes.add(hashlib.sha256(body).hexdigest())

    redis_command(redis_host, redis_port, "DEL", cache_key)
    request_once(url, timeout)  # Warm-up request populates Redis.
    if redis_command(redis_host, redis_port, "EXISTS", cache_key) != 1:
        raise RuntimeError(f"Cache key was not created: {cache_key}")
    ttl_seconds = redis_command(redis_host, redis_port, "TTL", cache_key)
    for _ in range(requests):
        latency, body = request_once(url, timeout)
        warm_latencies.append(latency)
        response_hashes.add(hashlib.sha256(body).hexdigest())

    cold = summarize(cold_latencies)
    warm = summarize(warm_latencies)
    speedup = cold["mean_ms"] / warm["mean_ms"] if warm["mean_ms"] else 0.0
    reduction = 1 - warm["mean_ms"] / cold["mean_ms"] if cold["mean_ms"] else 0.0
    return {
        "evaluation": "redis_cache_comparison",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "url": url,
        "cache_key": cache_key,
        "requests_per_group": requests,
        "ttl_seconds_after_warmup": ttl_seconds,
        "response_consistent": len(response_hashes) == 1,
        "cold": cold,
        "warm": warm,
        "metrics": {
            "mean_speedup": round(speedup, 3),
            "mean_latency_reduction": round(reduction, 4),
        },
    }


def markdown_report(report: dict[str, Any]) -> str:
    cold = report["cold"]
    warm = report["warm"]
    metrics = report["metrics"]
    return "\n".join(
        [
            "# Redis 缓存冷热对照报告",
            "",
            f"- 评测时间：{report['generated_at']}",
            f"- 接口：{report['url']}",
            f"- 每组请求数：{report['requests_per_group']}",
            f"- 缓存键：{report['cache_key']}",
            f"- 预热后 TTL：{report['ttl_seconds_after_warmup']} 秒",
            f"- 冷热响应内容一致：{'是' if report['response_consistent'] else '否'}",
            "",
            "| 场景 | 平均(ms) | P50(ms) | P95(ms) | 最小(ms) | 最大(ms) |",
            "|---|---:|---:|---:|---:|---:|",
            f"| 冷缓存（每次先删除键） | {cold['mean_ms']:.2f} | {cold['p50_ms']:.2f} | {cold['p95_ms']:.2f} | {cold['min_ms']:.2f} | {cold['max_ms']:.2f} |",
            f"| 热缓存（预热后读取） | {warm['mean_ms']:.2f} | {warm['p50_ms']:.2f} | {warm['p95_ms']:.2f} | {warm['min_ms']:.2f} | {warm['max_ms']:.2f} |",
            "",
            f"- 平均响应加速比：{metrics['mean_speedup']:.2f}x",
            f"- 平均延迟下降：{metrics['mean_latency_reduction']:.2%}",
            "",
            "> 冷缓存请求包含 MySQL 查询与 Redis 写入；热缓存请求从 Redis 读取。该结果仅适用于报告中的本地测试环境。",
            "",
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare cold and warm Redis cache latency.")
    parser.add_argument("--url", default="http://127.0.0.1:8080/api/job/hot")
    parser.add_argument("--requests", type=int, default=30)
    parser.add_argument("--redis-host", default="127.0.0.1")
    parser.add_argument("--redis-port", type=int, default=6379)
    parser.add_argument("--cache-key", default="offerpilot:job:hot")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "evaluation/results")
    args = parser.parse_args()
    if args.requests < 2:
        parser.error("--requests must be at least 2")

    try:
        report = evaluate(
            args.url, args.requests, args.redis_host, args.redis_port, args.cache_key, args.timeout
        )
    except (ConnectionError, OSError, urllib.error.URLError, RuntimeError) as exc:
        raise SystemExit(
            "缓存评测未执行：请先启动 OfferPilot、MySQL 和 Redis，并确认 8080 端口运行的是 "
            f"OfferPilot。原因：{exc}"
        ) from exc

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "cache_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (args.output_dir / "cache_report.md").write_text(markdown_report(report), encoding="utf-8")
    print(markdown_report(report))


if __name__ == "__main__":
    main()
