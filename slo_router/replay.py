"""Arrival-rate replay against the real router; exact-match demo labels are optional."""
import argparse
import asyncio
import json
import math
import statistics
import time
from pathlib import Path
from typing import Any, Dict, List

import httpx


def percentile(values: List[float], p: float) -> float:
    if not values:
        return math.nan
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, math.ceil(p * len(ordered)) - 1)]


async def run_case(client: httpx.AsyncClient, base_url: str, row: Dict[str, Any], policy: str, start: float,
                   index: int, scale: float) -> Dict[str, Any]:
    target = start + row.get("arrival_ms", 0) / 1000 / scale
    await asyncio.sleep(max(0, target - time.perf_counter()))
    started = time.perf_counter()
    try:
        response = await client.post(base_url.rstrip("/") + "/v1/chat/completions", json={
            "model": "auto", "messages": row["messages"], "max_tokens": row.get("max_tokens", 64),
            "slo_ms": row.get("slo_ms", 10000), "quality_floor": row.get("quality_floor"), "policy": policy,
            "tenant": row.get("tenant", "demo"),
        }, timeout=60)
        elapsed = (time.perf_counter() - started) * 1000
        result = {"index": index, "policy": policy, "status": response.status_code, "latency_ms": elapsed,
                  "route": response.headers.get("X-SLO-Route"), "slo_met": elapsed <= row.get("slo_ms", 10000),
                  "predicted_cost_usd": float(response.headers.get("X-SLO-Predicted-Cost-Usd", "nan")),
                  "feature_source": response.headers.get("X-SLO-Feature-Source")}
        if response.is_success:
            body = response.json()
            answer = body["choices"][0]["message"]["content"]
            result["answer"] = answer
            if "reference" in row:
                result["correct"] = answer.strip() == row["reference"].strip()
            result["usage"] = body.get("usage")
        else:
            result["error"] = response.text[:500]
        return result
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        return {"index": index, "policy": policy, "status": 0,
                "latency_ms": (time.perf_counter() - started) * 1000, "error": type(exc).__name__,
                "slo_met": False}


def summarize(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    done = [r for r in rows if r["status"] == 200]
    scored = [r for r in done if "correct" in r]
    latencies = [r["latency_ms"] for r in done]
    return {
        "requests": len(rows), "completed": len(done), "scored": len(scored),
        "accuracy": sum(r["correct"] for r in scored) / len(scored) if scored else None,
        "correct_in_slo": sum(r.get("correct", False) and r["slo_met"] for r in scored),
        "slo_success_rate": sum(r["slo_met"] for r in done) / len(rows) if rows else None,
        "p50_ms": statistics.median(latencies) if latencies else None,
        "p95_ms": percentile(latencies, 0.95) if latencies else None,
        "p99_ms": percentile(latencies, 0.99) if latencies else None,
        "predicted_cost_usd": sum(r["predicted_cost_usd"] for r in done),
        "cost_per_correct_in_slo_usd": (
            sum(r["predicted_cost_usd"] for r in done) /
            sum(r.get("correct", False) and r["slo_met"] for r in scored)
        ) if any(r.get("correct", False) and r["slo_met"] for r in scored) else None,
        "routes": {name: sum(r.get("route") == name for r in done)
                   for name in sorted({r.get("route") for r in done if r.get("route")})},
        "feature_sources": {name: sum(r.get("feature_source") == name for r in done)
                            for name in sorted({r.get("feature_source") for r in done if r.get("feature_source")})},
    }


async def main_async(args: argparse.Namespace) -> None:
    rows = [json.loads(line) for line in Path(args.dataset).read_text().splitlines() if line.strip()]
    policies = args.policies.split(",")
    all_results = []
    async with httpx.AsyncClient(headers={"Authorization": "Bearer " + args.router_key} if args.router_key else {}) as client:
        for policy in policies:
            if args.router_key:
                reset = await client.post(args.url.rstrip("/") + "/admin/reset")
                reset.raise_for_status()
            start = time.perf_counter() + 0.05
            results = await asyncio.gather(*(run_case(client, args.url, row, policy, start, i, args.scale)
                                             for i, row in enumerate(rows)))
            all_results.extend(results)
            print(json.dumps({"policy": policy, **summarize(results)}, sort_keys=True))
    Path(args.output).write_text("".join(json.dumps(row) + "\n" for row in all_results))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset")
    parser.add_argument("--url", default="http://127.0.0.1:8100")
    parser.add_argument("--policies", default="fixed_cheapest,fixed_strongest,quality_only,slo_no_jev,slo")
    parser.add_argument("--scale", type=float, default=1.0, help="arrival speed multiplier")
    parser.add_argument("--output", default="replay-results.jsonl")
    parser.add_argument("--router-key", default="")
    args = parser.parse_args()
    if args.scale <= 0:
        parser.error("--scale must be positive")
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
