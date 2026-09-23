# Adversarial counter-review: SLO Router experimental evidence

**Review date:** 23 September 2026  
**Review role:** skeptical external reviewer  
**Decision:** acceptable for a clearly labeled engineering demonstration; not yet sufficient for a model-routing research claim or a production-savings claim.

## Executive assessment

The repository demonstrates a real and useful mechanism: an OpenAI-compatible proxy observes in-process demand, estimates whether a configured backend can meet a deadline, and diverts requests from a constrained cheap simulator to a higher-capacity simulator. The checked-in burst result is internally consistent: for the exact ten-request, 400 ms fixture, the SLO policy sends four requests to `cheap` and six to `fast-capacity`, while fixed-cheapest and quality-only send all ten to `cheap`. The live OpenRouter experiment also establishes that the Jev integration worked and, on eight prompts, added substantial synchronous latency without changing a route. Publishing that negative result is a strength.

The evidence does **not** establish that the router identifies the cheapest real LLM that will answer correctly within an SLO. The burst test uses two hard-coded lookup-table servers, two unique prompts repeated five times each, fixed 80 ms service, configured quality priors rather than measured request-level quality, invented token prices, and a queue estimator whose configured decode rate makes each queued cheap request contribute exactly the simulator's 80 ms service time. This is a controlled mechanism test with near-perfect model/simulator alignment. It cannot estimate production savings, real-model quality, general SLO attainment, or the incremental value of Jev.

The video can ship within the current deadline if it says exactly that. A defensible headline is:

> In a deterministic queueing experiment, the SLO-aware policy shifted traffic to spare capacity as the cheap backend queued, meeting all ten 400 ms deadlines while using the expensive tier for only six requests. A separate eight-prompt live Jev integration test added latency and did not change routing decisions.

Do not call the current work a real-model benchmark. Do not say it proves 36% production savings, 100% general SLO attainment, Jev improves routing, or that the router knows whether an answer will be correct.

## Scope and evidence audited

This review inspected the following repository evidence and implementation paths:

- [`README.md`](../../README.md), especially the two experimental result tables and routing claims.
- [`results/video-analysis.md`](../../results/video-analysis.md), [`results/video-replay.jsonl`](../../results/video-replay.jsonl), and [`results/video-traces.jsonl`](../../results/video-traces.jsonl).
- [`results/live-jev-analysis.md`](../../results/live-jev-analysis.md), [`results/live-jev-replay.jsonl`](../../results/live-jev-replay.jsonl), and [`results/live-jev-traces.jsonl`](../../results/live-jev-traces.jsonl).
- Working-tree load, deadline, and arrival sweeps: `results/load-sweep-*`, `results/slo-sweep-*`, and `results/arrival-sweep-*`.
- [`slo_router/core.py`](../../slo_router/core.py), [`slo_router/service.py`](../../slo_router/service.py), [`slo_router/replay.py`](../../slo_router/replay.py), [`slo_router/sim_backend.py`](../../slo_router/sim_backend.py), and [`slo_router/matrix.py`](../../slo_router/matrix.py).
- [`config.video.json`](../../config.video.json), [`data/video-burst.jsonl`](../../data/video-burst.jsonl), and [`data/demo.jsonl`](../../data/demo.jsonl).

At review time, `load-sweep`, `slo-sweep`, and `arrival-sweep` artifacts and `scripts/experiment_sweeps.py` existed only in the working tree. They were not part of the repository's current `HEAD`. The working copy of `results/video-traces.jsonl` had also grown from the 40 records in `HEAD` to 1,671 records because sensitivity runs reused the video's trace path. This provenance issue must be fixed before the new sweeps are cited publicly.

## What the current experiments actually establish

| Finding | Evidence strength | Defensible interpretation |
| --- | --- | --- |
| The proxy, simulator, replay, trace, and report path work end to end | Strong for this code path | Integration behavior is demonstrated locally. |
| Queue-aware selection changes routes under a simultaneous burst | Strong for the exact deterministic fixture | The controller reacts to its observed active count and configured latency model. |
| Ten-request SLO success was 100% for the SLO policy and 40% for quality-only | Strong for one checked-in fixture; repeated summaries exist but raw five-run provenance is incomplete | Exact-fixture result only. |
| Configured predicted cost was 36% below fixed-strongest | Arithmetically correct for the fixture | It is a configured-price result, not a cloud bill or production saving. |
| SLO routing adapts as burst size, deadline, and inter-arrival gap change | Supported by new deterministic sensitivity sweeps | Useful mechanism evidence, still tied to the same simulator assumptions. |
| Jev calls succeeded 16/16 | Supported for those 16 calls | Endpoint integration smoke result, not an availability estimate. |
| Jev did not change routes and increased latency on eight prompts | Supported for this small run | Negative result for this fixture; no conclusion about other workloads. |
| The router predicts request correctness | Unsupported | It reads static per-task priors; it does not estimate request-level correctness. |
| The system improves real-model quality/cost/latency | Unsupported | No real downstream model counterfactual matrix has been published. |

## Major methodological concerns

### 1. The simulator is constructed to match the routing equation

The cheap simulator sleeps for a constant 80 ms and has concurrency one. The router estimates queue delay as:

```text
(waiting + active) × output_token_budget / decode_tokens_per_second
```

For the video fixture, `output_token_budget = 8` and the cheap backend is configured at `100 tokens/s`, so every active request contributes exactly `8 / 100 = 80 ms`. That is the simulator's exact service time. The capacity tier is configured with a 75 ms base latency and a 2,000 tokens/s decode rate while also sleeping for 80 ms. The predictor therefore receives parameters designed to reproduce the simulated service process.

This is appropriate for a unit-style mechanism demonstration. It is circular evidence for predictor quality. Real continuous-batching inference does not serialize requests as identical 80 ms jobs. Prompt length, generated length, batch composition, prefill/decode interference, KV-cache pressure, preemption, hardware, and remaining work all matter. vLLM exposes distinct queue, prefill, decode, time-to-first-token (TTFT), time-per-output-token (TPOT), KV-cache, running-request, and end-to-end metrics precisely because queue length alone is not a sufficient latency model ([vLLM metrics](https://docs.vllm.ai/en/latest/design/metrics/)).

**Required correction:** describe the result as validation of control logic under a calibrated deterministic simulator. A real serving experiment must deliberately fit on one trace and evaluate on different loads, lengths, and arrival processes without reusing the true simulator service constant.

### 2. “Live backend load” is overstated for the burst experiment

During dispatch, the router increments a process-local `runtime.active` counter. The video routing split is driven primarily by this counter. The Prometheus polling path reads only `vllm:num_requests_waiting`, is rate-limited to once per second per backend, and silently retains prior state on polling errors. During a sub-second simultaneous burst, most requests therefore do not receive fresh external queue measurements.

The result proves single-process admission awareness. It does not yet prove routing from live backend telemetry, especially with multiple router replicas or traffic bypassing this proxy. Official vLLM telemetry includes both waiting and running requests plus KV-cache utilization and request timing ([vLLM production metrics](https://docs.vllm.ai/en/latest/usage/metrics/)). The Kubernetes inference-routing protocol likewise standardizes queued requests, running requests, and KV-cache utilization as separate inputs ([model-server metrics proposal](https://github.com/kubernetes-sigs/gateway-api-inference-extension/blob/main/docs/proposals/003-model-server-protocol/README.md)).

**Required correction:** in the video, say “observed in-process load” for this demo. Reserve “live backend load” for an experiment that injects load directly into the backend or through a second router and still routes correctly from externally scraped metrics.

### 3. Quality is fixed by configuration, not learned or evaluated

The video contains only extraction prompts, and both simulators return the same hard-coded correct answer. Accuracy is therefore guaranteed by fixture construction. Backend quality values such as `0.92` and `0.98` are configuration constants. They are not fitted from the video data and have no uncertainty intervals.

The separate eight-prompt fixture is also a lookup table. The fast simulator is explicitly coded to fail three named prompts. This is useful for verifying policy branches but cannot support a model-quality conclusion. Exact match is also unsuitable for unconstrained summaries and explanations; the references are hand-written strings that the simulator returns verbatim.

The repository has a counterfactual matrix collector and a deterministic train/test split, but no published real-model matrix. Its fitted estimator is a per-task Beta posterior mean rather than `P(correct | request, backend)`. With the current five broad task labels, within-task difficulty is invisible.

Large router evaluations use fixed per-prompt/per-model outcomes, task-specific scoring, consistent held-out splits, and explicit best-single and oracle baselines. LLMRouterBench uses 21 datasets, 33 models, more than 400,000 evaluated instances, consistent train/test splits, and dataset-specific evaluators; it also finds that several routers fail to beat the best single model ([LLMRouterBench paper](https://aclanthology.org/2026.findings-acl.1881.pdf)). The scale is not a launch requirement here, but the methodological structure is.

**Required correction:** change “can answer correctly” to “meets a configured quality prior” wherever describing the current implementation. Do not claim quality-aware savings until a held-out real-model matrix exists.

### 4. The baselines are too weak to isolate the novel contribution

For the burst fixture, `quality_only` collapses to fixed-cheapest because every request has the same task and both quality priors clear the floor. Fixed-strongest selects the backend with the highest *mean configured quality over all tasks*, not necessarily the best backend for the current task. The experiment omits:

- round robin;
- least-active or least-queue routing;
- shortest predicted completion time without quality/cost constraints;
- random routing;
- an offline oracle choosing the cheapest route that actually finishes correctly within the SLO;
- the best fixed single backend selected on training data.

This matters because the current result may be attainable by a much simpler least-active rule. LLMRouterBench explicitly compares random, best-single, and oracle references and reports cost savings only when accuracy is no worse than best-single ([evaluation protocol](https://aclanthology.org/2026.findings-acl.1881.pdf)). Its strongest warning applies directly here: a routing method should not receive credit merely for beating a deliberately overloaded cheap baseline.

**Required correction:** add least-active and oracle to the deterministic study. For real-model work, add best-single selected on the training partition and compute a cost-quality-latency frontier.

### 5. The cost result is modeled, not measured

The README table reports “Predicted cost.” It uses the request's `max_tokens` budget rather than actual generated tokens. The simulators emit token counts estimated from character length, and the configured prices are illustrative. The 36% relative reduction is arithmetically valid because all responses have identical usage and the capacity tier is priced at exactly ten times the cheap tier, but it is a property of the chosen price ratio and route counts:

```text
fixed strongest: 10 expensive requests
SLO policy:       4 cheap + 6 expensive requests
relative saving:  1 - (4×1 + 6×10)/(10×10) = 36%
```

No provider billed those completion costs. Jev cost is different: the live response includes usage and billed cost, so that portion is measured.

**Required correction:** label simulator money as “configured token-cost estimate.” Publish actual provider cost only from usage/billing metadata, with model price versions and collection date frozen.

### 6. Tail-latency statistics are unstable at the current sample sizes

With ten requests, the repository's nearest-rank p95 and p99 are both the single maximum observation. With eight Jev-backed requests, the same problem is worse. Repeating the identical deterministic fixture five times improves run-to-run evidence but does not create 50 independent workloads; the effective semantic diversity remains two unique prompts for the video burst.

The claim “five independent runs” is also not fully auditable from the checked-in `video-replay.jsonl`, which contains one ten-request run per policy. The analysis reports the five-run median, but the underlying five raw runs are not preserved in that artifact. New sensitivity sweeps preserve three repeats, which is an improvement, but they still repeat the same hard-coded prompt and service process.

For scale: observing 8/8 successes has a two-sided 95% Wilson lower bound of only about 67.6%; 16/16 has a lower bound of about 80.6%. These intervals are not estimates of production behavior because the samples are not drawn from production, but they illustrate why “all succeeded” is not a reliability claim.

**Required correction:** call maxima “max latency” at `n < 20`, or collect enough requests for tail percentiles. Preserve every repeat, environment, command, seed, and raw trace in a clean experiment-specific artifact.

### 7. The Jev study measures integration overhead, not routing utility

The Jev run is candidly labeled as an integration measurement, which is correct. Its limits are:

- only eight prompts;
- no held-out ground-truth labels for Jev's task, exactness, or external-evidence decisions;
- no repeated Jev calls per prompt to measure output variance;
- no confidence calibration, Brier score, expected calibration error, or threshold study;
- no route changes relative to the lexical path, so incremental routing value is exactly zero on the fixture;
- policy runs occur in a fixed sequence rather than randomized or counterbalanced order;
- remote service variation is confounded with policy differences;
- a single cache pair and 16 successful calls do not characterize cache effectiveness, availability, fallback rate, 429 behavior, or timeout behavior.

The observed policy tails themselves expose external variance: the eight `quality_only` Jev requests have p95 1,296 ms, while the eight `slo` Jev requests have p95 490 ms, despite both making the same kind of Jev decision call and producing the same route split. A single small run cannot distinguish warm-up, provider load, connection reuse, execution order, or random service variation.

TypeSafe states that Jev probabilities are calibrated over groups and do not guarantee any individual decision ([System One documentation](https://docs.typesafe.ai/concepts/system-one)). OpenRouter likewise recommends choosing thresholds from workload-specific labeled data and the cost of mistakes ([Jev routing guidance](https://openrouter.ai/blog/tutorials/jev-vs-llm-when-to-use-each/)). OpenRouter also notes that probabilities can vary across calls to the same state ([Jev technical guide](https://openrouter.ai/blog/insights/what-is-jev/)).

**Required correction:** retain the negative result. Do not imply that Jev improved selection. A meaningful Jev claim requires a labeled feature dataset, repeated calls, calibration analysis, route-flip analysis, and end-to-end utility after its latency and cost.

### 8. Latency “probability” is an uncalibrated score

The router converts predicted latency to `slo_probability` with a logistic function. Before ten history samples, uncertainty is `max(100 ms, 25% of predicted latency)`; afterward it is `max(50 ms, p90 - p50)` over recent latencies. No calibration experiment shows that requests assigned 0.8 probability meet the SLO 80% of the time. History also mixes end-to-end latency, including semantic-feature overhead, with backend behavior.

The new sweeps add latency mean absolute error, which is useful, but MAE alone does not validate a probability. The release needs reliability bins or Brier/log loss, broken down by backend, load, prompt length, output length, and SLO target. It should also compare the analytic model with a trivial empirical baseline.

**Required correction:** call this value a “feasibility score” until calibrated on held-out traffic. If it remains named a probability, publish calibration plots and coverage.

### 9. The SLO is underspecified for streaming inference

The current non-streaming experiment uses end-to-end completion latency. The streaming path records first received chunk as TTFT, but it does not compute TPOT. In LLM serving, user-facing objectives commonly separate TTFT, TPOT/inter-token latency, and end-to-end latency. vLLM exposes each separately ([vLLM metrics](https://docs.vllm.ai/en/latest/design/metrics/)); DistServe defines goodput as the maximum request rate served while meeting both TTFT and TPOT constraints ([DistServe](https://arxiv.org/abs/2401.09670)).

**Required correction:** state that the current SLO is full-response latency for short non-streaming responses. Real streaming experiments must report TTFT and TPOT separately and define whether a request succeeds only when both objectives are met.

### 10. Trace privacy language needs tighter wording

Raw prompts are absent from decision traces, which is good. However, plain SHA-256 prompt and tenant hashes are pseudonymous identifiers, not anonymization. Short or predictable prompts and tenant names can be guessed and hashed offline. Repeated prompts remain linkable.

**Required correction:** say “raw prompts are omitted” rather than implying the hash makes prompts private. Use tenant-scoped HMAC with a secret key for production traces, and document retention and rotation.

## Review of the new sensitivity sweeps

The working-tree sweeps materially improve the mechanism story:

- **Burst size:** across three runs, SLO routing stays at 100% through bursts of 20 and reaches 97.5%–100% at 40, while quality-only falls from 100% at one request to 10% at 40.
- **Deadline:** for ten simultaneous requests, the SLO policy shifts more traffic to capacity as the target tightens from 800 ms to 150 ms; the configured predicted cost rises accordingly.
- **Arrival interval:** at 80–120 ms spacing, the cheap single-slot backend keeps up and both policies converge to the cheap route; at 0–40 ms spacing, SLO routing buys capacity.

These are the right qualitative sensitivity checks: the policy reacts only when congestion or a tighter deadline creates a need. They also reveal a useful negative boundary: at burst 40, one run misses one deadline, so “100% SLO attainment” is not stable even in the simulator.

Their remaining limitations are unchanged: one unique lookup-table prompt per sweep, three repeats, calibrated deterministic service, no real token generation, no external-load source, no stronger scheduling baseline, and configured rather than billed cost. Before publication, the sweep script and its consolidated raw artifacts must be committed, and each run must write to an experiment-specific trace instead of appending to `video-traces.jsonl`.

## Minimum additional experiments before release

### Release gate A: one-hour walkthrough video

The video can be released as a controlled engineering demo after these minimum checks:

1. **Clean provenance:** regenerate the video result and each sweep into separate files; ensure `video-traces.jsonl` contains only the video run. Commit the exact script, configuration, raw JSONL, summaries, and run date.
2. **Use precise labels:** rename “Predicted cost” to “Configured token-cost estimate”; label every simulator table “deterministic simulated backends.”
3. **Show the sensitivity result:** include one compact table or chart showing burst 1/5/10/20/40 and the 97.5%–100% result at burst 40. This prevents cherry-picking the ten-request point.
4. **Show one simpler baseline:** add least-active or least-queue. If it matches the SLO policy, say so; the value of this repository is then the constrained cost/quality/SLO framework and traceability, not a claim that the scheduling rule is uniquely strong.
5. **Preserve the Jev negative result:** state that live Jev added latency and did not change routes on eight prompts. Avoid claims about Jev accuracy or reliability.
6. **Run a reproducibility check:** from a clean checkout, execute tests and the demo command once, compare generated summary values within a declared timing tolerance, and record Python/OS versions.

Nothing else is required to publish a truthful mechanism walkthrough.

### Release gate B: call it an “experimental study of LLM routing”

Before using that stronger description, complete the following minimum study:

#### Experiment 1: real-model counterfactual quality matrix

- At least two pinned real completion models with materially different price/capability.
- At least 200 held-out prompts spanning four task families; 500+ is preferable if claims are broken down by task.
- Run every prompt on every backend before evaluating routing.
- Freeze prompts, model revisions, temperatures, max tokens, tool settings, provider, and collection dates.
- Use task-appropriate executable scoring for math/code/extraction and blinded human or independently validated judging for open responses.
- Split by unique prompt or source group, never by duplicated variants; fit priors only on training data.
- Report per-model, best-single, random, routed, and oracle quality; report route recall when only one backend is correct.

#### Experiment 2: real serving-load study

- Use vLLM or another instrumented real inference server.
- Evaluate burst and steady arrivals at low, medium, high, and saturation-adjacent offered load.
- Mix short/long prompts and short/long outputs; include repeated and non-repeated prefixes.
- Use at least 1,000 completed requests per operating point or run each point long enough to obtain stable tails; repeat each point at least three times.
- Compare fixed-cheapest, best-single/strongest, round robin, least-queue, shortest-predicted-completion, and SLO-aware routing.
- Report throughput, failure rate, TTFT p50/p95/p99, TPOT p50/p95/p99, end-to-end latency, and goodput under explicit SLOs.
- Inject background load outside the router process to test whether external telemetry, not local active counts, drives correct decisions.

#### Experiment 3: Jev feature and utility study

- Label at least 200 prompts for task, exactness, and external-evidence need.
- Call the pinned Jev snapshot at least three times per prompt or enough to estimate decision variance.
- Report accuracy/F1 for choice labels, Brier score and calibration error for probabilities, route-flip rate, latency distribution, cache-hit rate, fallback rate, and billed cost.
- Compare Jev, lexical features, and a no-feature baseline on the same downstream counterfactual matrix.
- Measure incremental correct-in-SLO answers per dollar and per millisecond. If Jev does not move the Pareto frontier, keep it optional and off the synchronous default path.

#### Experiment 4: failure and stale-state behavior

- Inject backend 429, 5xx, connection timeout, slow response, and crash.
- Inject Jev timeout, 429, malformed response, and high latency.
- Stop or delay metrics updates and add load through another client/router.
- Measure error rate, fallback correctness, retry amplification, deadline misses, recovery time, and whether requests are sent to a backend marked healthy from stale data.

### Statistical reporting contract

For every public result:

- preserve request-level raw data and environment metadata;
- use paired evaluation on the same prompts and arrival traces;
- randomize or counterbalance policy execution order for remote services;
- report confidence intervals clustered by prompt or run, rather than treating duplicate requests as independent;
- report all failures in denominators;
- separate model-quality uncertainty, routing uncertainty, and timing variance;
- distinguish configured/predicted cost from actual billed cost;
- present the cost-quality-latency Pareto frontier, not one selected operating point.

This follows the direction of contemporary routing evaluation. RouteLLM evaluates explicit cost-quality tradeoffs on held-out benchmarks ([RouteLLM](https://arxiv.org/abs/2406.18665)); LLMRouterBench standardizes train/test splits, per-model outcomes, multiple baselines, best-single comparison, oracle comparison, and Pareto analysis ([LLMRouterBench](https://aclanthology.org/2026.findings-acl.1881.pdf)); FrugalGPT learns cascades against empirical response quality rather than configured quality constants ([FrugalGPT](https://arxiv.org/abs/2305.05176)).

## Claim-by-claim release guidance

| Proposed claim | Decision | Safer wording |
| --- | --- | --- |
| “Built an SLO-aware inference router” | Accept | The implementation applies a configured quality floor and latency-feasibility score under observed load. |
| “Uses Jev as a model for model decisions” | Qualify | Jev supplies typed task/exactness/evidence features; deterministic controller code selects the backend. |
| “Selects the cheapest model that can answer correctly within the SLO” | Reject | Selects the lowest configured-cost eligible backend whose static quality prior and estimated latency clear configured thresholds. |
| “Achieved 100% SLO success” | Qualify | Achieved 10/10 within 400 ms in the selected deterministic burst fixture; sensitivity sweeps reached 97.5%–100% at burst 40. |
| “Reduced cost by 36%” | Qualify | Used 36% less configured token cost than fixed-capacity routing in the ten-request simulator fixture. |
| “Jev improves routing” | Reject | Jev did not change a route on the eight-prompt fixture and increased latency. |
| “Live-load aware” | Qualify | Single-process active-count aware in the demo; external queue telemetry support exists but is not isolated by the current experiment. |
| “Privacy-preserving hashed traces” | Qualify | Traces omit raw prompts and store linkable SHA-256 identifiers; production should use keyed HMAC. |
| “Production-ready” | Reject | No real-model, real-serving, multi-replica, security, or failure-injection evidence yet. |

## Recommended video narrative

1. State that the study separates **control-plane behavior** from **model quality**.
2. Show the exact two-backend simulator and explain its deliberately controlled service times.
3. Run the ten-request burst and show the route split, deadline attainment, and configured cost.
4. Show the burst/deadline/arrival sensitivity table, including the burst-40 miss.
5. Show one decision trace and call the latency value an estimate or feasibility score.
6. Show the live Jev negative result: successful integration, no route changes, additional latency.
7. Close with the next scientific step: a frozen real-model counterfactual matrix and real vLLM load test.

That story is technically credible because it makes the experiment boundary visible instead of hiding it.

## Evidence registry

| ID | Source | Type | Quality | Use in this review |
| --- | --- | --- | --- | --- |
| R1 | [SLO Router repository artifacts](../../README.md) | Primary project evidence | A for what this repository did | Current claims, commands, and result tables |
| R2 | [LLMRouterBench](https://aclanthology.org/2026.findings-acl.1881.pdf) | Peer-reviewed primary research | A | Baselines, held-out splits, per-model matrices, Pareto evaluation, evidence that routers can fail to beat best-single |
| R3 | [RouteLLM](https://arxiv.org/abs/2406.18665) | Primary research/preprint | A- | Cost-quality routing framing and held-out benchmark comparison |
| R4 | [FrugalGPT](https://arxiv.org/abs/2305.05176) | Primary research/preprint | A- | Empirical cascade evaluation and cost-quality tradeoff |
| R5 | [vLLM metrics](https://docs.vllm.ai/en/latest/design/metrics/) | Official technical documentation | A | Required queue, KV, TTFT, TPOT, and end-to-end serving measurements |
| R6 | [Kubernetes inference model-server protocol](https://github.com/kubernetes-sigs/gateway-api-inference-extension/blob/main/docs/proposals/003-model-server-protocol/README.md) | Official project specification | A- | Distinct queued, running, and KV-cache metrics for inference routing |
| R7 | [DistServe](https://arxiv.org/abs/2401.09670) | Primary systems research | A- | TTFT/TPOT SLOs and goodput framing |
| R8 | [TypeSafe System One documentation](https://docs.typesafe.ai/concepts/system-one) | Vendor primary documentation | B+ | Jev typed outputs and group-level calibration limitation |
| R9 | [OpenRouter Jev technical guide](https://openrouter.ai/blog/insights/what-is-jev/) | Vendor primary documentation | B | Endpoint behavior, cost, and repeated-call probability variation |
| R10 | [OpenRouter Jev routing guide](https://openrouter.ai/blog/tutorials/jev-vs-llm-when-to-use-each/) | Vendor primary documentation | B | Workload-specific threshold guidance |

## Final verdict

The repository has enough evidence for a compelling, honest walkthrough of a queue-aware constrained router and a live Jev integration with a negative latency result. The new load, deadline, and arrival sweeps make that mechanism demonstration substantially stronger.

The project does not yet have the empirical foundation for claims about real LLM correctness, production savings, calibrated SLO probability, Jev routing benefit, or production reliability. The minimum path to that stronger claim is a held-out all-model counterfactual matrix, a real instrumented serving-load study with stronger baselines, and a labeled Jev calibration/utility study. Until then, the simulator result should remain explicitly framed as a controlled systems demonstration.
