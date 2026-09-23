# Burst-load SLO experiment

Run date: 23 September 2026. This experiment uses deterministic simulated backends to isolate queue-aware routing behavior. It is a router integration test, not a benchmark of real language models.

## Setup

- Ten extraction requests arrive simultaneously with a 400 ms latency SLO.
- The `cheap` backend has one execution slot, 80 ms service time, and the lower token price.
- The `fast-capacity` backend has sixteen execution slots, 80 ms service time, and costs ten times more per token.
- Both backends return the same correct answers for this dataset.
- Router runtime state is reset between policies.

## Repeated result

Five independent runs produced the same route distribution and SLO-success rate for every policy.

| Policy | Routes | SLO success range | Median p95 across runs | Predicted cost |
| --- | --- | ---: | ---: | ---: |
| Fixed cheapest | cheap 10 | 40%–40% | 833.69 ms | $0.0000530 |
| Fixed strongest | fast-capacity 10 | 100%–100% | 112.78 ms | $0.0005300 |
| Quality only | cheap 10 | 40%–40% | 827.90 ms | $0.0000530 |
| SLO-aware | cheap 4 / fast-capacity 6 | 100%–100% | 341.91 ms | $0.0003392 |

The quality-only policy keeps selecting the cheapest eligible backend because it does not consider queue-induced deadline risk. The SLO-aware policy leaves four requests on the cheap backend and moves six to available capacity. This preserves 100% accuracy and raises SLO success from 40% to 100%, while costing 36% less than fixed-strongest routing.

## Reproduce

```sh
make video-demo
```

The command writes `video-replay.jsonl`, `video-traces.jsonl`, `video-results.md`, and `video-results.svg` into this directory.

## Limits

The backend quality values, prices, service times, and labels are controlled fixtures. They demonstrate the routing mechanism but do not predict savings on a real workload. Production claims require a frozen counterfactual dataset, measured model endpoints, workload-specific graders, and repeated live-load evaluation.
