"""Collect counterfactual backend outcomes and fit transparent per-task quality priors."""
import argparse
import asyncio
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List

import httpx

from .core import TASKS, Settings


def split(row: Dict[str, Any]) -> str:
    key = json.dumps(row["messages"], sort_keys=True)
    return "test" if int(hashlib.sha256(key.encode()).hexdigest()[:8], 16) % 5 == 0 else "train"


async def collect_one(client: httpx.AsyncClient, backend, row: Dict[str, Any], index: int) -> Dict[str, Any]:
    started = time.perf_counter()
    headers = {}
    if backend.api_key_env and os.environ.get(backend.api_key_env):
        headers["Authorization"] = "Bearer " + os.environ[backend.api_key_env]
    result = {"index": index, "backend": backend.name, "task": row["task"], "split": split(row),
              "reference": row["reference"]}
    try:
        response = await client.post(str(backend.url).rstrip("/") + "/v1/chat/completions",
                                     headers=headers,
                                     json={"model": backend.model, "messages": row["messages"], "stream": False,
                                           "max_tokens": row.get("max_tokens", 64)}, timeout=120)
        result["status"] = response.status_code
        response.raise_for_status()
        body = response.json()
        answer = body["choices"][0]["message"]["content"]
        result["answer"] = answer
        result["correct"] = answer.strip() == row["reference"].strip()
        result["usage"] = body.get("usage")
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        result["error"] = type(exc).__name__
        result["correct"] = False
    result["latency_ms"] = (time.perf_counter() - started) * 1000
    return result


async def collect(args) -> None:
    settings = Settings.model_validate_json(Path(args.config).read_text())
    rows = [json.loads(line) for line in Path(args.dataset).read_text().splitlines() if line.strip()]
    for row in rows:
        if row.get("task") not in TASKS or "reference" not in row:
            raise ValueError("each row needs a task and reference")
    semaphore = asyncio.Semaphore(args.concurrency)
    async with httpx.AsyncClient() as client:
        async def bounded(backend, row, index):
            async with semaphore:
                return await collect_one(client, backend, row, index)
        results = await asyncio.gather(*(bounded(backend, row, i) for i, row in enumerate(rows)
                                         for backend in settings.backends))
    Path(args.output).write_text("".join(json.dumps(result) + "\n" for result in results))
    print(json.dumps({"rows": len(rows), "backend_runs": len(results), "output": args.output}))


def fit(args) -> None:
    config = json.loads(Path(args.config).read_text())
    results = [json.loads(line) for line in Path(args.matrix).read_text().splitlines() if line.strip()]
    report = {}
    for backend in config["backends"]:
        report[backend["name"]] = {}
        for task in TASKS:
            train = [r for r in results if r["backend"] == backend["name"] and r["task"] == task and r["split"] == "train"]
            test = [r for r in results if r["backend"] == backend["name"] and r["task"] == task and r["split"] == "test"]
            # Beta(1,1) posterior mean; low-n estimates remain explicitly marked.
            if len(train) >= args.min_samples:
                backend["quality"][task] = (1 + sum(bool(r["correct"]) for r in train)) / (2 + len(train))
            report[backend["name"]][task] = {
                "train_n": len(train), "train_correct": sum(bool(r["correct"]) for r in train),
                "test_n": len(test), "test_accuracy": sum(bool(r["correct"]) for r in test) / len(test) if test else None,
                "fitted_quality": backend["quality"][task],
                "fit_applied": len(train) >= args.min_samples,
            }
    Path(args.output).write_text(json.dumps(config, indent=2) + "\n")
    Path(args.report).write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"config": args.output, "report": args.report}))


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    collect_parser = sub.add_parser("collect")
    collect_parser.add_argument("dataset")
    collect_parser.add_argument("--config", default="config.example.json")
    collect_parser.add_argument("--concurrency", type=int, default=8)
    collect_parser.add_argument("--output", default="matrix.jsonl")
    fit_parser = sub.add_parser("fit")
    fit_parser.add_argument("matrix")
    fit_parser.add_argument("--config", default="config.example.json")
    fit_parser.add_argument("--output", default="config.fitted.json")
    fit_parser.add_argument("--report", default="fit-report.json")
    fit_parser.add_argument("--min-samples", type=int, default=20)
    args = parser.parse_args()
    if args.command == "collect":
        if args.concurrency <= 0:
            parser.error("--concurrency must be positive")
        asyncio.run(collect(args))
    else:
        if args.min_samples <= 0:
            parser.error("--min-samples must be positive")
        fit(args)


if __name__ == "__main__":
    main()
