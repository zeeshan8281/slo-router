"""Repeatable load, deadline, and arrival-pattern sweeps for the deterministic router fixture."""
import asyncio
import json
import math
import statistics
import time
from pathlib import Path

import httpx

from slo_router.replay import run_case, summarize


URL = "http://127.0.0.1:8100"
POLICIES = ("quality_only", "slo_no_jev")
REPEATS = 3


def case(arrival_ms: int = 0, slo_ms: int = 400) -> dict:
    return {
        "arrival_ms": arrival_ms,
        "messages": [{"role": "user", "content": "Extract the color from: the car is blue."}],
        "reference": "blue",
        "max_tokens": 8,
        "slo_ms": slo_ms,
    }


async def run_cell(client, cases, policy, metadata):
    reset = await client.post(URL + "/admin/reset")
    reset.raise_for_status()
    start = time.perf_counter() + 0.02
    rows = await asyncio.gather(*[
        run_case(client, URL, item, policy, start, index, 1.0)
        for index, item in enumerate(cases)
    ])
    for row in rows:
        row.update(metadata)
    summary = {**metadata, "policy": policy, **summarize(rows)}
    errors = [abs(row["latency_ms"] - row["predicted_latency_ms"]) for row in rows
              if row["status"] == 200 and math.isfinite(row["predicted_latency_ms"])]
    summary["latency_mae_ms"] = statistics.mean(errors) if errors else None
    return rows, summary


async def sweep(client, name, dimensions):
    raw, summaries = [], []
    for value, cases in dimensions:
        for repeat in range(1, REPEATS + 1):
            for policy in POLICIES:
                rows, summary = await run_cell(
                    client, cases, policy, {"experiment": name, "value": value, "repeat": repeat}
                )
                raw.extend(rows)
                summaries.append(summary)
    return raw, summaries


def range_text(values, percent=False):
    low, high = min(values), max(values)
    if percent:
        return f"{low:.0%}" if low == high else f"{low:.0%}–{high:.0%}"
    return f"{low:.2f}" if low == high else f"{low:.2f}–{high:.2f}"


def routes_text(routes):
    return " / ".join(f"{name} {count}" for name, count in routes.items())


def table(summaries, experiment, label, suffix=""):
    lines = [
        f"| {label} | Policy | SLO success across 3 runs | Median p95 | Median latency MAE | Last-run routes |",
        "| ---: | --- | ---: | ---: | ---: | --- |",
    ]
    values = list(dict.fromkeys(row["value"] for row in summaries if row["experiment"] == experiment))
    for value in values:
        for policy in POLICIES:
            cells = [row for row in summaries if row["experiment"] == experiment
                     and row["value"] == value and row["policy"] == policy]
            lines.append(
                f"| {value}{suffix} | {policy} | "
                f"{range_text([row['slo_success_rate'] for row in cells], percent=True)} | "
                f"{statistics.median(row['p95_ms'] for row in cells):.2f} ms | "
                f"{statistics.median(row['latency_mae_ms'] for row in cells):.2f} ms | "
                f"{routes_text(cells[-1]['routes'])} |"
            )
    return lines


async def main():
    load = [(size, [case() for _ in range(size)]) for size in (1, 5, 10, 20, 40)]
    deadlines = [(target, [case(slo_ms=target) for _ in range(10)]) for target in (150, 250, 400, 800)]
    arrivals = [(gap, [case(arrival_ms=index * gap) for index in range(20)])
                for gap in (0, 40, 80, 120)]

    all_raw, all_summaries = [], []
    async with httpx.AsyncClient(headers={"Authorization": "Bearer demo"}) as client:
        for name, dimensions in (("load", load), ("slo", deadlines), ("arrival", arrivals)):
            raw, summaries = await sweep(client, name, dimensions)
            all_raw.extend(raw)
            all_summaries.extend(summaries)

    results = Path("results")
    results.joinpath("sweep-replay.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in all_raw)
    )
    results.joinpath("sweep-summary.json").write_text(json.dumps(all_summaries, indent=2) + "\n")

    lines = [
        "# Router sensitivity sweeps",
        "",
        "Each point is three independent runs against deterministic simulated backends. Quality-only and SLO-aware policies receive identical requests, backend parameters, and reset runtime state. Latency MAE is the mean absolute error between the selected route's pre-dispatch prediction and observed end-to-end latency.",
        "",
        "## Burst-size sweep",
        "",
        *table(all_summaries, "load", "Simultaneous requests"),
        "",
        "## SLO-target sweep",
        "",
        *table(all_summaries, "slo", "SLO target", " ms"),
        "",
        "## Arrival-pattern sweep",
        "",
        *table(all_summaries, "arrival", "Inter-arrival gap", " ms"),
        "",
        "These are mechanism and sensitivity tests, not real-model performance claims. The simulator does not reproduce GPU batching, token-level scheduling, network variance, or model-quality uncertainty.",
    ]
    results.joinpath("sweep-analysis.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    asyncio.run(main())
