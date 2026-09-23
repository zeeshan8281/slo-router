# SLO Router: An Evidence Audit and Evaluation Plan for Cost-Aware, Deadline-Constrained LLM Routing

**Review date:** 23 September 2026  
**Artifact scope:** repository state inspected on the review date  
**Evaluation status:** controlled systems prototype; real-model validation outstanding

## Abstract

SLO Router is an OpenAI-compatible proxy that chooses among language-model backends by minimizing configured request cost subject to a task-level quality floor and a predicted probability of meeting a latency service-level objective (SLO). Its controller combines deterministic or Jev-derived semantic features, configured per-task quality priors, an analytic prefill/decode latency model, local or scraped queue state, context and tool constraints, and backend health. The repository includes a counterfactual matrix collector, prior fitter, arrival-time replay harness, deterministic backends, prompt-free decision traces, and dependency-free reports.

The checked-in evidence establishes three narrow claims. First, the complete proxy and retry/streaming paths are executable and covered by five passing tests. Second, under a deterministic burst fixture, queue-aware routing moves traffic from a saturated cheap backend to an idle, higher-cost backend and increases deadline attainment from 40% to 100% for ten simultaneous requests, while its configured predicted cost is 36% below the all-strong baseline. Third, a live Jev 1.13 ablation shows that synchronous semantic classification adds substantial latency and cost without changing a route on the eight-request fixture: SLO-aware p95 rises from 77.93 ms to 490.38 ms, approximately 6.3 times.

These results validate mechanism, not production utility. Completion backends are deterministic simulators; quality priors, prices, service rates, and answers are fixture inputs; exact-match grading covers eight unique prompts; and no experiment calibrates predicted SLO probability or quality on real models. The strongest publication path is therefore a reproducible multi-model evaluation that reports quality and latency calibration, regret against a counterfactual oracle, correct-within-SLO goodput, actual billed cost, and robustness under burst, steady-state, long-context, prefix-reuse, outage, and distribution-shift workloads.

## 1. Research question and positioning

The system addresses a joint optimization problem:

> For each request, select the least expensive eligible backend whose expected answer quality exceeds a caller-specified floor and whose probability of completing within the latency deadline exceeds a configured threshold.

This places SLO Router between two research lines. Model routers such as RouteLLM learn a quality/cost decision from preference data, while FrugalGPT studies cascades that trade model cost against task performance ([RouteLLM](https://proceedings.iclr.cc/paper_files/paper/2025/file/5503a7c69d48a2f86fc00b3dc09de686-Paper-Conference.pdf); [FrugalGPT](https://arxiv.org/abs/2305.05176)). Serving systems such as vLLM, DistServe, and Splitwise optimize execution, memory, placement, or phase-specific latency inside an inference fleet ([vLLM/PagedAttention](https://doi.org/10.1145/3600006.3613165); [DistServe](https://www.usenix.org/system/files/osdi24-zhong-yinmin.pdf); [Splitwise](https://www.microsoft.com/en-us/research/wp-content/uploads/2023/12/Splitwise_ISCA24.pdf)). SLO Router's distinct intended contribution is a transparent request-level controller that combines semantic eligibility with live load and an explicit deadline probability, while remaining compatible with heterogeneous OpenAI-style endpoints.

That contribution is plausible and useful, but the current artifact demonstrates it only in a controlled simulator. It should presently be described as a tested routing prototype and experimental harness.

## 2. System under review

### 2.1 Decision path

For a request with backend \(b\), estimated input tokens \(n_{in}\), output budget \(n_{out}\), and deadline \(D\), the implementation computes an interpretable latency estimate:

\[
\hat{L}_b = L^{base}_b
 \frac{1000\,n_{in}^{uncached}}{r^{prefill}_b}
 \frac{1000\,n_{out}}{r^{decode}_b}
 \frac{1000\,(q_b+a_b)n_{out}}{r^{decode}_b}
 L^{feature},
\]

where \(q_b\) and \(a_b\) are observed waiting and active counts. A recent tenant-scoped system/developer prefix reduces modeled prefill work to 55% of its original size. The SLO probability is a logistic transform of \((D-\hat{L}_b)\), with uncertainty derived from the backend's recent p50-to-p90 latency spread after ten observations and from a fixed heuristic before then.

Each candidate is rejected if unhealthy, context-ineligible, or lacking required tool capability. The SLO policy then filters candidates by configured task quality and predicted deadline probability and selects minimum predicted token cost. Exactness at or above 0.8 raises the quality floor to at least 0.85. When no candidate is feasible, the API returns an explicit 503 rather than choosing a backend that violates the declared constraints.

### 2.2 Semantic features

The local classifier maps request text into five task classes using regular expressions and assigns coarse exactness and external-evidence values. The optional remote path calls OpenRouter's Decisions API with `typesafe/jev-1.13` for typed task, exactness, and evidence decisions. Calls are bounded by a timeout, fall back to the lexical path, and may be cached by question revision, tenant, and messages.

This design makes semantic routing failure-bounded and auditable. It does not yet estimate request-specific backend correctness. The candidate quality value is a backend/task table lookup, so two requests assigned to the same task have identical predicted quality on a backend regardless of difficulty or distribution shift.

### 2.3 Runtime state and failure handling

The proxy tracks process-local active requests, recent latencies, and prefix keys. It can scrape `vllm:num_requests_waiting` once per second from a configured metrics endpoint. Transport failures, HTTP 429, and HTTP 5xx mark a backend unavailable for five seconds and trigger selection among the remaining prepared candidates. Non-retryable backend errors are forwarded with a bounded response body. Streaming traces include time to first byte and client disconnect state; disconnected streams are excluded from successful latency history.

The code's trace contract is unusually useful for evaluation: it records hashed prompt and tenant identity, feature values, every candidate's estimate, the chosen route, actual latency, SLO outcome, and cost inputs without storing raw prompts.

## 3. Evidence inventory and claim audit

The table distinguishes what is directly supported by checked-in artifacts from what remains a hypothesis.

| Claim | Evidence | Assessment |
| --- | --- | --- |
| The proxy, controller, simulator, and core failure paths execute | `tests/test_core.py`; 5/5 tests passed on review | **Supported as a small functional test suite.** It is not a load or fault-injection validation. |
| Queue-aware routing reacts to saturation | Ten-request burst routes 4 requests to `cheap` and 6 to `fast-capacity`; five stated verification runs have identical route/SLO outcomes | **Supported for the deterministic fixture.** |
| SLO routing improves deadline attainment over quality-only routing | At 400 ms, 100% versus 40% for the ten-request burst; load sweep sustains 100% through burst 20 and 97.5–100% at burst 40 | **Supported for simulated service times and capacities.** |
| SLO routing is cheaper than always using the strong tier | $0.0003392 versus $0.0005300 predicted cost in the ten-request burst, a 36% reduction | **Supported arithmetically for configured token prices.** No invoice or real provider cost validates the amount. |
| The controller adapts monotonically to load | Strong-tier routes increase from 0/1 at burst 1 to 36/40 at burst 40 | **Supported in the load sweep.** |
| The controller adapts to tighter deadlines | Strong-tier routes change from 1/10 at 800 ms to 9/10 at 150 ms | **Supported in the SLO sweep.** |
| Live Jev integration works | 16/16 Jev-backed calls succeeded; provider/model resolution and typed decisions are recorded in the analysis | **Supported as a dated integration result.** The upstream alpha endpoint may change. |
| Jev improves routing quality | No route or accuracy changed relative to `slo_no_jev` on eight prompts | **Unsupported; current evidence is negative.** |
| Quality constraints improve real answer correctness | Deterministic backends deliberately return fixed answers and configured quality priors are not fitted from a real matrix | **Not tested.** |
| Predicted SLO probabilities are calibrated | Candidate probabilities are traced, but no reliability curve, Brier score, ECE, or held-out calibration result is reported | **Not tested.** |
| Prefix reuse prediction represents backend cache behavior | A 45% prefill discount is hard-coded after a local prefix observation | **Not tested against actual prefix-cache metrics.** |
| The router improves production cost/goodput | No real completion models, GPU endpoints, billed costs, or sustained offered-load experiment | **Not supported.** |

## 4. Reanalysis of checked-in results

### 4.1 Burst and load scaling

The load sweep contains three repetitions per burst size for `quality_only` and `slo_no_jev`. Both policies are 100% accurate because the selected simulated backends return the same correct answers on the extraction fixture.

| Burst | Quality-only SLO success | SLO-aware SLO success | Quality-only median p95 | SLO-aware median p95 | SLO-aware route mix |
| ---: | ---: | ---: | ---: | ---: | --- |
| 1 | 100% | 100% | 87.29 ms | 86.24 ms | cheap 1 |
| 5 | 80% | 100% | 411.67 ms | 330.98 ms | cheap 4, capacity 1 |
| 10 | 40% | 100% | 820.20 ms | 335.75 ms | cheap 4, capacity 6 |
| 20 | 20% | 100% | 1569.17 ms | 274.12 ms | cheap 4, capacity 16 |
| 40 | 10% | 99.17% mean | 3101.86 ms | 291.05 ms | cheap 4, capacity 36 |

This is the clearest evidence for the controller. The cheap backend's one-slot capacity causes deadline attainment to fall almost inversely with burst size. The SLO policy consistently admits about four requests to the cheap tier under a 400 ms deadline and spills the rest to the 16-slot tier. At burst 40, one of 120 SLO-aware requests misses the deadline, producing a 97.5–100% range across repetitions.

The result is mechanism-valid because the experimental construction directly induces queueing. Its external validity is limited because every request arrives at exactly the same time, every request has the same small output budget, and both backends sleep for the same fixed 80 ms service time. Real inference has prompt- and output-dependent service distributions, iteration-level batching, preemption, and correlated cold starts.

### 4.2 Deadline sensitivity

With burst size fixed at ten, the deadline sweep shows the intended control response.

| SLO target | Quality-only mean success | SLO-aware mean success | SLO-aware route mix | SLO-aware configured cost |
| ---: | ---: | ---: | --- | ---: |
| 150 ms | 10.0% | 100% | cheap 1, capacity 9 | $0.0004823 |
| 250 ms | 23.3% | 100% | cheap 2, capacity 8 | $0.0004346 |
| 400 ms | 40.0% | 100% | cheap 4, capacity 6 | $0.0003392 |
| 800 ms | 90.0% | 100% | cheap 9, capacity 1 | $0.0001007 |

The route mix changes monotonically in the expected direction: looser deadlines permit more use of the cheap serial backend. This is stronger than showing a single favorable operating point. However, all four targets are evaluated against the same simulator and only three repetitions, so confidence intervals would add little statistical meaning; more importantly, the workload lacks real latency variance.

### 4.3 Live Jev ablation

The live integration experiment uses eight labeled requests and deterministic local completion backends.

| Policy | Feature path | Accuracy | p50 | p95 | Predicted total cost | Routes |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| Fixed cheapest | lexical | 62.5% | 28.58 ms | 35.64 ms | $0.00013140 | fast 8 |
| Fixed strongest | lexical | 100% | 69.23 ms | 69.47 ms | $0.00131400 | strong 8 |
| Quality only | live Jev | 100% | 777.64 ms | 1296.30 ms | $0.00086016 | fast 4, strong 4 |
| SLO-aware | lexical | 100% | 56.10 ms | 77.93 ms | $0.00071190 | fast 4, strong 4 |
| SLO-aware | live Jev | 100% | 436.99 ms | 490.38 ms | $0.00086016 | fast 4, strong 4 |

Jev and the lexical classifier disagree on three task labels, including both arithmetic prompts, but exactness raises the quality floor and preserves the same routes. The experiment therefore supplies an important negative result: synchronous Jev consumes $0.00014826 in incremental predicted cost for the eight SLO requests and multiplies p95 by about 6.3 without observable benefit. The correct conclusion is workload-specific. A longer generation workload could amortize feature latency, and a more heterogeneous corpus could reveal routing improvements that eight prompts cannot.

### 4.4 Artifact integrity observation

The checked-in `results/video-traces.jsonl` currently contains 736 records: 40 from the four-policy video replay, 456 from the load sweep, and 240 from the deadline sweep. The count exactly matches the union of those experiments. The replay result files themselves remain separable, but the trace filename is shared and appended across runs. A publication artifact should assign an immutable run ID and write each experiment to a fresh directory or manifest. Without that change, a reader cannot safely treat `video-traces.jsonl` as the trace set for only the ten-request video experiment.

## 5. Methodological risks

### 5.1 Construct validity

**Quality.** Exact string equality is suitable for the deliberately tiny extraction/arithmetic fixture. It is not a valid general measure for summarization, reasoning, or debugging. The simulator's strong and weak behavior is encoded in a prompt-to-answer dictionary, so measured “accuracy” is a property of the fixture rather than a model.

**Cost.** Reported experiment cost is predicted from configured rates and token estimates. Actual cost is computed in traces when usage exists, but no result table compares predicted cost with provider billing. Claims should continue to say “configured predicted cost” until reconciled against invoices or endpoint accounting.

**Latency SLO.** Replay measures end-to-end completion latency, which is appropriate for non-streaming requests. For streaming generation, the system traces TTFT but lacks TPOT/inter-token latency and separate TTFT/TBT constraints. DistServe formalizes why these phase-specific SLOs matter for LLM serving; one total-duration deadline can conceal poor interactive behavior.

### 5.2 Internal validity

The same configured prefill/decode rates influence routing and were chosen to match the simulated topology. This is sufficient for an integration test but risks circularity in an evaluation: an estimator built from the fixture is then rewarded for fitting the fixture. Real experiments must fit rate and uncertainty parameters on a disjoint calibration period and freeze them before test traffic.

The router increments local `active` only after selection. Under high concurrent admission, several requests can prepare candidates from nearly the same state. The simulator's polled waiting metric and event-loop ordering produce the desired split, but a real multi-worker deployment may observe stale or inconsistent queue state. This is a central system property to measure, especially because runtime state is process-local.

The five-second backend quarantine is fixed, and retry candidates reuse the estimates prepared before the failed attempt. The retry path therefore does not re-estimate remaining deadline budget or changed queue state. Fault experiments should report whether retries meet the original SLO and should distinguish successful completion from successful completion within deadline.

### 5.3 External validity

No checked-in experiment uses a real completion model or GPU serving engine. Results therefore do not cover batching interference, tokenizer variance, KV-cache pressure, long-context prefill, variable output length, speculative decoding, quantization, model warmup, provider rate limits, or network-region effects. These are precisely the mechanisms that make real LLM latency heavy-tailed.

The task taxonomy has only five coarse classes and the fitted prior is constant within each class. RouteLLM's learned request-level routers provide a natural comparison because they model preference at prompt granularity. A fair study should ask whether SLO Router's transparent prior is competitive when live load matters, and whether a learned quality score adds value beyond the task table.

### 5.4 Statistical conclusion validity

The main burst claim is repeated five times, while sweeps use three repetitions. Deterministic simulators make those repetitions useful as stability checks but weak as statistical evidence. A live study should use enough independent runs to bootstrap confidence intervals across run seeds or time windows. Per-request samples from the same burst are correlated and must not be treated as independent replicates.

## 6. Experiments required for a publication-quality evaluation

### E1. Real-model counterfactual quality matrix

Freeze 1,000–5,000 requests spanning extraction, summarization, reasoning, code debugging, tool use, and an “other” slice. Run every request on every backend with pinned model revisions, prompts, temperatures, and max-token budgets. Use executable graders for exact tasks, reference-aware semantic metrics plus blinded human checks for open-ended tasks, and pass@k or unit tests for code. Fit priors only on the training split; report held-out accuracy, AUROC for correctness, Brier score, expected calibration error (ECE), and calibration diagrams.

Backends should include at least three capability/cost tiers. A practical initial matrix could use one small open model, one larger open model on vLLM, and one frontier API. Record actual usage and billed cost. The goal is not to prove one model hierarchy; it is to create genuine per-request disagreement for evaluating the router.

### E2. Policy comparison under identical traffic

Compare:

1. fixed cheapest;
2. fixed strongest;
3. random route with matched strong-tier fraction;
4. quality-only per-task prior;
5. SLO Router without Jev;
6. SLO Router with cached/offline semantic features;
7. a learned quality router such as RouteLLM or a simple logistic baseline;
8. an oracle that selects the cheapest backend known counterfactually to be correct and within SLO.

Primary outcomes should be correct-within-SLO rate, cost per correct-within-SLO response, and normalized regret relative to the oracle. Secondary outcomes are p50/p95/p99 TTFT, TPOT, end-to-end latency, route mix, failure rate, and retry rate.

### E3. Arrival-process and load sweep

Use both open-loop Poisson arrivals and trace-driven burst arrivals. Sweep offered load from 10% to beyond saturation for each backend mix. An open-loop generator is essential because closed-loop clients reduce offered load when latency rises and can make overloaded systems look stable. Report goodput as completed-and-correct requests satisfying the SLO per second, following the SLO-aware framing used in DistServe.

At each load point, use at least five independent runs long enough to reach steady state after warmup. Report bootstrap 95% confidence intervals over runs. Preserve per-request correlations by resampling runs or time blocks rather than individual requests.

### E4. Latency-model calibration

For each backend and workload slice, compare predicted and observed latency with median absolute error, p90 absolute percentage error, and interval coverage. For SLO probability, report Brier score, ECE, and a ten-bin reliability diagram. Break results down by prompt length, output length, queue depth, prefix hit/miss, and backend.

This experiment should separately test:

- the analytic prefill/decode equation;
- cold-start versus warm execution;
- waiting metrics versus process-local active counts;
- the first-ten-request uncertainty heuristic;
- the 45% prefix discount;
- calibration drift after a load or model change.

### E5. Failure and stale-state robustness

Inject backend connection failures, 429s, 5xx responses, malformed JSON, slow streams, and mid-stream disconnects. Vary outage duration around the five-second quarantine. Run the router with multiple worker processes to quantify disagreement caused by process-local health, latency history, and prefix state. Measure completion rate, correct-within-SLO rate, duplicate work, retry overhead, and recovery time.

### E6. Jev value and placement

Evaluate lexical, synchronous Jev, cached Jev, and offline/precomputed Jev features on the real matrix. Report task classification macro-F1, exactness/evidence calibration, route-change rate, quality lift among changed routes, incremental cost, and added p95. Stratify by generation duration to test whether longer requests amortize semantic overhead. The current negative result makes synchronous Jev a challenger rather than the default.

### E7. Long-context and prefix reuse

Sweep prompt lengths from 128 tokens to each backend's context boundary and use tokenizer-exact counts per model family. For repeated system prefixes, measure actual prefill reduction and cache-hit evidence at the backend. Compare the hard-coded 55% uncached-token assumption against observed TTFT and use a no-discount ablation.

## 7. Publication tables

### Table 1: End-to-end policy frontier

| Policy | Correct (%) | SLO met (%) | Correct within SLO (%) | p95 TTFT (ms) | p95 E2E (ms) | Actual cost / 1k req | Cost / correct-in-SLO | Oracle regret |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Fixed cheapest | | | | | | | | |
| Fixed strongest | | | | | | | | |
| Quality only | | | | | | | | |
| Learned quality router | | | | | | | | |
| SLO Router | | | | | | | | |
| Counterfactual oracle | | | | | | | | 0 |

This is the main paper table. It must use real endpoints and actual cost.

### Table 2: Quality calibration by task and backend

| Backend | Task | Test n | Accuracy | Predicted quality | Brier | ECE | 95% CI |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |

This table reveals whether coarse per-task priors are trustworthy and where a learned request-level estimator is justified.

### Table 3: Robustness and ablations

| Variant | Correct-in-SLO | p95 | Cost | Route changes | Failure recovery |
| --- | ---: | ---: | ---: | ---: | ---: |
| Full controller | | | | | |
| No live queue | | | | | |
| No latency history | | | | | |
| No prefix discount | | | | | |
| Lexical features | | | | | |
| Synchronous Jev | | | | | |
| Cached/offline Jev | | | | | |

## 8. Publication figures

1. **Cost–quality–SLO Pareto frontier.** Scatter plot with actual cost per 1,000 requests on the x-axis and correct-within-SLO rate on the y-axis. Marker shape identifies policy and color identifies offered load. Connect operating points for policies with tunable thresholds.

2. **Goodput versus offered load.** Lines for every policy; x-axis is offered requests/s and y-axis is correct requests/s meeting both TTFT and TPOT/E2E SLOs. Add 95% bootstrap bands and a vertical line at each backend pool's empirical saturation point.

3. **SLO reliability diagram.** Bin predicted deadline probability and plot observed attainment. Include the identity line, sample count per bin, Brier score, and ECE. Facet by backend and warm/cold state.

4. **Latency prediction residuals.** Predicted versus observed latency with a log scale and identity line, plus a residual panel grouped by prompt length, output length, and queue depth. This directly tests the controller rather than only downstream policy outcomes.

5. **Routing heatmap.** Deadline on one axis, offered load on the other, and fraction routed to each tier as fill color. The checked-in deadline/load sweeps already suggest a monotonic pattern; real-model results would show whether it survives noisy latency.

6. **Jev incremental-value plot.** For requests whose route changes under Jev, plot quality change against added latency and cost. Requests with unchanged routes should be shown separately because they measure pure overhead.

7. **Failure timeline.** Time series of backend health, offered load, selected routes, p95 latency, and SLO attainment around injected outages and recovery.

Every plot should publish its source CSV/JSONL, generation script, run manifest, and exact commit/model identifiers.

## 9. Reproducibility checklist

- Pin repository commit, Python dependencies, model revisions, tokenizers, serving-engine versions, GPU types, regions, and provider prices.
- Store one immutable manifest per run with random seed, offered-load process, SLO, quality floor, backend configuration, Jev question revision, and wall-clock interval.
- Write traces to a fresh run directory; do not append unrelated experiments to a shared filename.
- Separate warmup from measurement and disclose cache state.
- Reset router and backend state between policy comparisons, then randomize policy order across repetitions.
- Publish raw counterfactual outputs subject to dataset licenses and privacy constraints.
- Use tokenizer-exact input counts for context eligibility and cost accounting.
- Report both configured predicted cost and actual measured/billed cost.
- Record unsuccessful and infeasible requests in denominators; avoid conditioning latency only on successes without a parallel failure metric.
- Generate tables and figures from raw artifacts in one scripted command.

## 10. Overall assessment

SLO Router is a coherent, compact prototype with a stronger evidence discipline than its size suggests. It exposes assumptions in configuration, rejects infeasible requests explicitly, records candidate-level decisions, supplies deterministic end-to-end reproduction, and includes a negative Jev result rather than obscuring it. The load and deadline sweeps demonstrate the intended controller response cleanly.

The current evidence does not establish that the controller reduces cost while preserving quality and latency on real LLM workloads. The paper-worthy contribution will come from calibrating the transparent controller on a counterfactual real-model matrix, comparing it against learned and fixed baselines, and measuring correct-within-SLO goodput under open-loop load. Until those experiments exist, the defensible claim is narrower: the artifact implements and validates an SLO-constrained routing mechanism under controlled conditions, and it provides most of the instrumentation needed for the real evaluation.

## References

1. Chen, L., Zaharia, M., and Zou, J. “FrugalGPT: How to Use Large Language Models While Reducing Cost and Improving Performance.” TMLR, 2024. <https://arxiv.org/abs/2305.05176>
2. Kwon, W. et al. “Efficient Memory Management for Large Language Model Serving with PagedAttention.” SOSP, 2023. <https://doi.org/10.1145/3600006.3613165>
3. Ong, I. et al. “RouteLLM: Learning to Route LLMs with Preference Data.” ICLR, 2025. <https://proceedings.iclr.cc/paper_files/paper/2025/file/5503a7c69d48a2f86fc00b3dc09de686-Paper-Conference.pdf>
4. Patel, P. et al. “Splitwise: Efficient Generative LLM Inference Using Phase Splitting.” ISCA, 2024. <https://www.microsoft.com/en-us/research/wp-content/uploads/2023/12/Splitwise_ISCA24.pdf>
5. Zhong, Y. et al. “DistServe: Disaggregating Prefill and Decoding for Goodput-optimized Large Language Model Serving.” OSDI, 2024. <https://www.usenix.org/system/files/osdi24-zhong-yinmin.pdf>
