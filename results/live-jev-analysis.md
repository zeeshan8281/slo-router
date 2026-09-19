# Live Jev 1.13 integration result

Run date: 19 September 2026. The semantic feature path used the real OpenRouter `POST /api/alpha/decisions` endpoint with `typesafe/jev-1.13`; both downstream completion backends were deterministic local simulators. This isolates router behavior and Jev overhead. It is an integration measurement, not a claim about real downstream model quality.

## Endpoint validation

The initial smoke request returned HTTP 200 from provider `TypeSafe` using resolved model `typesafe/jev-1.13-20260917`. The response contained all three requested typed decisions, probability distributions, token usage, and billed cost. The API key was held only in an ephemeral shell environment and was not written to project files or traces.

## Replay result

| Policy | Feature path | Accuracy | Routes | p50 end-to-end | p95 end-to-end | Predicted total cost |
| --- | --- | ---: | --- | ---: | ---: | ---: |
| Fixed cheapest | Local | 62.5% | fast 8 | 28.58 ms | 35.64 ms | $0.00013140 |
| Fixed strongest | Local | 100% | strong 8 | 69.23 ms | 69.47 ms | $0.00131400 |
| Quality only | Live Jev | 100% | fast 4 / strong 4 | 777.64 ms | 1296.30 ms | $0.00086016 |
| SLO, no Jev | Local | 100% | fast 4 / strong 4 | 56.10 ms | 77.93 ms | $0.00071190 |
| SLO + Jev | Live Jev | 100% | fast 4 / strong 4 | 436.99 ms | 490.38 ms | $0.00086016 |

Across the two Jev-backed policies, 16/16 decision calls succeeded with no lexical fallbacks. Jev feature latency was 453.58 ms at p50 and 1257.50 ms at p95. Total Jev input cost across those calls was $0.00029652. The SLO policy's eight Jev calls added $0.00014826 to predicted total cost.

On this fixture, Jev did not change a route or improve accuracy relative to `slo_no_jev`. It increased SLO-router p95 from 77.93 ms to 490.38 ms, about 6.3×. That is a negative result for synchronous Jev routing on this particular workload: the local feature path reached the same decision frontier with materially lower latency and cost.

## Semantic differences

Jev and the local classifier disagreed on three of eight task labels:

- `Why does a CUDA barrier inside a divergent branch deadlock?`: local `code_debugging`; Jev `reasoning` with 0.96 probability and `code_debugging` at 0.04.
- `What is 2+2?`: local `reasoning`; Jev `other` at 0.76 and `reasoning` at 0.24.
- `What is 9*7?`: local `reasoning`; Jev `other` at 0.94 and `reasoning` at 0.06.

The disagreements did not change routes. The exactness signal was high for the arithmetic prompts, raising the effective quality floor and sending them to the strong backend even when the task label was `other`. Jev assigned external-evidence probabilities from 0.02 to 0.08 for all eight static prompts, so no request was rejected for missing retrieval tools.

## Cache validation

After an authenticated runtime reset, two identical tenant-scoped SLO requests produced:

- first request: `X-SLO-Feature-Source: jev`, predicted cost `$0.000192732`;
- second request: `X-SLO-Feature-Source: jev_cache`, predicted cost `$0.000174000`.

The difference is the removed incremental Jev call. Cache identity includes the tenant, messages, and pinned question revision; resetting runtime state also clears this cache.

## Engineering conclusion

Keep Jev out of the synchronous path for this workload unless a larger, real-model counterfactual dataset demonstrates quality gains that justify several hundred milliseconds of added tail latency. The strongest next experiment is asynchronous/offline feature extraction or routing requests with longer downstream generation times, where Jev latency may be amortized. The system already supports both paths: `slo_no_jev` is the production baseline, and `slo` remains the measured experimental policy.

Raw artifacts in this directory: `live-jev-replay.jsonl`, `live-jev-traces.jsonl`, `live-jev-summary.json`, and `live-jev-results.svg`.
