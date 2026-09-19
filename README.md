# SLO Router

<p align="center">
  <strong>Route each LLM request to the cheapest backend that can answer correctly within its latency SLO.</strong>
</p>

<p align="center">
  <a href="https://github.com/zeeshan8281/slo-router/actions/workflows/test.yml"><img alt="Tests" src="https://github.com/zeeshan8281/slo-router/actions/workflows/test.yml/badge.svg"></a>
  <img alt="Python 3.9+" src="https://img.shields.io/badge/python-3.9%2B-3776AB?logo=python&logoColor=white">
  <img alt="OpenAI compatible" src="https://img.shields.io/badge/API-OpenAI--compatible-111827">
  <img alt="Jev 1.13" src="https://img.shields.io/badge/decision_model-Jev_1.13-7048E8">
</p>

SLO Router is an OpenAI-compatible proxy that chooses an LLM backend using request semantics, backend quality priors, live queue depth, context capacity, expected prefill/decode time, price, and a caller latency SLO. Jev 1.13 can supply bounded semantic features; the service falls back to deterministic local features when the Jev key is absent, times out, or returns an invalid response.

The repository is standalone. The bundled simulated backends let the complete proxy, trace, counterfactual collection, and replay paths run without GPUs or paid API keys. Replace them with vLLM or any OpenAI-compatible endpoints for a real experiment.

The checked-in [live Jev analysis](results/live-jev-analysis.md) records a real OpenRouter Decisions run against the deterministic backend fixture, including latency, cost, semantic disagreements, and cache behavior.

> **Measured result:** Jev preserved the same routes and accuracy as the local feature path on the bundled fixture, but increased p95 end-to-end latency from **77.93 ms to 490.38 ms**. The repository keeps both implementations so the decision can be repeated on real workloads instead of assumed.

## What this repository contributes

| Component | Purpose |
| --- | --- |
| OpenAI-compatible proxy | Drop-in synchronous and streaming request path |
| Typed semantic features | Jev task, exactness, and external-evidence decisions |
| Constrained controller | Minimum expected cost subject to quality and SLO floors |
| Live serving state | Queue depth, active requests, backend health, and prefix reuse |
| Counterfactual matrix | Runs every labeled request on every backend before fitting priors |
| Arrival-rate replay | Measures quality, p50/p95/p99, route mix, cost, and correct-in-SLO |
| Failure handling | Jev fallback, backend retry, context/tool filtering, and explicit infeasibility |

## Architecture

[Open the editable Excalidraw architecture](diagrams/slo-router-architecture.excalidraw) in Excalidraw using **File → Open**. Every node, label, connector, and color remains editable.

The request path is `client → authenticated proxy → semantic feature stage → constrained controller → selected backend → streamed response`. Jev success is cached by tenant and question revision; timeout, 429, malformed output, or overload uses the local deterministic feature path. Queue metrics and fitted quality/cost priors enter the controller independently, while every decision produces a prompt-free hashed trace for replay.

For backend `b`, the controller estimates:

```text
latency_b = queue_wait_b
          + uncached_prompt_tokens / prefill_rate_b
          + expected_output_tokens / decode_rate_b
          + base_network_latency_b
          + semantic_feature_latency
```

It filters backends by health, context, tool support, quality floor, and predicted SLO-success probability. Among feasible backends it chooses minimum expected request cost. An exactness signal raises the quality floor; it never overrides context or capability checks. If no backend is feasible, the API returns `503` with per-backend reasons instead of silently violating the contract.

The latency model is intentionally interpretable. Its rates and quality priors are configuration inputs that must be fitted to the deployed models and workload. They are not universal model claims.

## Run the local end-to-end system

Python 3.9+ is supported. From this directory:

```sh
python3 -m pip install -e '.[test]'

python3 -m uvicorn slo_router.sim_backend:app --host 127.0.0.1 --port 8101
SLO_SIM_TIER=strong python3 -m uvicorn slo_router.sim_backend:app --host 127.0.0.1 --port 8102
SLO_ROUTER_API_KEY=demo SLO_ROUTER_CONFIG=config.example.json \
  python3 -m uvicorn slo_router.service:app --host 127.0.0.1 --port 8100
```

Run the test suite, collect the counterfactual matrix, fit per-task quality priors, and replay every policy:

```sh
python3 -m pytest -q
python3 -m slo_router.matrix collect data/demo.jsonl --output matrix.jsonl
python3 -m slo_router.matrix fit matrix.jsonl --output config.fitted.json --report fit-report.json
python3 -m slo_router.replay data/demo.jsonl --router-key demo --output replay-results.jsonl
python3 -m slo_router.report replay-results.jsonl
```

The demo labels use exact match so that the harness is deterministic. Real workloads should replace this with task-specific executable checks, human labels, or a separately validated judge. Do not present the eight-row demo as a model benchmark.

### Use live Jev

Set the OpenRouter key only in your environment:

```sh
export OPENROUTER_API_KEY='...'
```

Requests using policy `slo` or `quality_only` will then call the Decisions endpoint. The response header `X-SLO-Feature-Source` reports `jev`, `jev_cache`, or `lexical_fallback`. Fixed policies and `slo_no_jev` never pay for a Jev call.

## Send a request

```sh
curl --fail-with-body http://127.0.0.1:8100/v1/chat/completions \
  -H 'Authorization: Bearer demo' \
  -H 'Content-Type: application/json' \
  -d '{
    "model":"auto",
    "messages":[{"role":"user","content":"Why can a CUDA barrier in a divergent branch deadlock?"}],
    "max_tokens":128,
    "slo_ms":2500,
    "quality_floor":0.85,
    "tenant":"research",
    "policy":"slo"
  }'
```

The upstream body remains OpenAI-compatible. Router controls are `slo_ms`, `quality_floor`, `tenant`, and `policy`. Response headers expose the chosen route, request ID, predicted latency/quality/cost, and whether features came from Jev or the local fallback. Jev/local features cover task type, exactness, and whether current external evidence is required. The trace stores prompt and tenant hashes rather than raw prompt text.

Policies:

- `fixed_cheapest`: lowest predicted request cost among eligible backends.
- `fixed_strongest`: highest configured task quality among eligible backends.
- `quality_only`: cheapest backend above the quality floor, ignoring SLO probability.
- `slo_no_jev`: full load-aware controller with deterministic semantic features.
- `slo`: full controller with Jev and automatic local fallback.

Set `OPENROUTER_API_KEY` to enable Jev. The implementation calls `POST https://openrouter.ai/api/alpha/decisions` with pinned model `typesafe/jev-1.13` and pinned question revision in code. This endpoint is alpha; failures are bounded by `jev_timeout_ms` and fall back locally. The official direct TypeSafe endpoint uses a different URL and model ID and is not silently substituted.

## Configure real backends

Copy `config.example.json`. Each backend needs an OpenAI-compatible base URL and model ID, prices, context limit, measured prefill/decode rates, base overhead, and task quality priors. Set `api_key_env` to the name of an environment variable containing that backend's bearer key. Set `metrics_url` to a vLLM Prometheus endpoint when available; the router reads `vllm:num_requests_waiting` and otherwise retains its local active-request count.

Quality priors must come from a counterfactual matrix: run every frozen labeled request on every backend with `matrix collect`, then fit only the training partition with `matrix fit`. The split is a deterministic hash of the message payload. The fit report keeps held-out accuracy separate. The current estimator uses a Beta(1,1) posterior mean and requires 20 training examples per backend/task slice by default; smaller slices are reported but do not overwrite configuration. Change `--min-samples` only as a disclosed experiment choice.

For real context enforcement, replace `count_tokens_approx` with tokenizer-exact counts for every backend family. The approximation is conservative and explicitly marked in code, but tokenizer differences make a single exact count impossible across arbitrary heterogeneous endpoints.

## Benchmark contract

Freeze the dataset, backend revisions, prompts, hardware, prices, arrival schedule, Jev model/questions, and configuration. Compare all policies on identical traffic. Reset runtime state between policy runs when an authenticated local router is used. Report:

- quality, per-task failures, and correct-in-SLO count;
- p50/p95/p99 end-to-end latency and SLO success rate;
- route distribution and offered load;
- total predicted/actual cost and cost per correct-in-SLO answer;
- Jev feature latency, fallback rate, and a no-Jev ablation;
- calibration of predicted backend quality and latency/SLO probability;
- steady, burst, long-prompt, repeated-prefix, 429, backend-failure, and context-overflow slices.

The replay output is one JSONL record per request. Router traces add the candidate estimates and actual outcome. Streaming traces additionally capture TTFT and client disconnects. Counterfactual offline evaluation and live routed evaluation answer different questions; publish them separately.

## Security and failure behavior

- `SLO_ROUTER_API_KEY` enables router bearer authentication and is required for `/admin/reset`.
- Backend credentials are read from named environment variables and never written to traces.
- Prefix cache identity is tenant-scoped; raw tenant and prompt text are not traced.
- Backends without declared tool support are excluded when tools are requested or the semantic feature path says current external evidence is required.
- Jev errors, timeouts, malformed output, 429s, and overload fall back locally.
- Successful Jev features are cached for the configured TTL with a tenant-scoped, revisioned hash key; cache hits carry zero incremental Jev cost.
- Upstream transport failures return `502`; infeasible routing returns `503`; backend errors are forwarded with a bounded error body.
- A disconnected streaming client closes the upstream response and does not update successful latency history.

## Files

- `slo_router/core.py`: feature extraction, cost/latency estimates, and routing policy.
- `slo_router/service.py`: authenticated OpenAI-compatible proxy, streaming, metrics, and traces.
- `slo_router/matrix.py`: all-backend counterfactual collection and transparent prior fitting.
- `slo_router/replay.py`: arrival-rate replay and policy summaries.
- `slo_router/report.py`: dependency-free Markdown and SVG policy comparison.
- `slo_router/sim_backend.py`: deterministic local verification backends.
- `data/demo.jsonl`: tiny executable fixture, not research evidence.
- `diagrams/slo-router-architecture.excalidraw`: editable system architecture.
- `results/live-jev-analysis.md`: measured OpenRouter integration result and conclusion.
- `results/live-jev-*.jsonl`: replay and trace evidence behind the report.

## Known ceilings

The controller currently uses per-task quality priors, an analytic queue estimate, and exact-match demo grading. It does not yet learn `P(correct | request, backend)` from embeddings, model internals, or response verification. Add a learned calibrator only after a sufficiently large labeled matrix shows that per-task priors leave material regret. The router is process-local; move runtime state to a shared control plane only when multiple router replicas make local observations inconsistent.
