# Evaluating an SLO-Aware LLM Router

**Technical study and experiment acceptance contract**  
**As of:** 2026-09-23  
**Scope:** heterogeneous LLM routing, load-sensitive deadline control, counterfactual evaluation, and Jev 1.13 semantic features

## Executive finding

SLO Router currently demonstrates two mechanisms: queue-aware routing can split a synthetic burst across capacity to meet a deadline, and Jev can be called through OpenRouter with bounded fallback. Those results are useful integration evidence. They do not yet establish that the router reduces production cost while preserving real-model quality and latency.

A credible evaluation needs two linked experiments:

1. **A frozen all-model response matrix** to measure answer quality, cost, router regret, calibration, and oracle headroom without missing counterfactual outcomes.
2. **A live serving replay** over steady and bursty arrival processes to measure client-observed TTFT, TPOT, end-to-end latency, deadline attainment, failures, and correct-in-SLO goodput.

The primary success metric should be **correct-in-SLO goodput**: completed, correctly graded requests satisfying their declared latency contract per unit time. Cost per correct-in-SLO request is the primary efficiency metric. Aggregate accuracy or raw throughput alone can reward a policy that is cheap but late, or fast but wrong.

The synchronous Jev path should remain experimental. In the repository's eight-request live integration run it changed no route and increased SLO-aware p95 latency from 77.93 ms to 490.38 ms. The minimum bar for enabling it is a held-out, real-model result showing that its route changes improve correct-in-SLO outcomes or cost enough to pay for its latency and API cost.

**Confidence:** High for the experimental design; Low for production benefit until the real endpoint study is run.

## 1. Research question and falsifiable hypotheses

The question is narrower than “does intelligent routing work?”:

> On a frozen workload and fixed set of real model endpoints, does this controller lower cost per correct response delivered within the caller's latency SLO, relative to simple policies, without an unacceptable loss in answer quality or reliability?

The following hypotheses must be preregistered before the held-out results are opened.

| ID | Hypothesis | Falsifier |
|---|---|---|
| H1 | Load-aware routing raises correct-in-SLO goodput under contention relative to quality-only and fixed-cheapest routing. | The paired 95% confidence interval for the gain includes zero in the preregistered supported-load region. |
| H2 | SLO routing lowers cost per correct-in-SLO request relative to fixed-strongest while remaining quality-noninferior. | Quality misses the noninferiority margin or the cost-ratio interval includes the required saving threshold. |
| H3 | Predicted backend quality and deadline probability are calibrated on held-out traffic. | Reliability error, Brier score, or interval coverage exceeds the thresholds below. |
| H4 | Route choices approach the feasible counterfactual oracle and beat the best simple policy. | Regret is no better than best-single/per-task or quality-only routing. |
| H5 | Jev features add decision value beyond deterministic local features. | Jev rarely changes routes, route changes are not more often beneficial, or feature latency/cost erases the gain. |
| H6 | Failure handling degrades gracefully under bounded 429, timeout, malformed-feature, and backend-outage injection. | Requests loop, exceed the retry budget, leak to ineligible backends, or miss the recovery thresholds. |

## 2. What prior work implies for this router

### 2.1 Router evaluation requires strong simple baselines and an oracle

[RouterBench](https://arxiv.org/abs/2403.12031) formalizes router evaluation as a quality–cost problem, publishes a 405,467-outcome matrix across 11 models and eight datasets, and uses an oracle that selects the cheapest model producing a satisfactory answer. [RouteLLM](https://arxiv.org/abs/2406.18665) evaluates learned strong-versus-weak routing by sweeping the routing threshold and comparing quality at different strong-model call rates. These designs imply that one operating point is inadequate: the evaluation must show a frontier over quality floor, SLO target, or routing threshold.

The newer [LLMRouterBench](https://arxiv.org/abs/2601.07206) strengthens the warning against weak comparisons. Across more than 400,000 instances, 21 datasets, 33 models, and ten router baselines, several sophisticated methods failed to reliably beat a best-single baseline; leading methods were often similar, and a persistent gap remained to the oracle. It reports results over five random seeds and argues that progress should move the Pareto frontier, rather than improve one selected scalar metric.

For SLO Router, the mandatory offline baselines are:

1. fixed cheapest eligible backend;
2. fixed strongest backend;
3. best single backend on the training split, then frozen;
4. best backend per coarse task on the training split, then frozen;
5. quality-only cheapest-feasible routing;
6. least-loaded eligible backend;
7. SLO-aware routing without Jev;
8. SLO-aware routing with Jev;
9. a hindsight oracle selecting the cheapest correct backend that would satisfy the SLO.

The oracle is an upper bound, never a deployable baseline. It quantifies avoidable regret and whether candidate models are complementary enough for routing to matter.

### 2.2 Serving metrics must preserve user-visible phases

[DistServe](https://www.usenix.org/conference/osdi24/presentation/zhong-yinmin) defines serving goodput as the maximum request rate that satisfies latency SLOs and separates prefill and decoding interference. [Llumnix](https://www.usenix.org/conference/osdi24/presentation/sun-biao) shows why heterogeneous, unpredictable requests create queue delay, tail-latency spikes, and SLO violations even when average service time looks acceptable. The Kubernetes [Gateway API Inference Extension](https://gateway-api-inference-extension.sigs.k8s.io/) likewise treats queue/load metrics, endpoint capabilities, and prefix-cache state as routing inputs rather than relying on ordinary round-robin balancing.

The official [vLLM serving benchmark documentation](https://github.com/vllm-project/vllm/blob/main/docs/benchmarking/cli.md) measures at the client and defines:

- **TTFT:** request send to first streamed token;
- **TPOT:** `(end-to-end latency - TTFT) / (output tokens - 1)` per request;
- **ITL:** observed gap between streamed chunks;
- **end-to-end latency:** request send to completion.

It warns that repeated prompts can reuse prefix cache and inflate apparent throughput, recommends resetting caches between independent runs, and supports finite request-rate, concurrency, ramp, and burst testing. SLO Router should copy the measurement points and formulas even when it uses its own replay client.

For request `i`, define:

```text
correct_i       = grader(response_i, label_i)
deadline_ok_i   = TTFT_i <= TTFT_SLO_i
                  and TPOT_i <= TPOT_SLO_i
                  and E2E_i <= E2E_SLO_i
good_i          = correct_i and deadline_ok_i and no_transport_error_i

goodput         = sum(good_i) / wall_clock_seconds
cost_per_good   = total_actual_cost / sum(good_i)
```

If the current API exposes only an end-to-end SLO, report it as such. Do not call it a complete interactive streaming SLO until TTFT and TPOT are separately enforced.

### 2.3 Logged routed traffic is not a complete counterfactual dataset

Production routing observes the answer and latency only for the chosen backend. Evaluating a new deterministic policy directly on those logs is biased because the unchosen outcomes are missing. Counterfactual risk minimization uses logged action propensities to correct this selection effect, but importance weighting can have high variance when candidate and logging policies differ ([Swaminathan and Joachims, ICML 2015](https://proceedings.mlr.press/v37/swaminathan15.html)). Doubly robust estimation combines a reward model with propensity weighting and is consistent if either the reward model or logging-policy model is correct under its assumptions ([Dudík, Langford, and Li, ICML 2011](https://arxiv.org/abs/1103.4601)).

The cleanest repository-scale design is therefore the existing matrix idea: run every frozen request on every candidate backend before fitting. That provides observed counterfactual quality, token counts, and unloaded service times. For a future online experiment:

- log the candidate set, chosen action, exact randomized propensity, policy version, predictions, queue snapshot, outcome, and cost;
- reserve a small randomized exploration bucket with nonzero support for every eligible action;
- report direct-model, inverse-propensity, self-normalized IPS, and doubly robust estimates with effective sample size;
- refuse offline claims where the target policy chooses actions with zero logging support.

Queueing outcomes are policy-dependent: sending more work to a backend changes future waits. A response matrix can estimate answer quality and service demand, but it cannot substitute for a live traffic replay when evaluating latency.

### 2.4 Probability outputs need calibration and selective evaluation

Calibration asks whether events assigned probability `p` occur about `p` of the time. [Guo et al.](https://proceedings.mlr.press/v70/guo17a.html) show that accurate predictive models can still be miscalibrated and evaluate post-hoc temperature scaling. [Selective classification](https://papers.nips.cc/paper_files/paper/2017/hash/4a8423d5e91fda00bb7e46540e2b0cf1-Abstract.html) evaluates the risk–coverage tradeoff when a model abstains below a confidence threshold.

Apply both ideas separately to:

- `P(correct | request, backend)`;
- `P(meets SLO | request, backend, load state)`;
- Jev Noul probabilities and Choice distributions;
- the router's final feasibility decision.

Report Brier score, log loss, reliability plots, ECE with disclosed bins, and calibration slope/intercept. ECE alone is bin-sensitive. Also show risk–coverage curves as the router raises the quality floor or abstains/returns infeasible.

### 2.5 Jev is a feature generator, not an accuracy guarantee

TypeSafe documents Jev as a model for atomic typed decisions, with independent Choice, Score, and Noul questions. Its own [Jev 1.13 limitations](https://docs.typesafe.ai/model-jaggedness/jev-1.13) include literal reading, weak arithmetic/date reasoning, indirection, irrelevant-context degradation, adversarial steering, and non-equivalence between a binary Choice and a Noul phrasing. TypeSafe's [confidence guidance](https://docs.typesafe.ai/confidence) says thresholds must be selected for the use case.

Independent counterevidence matters. A reproducible [2,000-email phishing benchmark](https://github.com/anisselbd/jev-phishing-bench) found 62.6% accuracy for a single Jev verdict versus 81.3% for Claude Haiku 4.5. On a held-out 1,000-email half, five decomposed Jev signals plus logistic regression reached 95.0% accuracy, above a 91.8% regex baseline, while the corresponding Haiku signal model reached 93.2%; that Jev–Haiku accuracy gap was not significant. The dataset was unusually separable by URL heuristics, and the feature questions were informed by its taxonomy. The lesson is methodological: test decomposition, a deterministic baseline, the same questions on a conventional LLM, and a held-out combiner. A typed answer is not necessarily a useful feature.

## 3. Experimental system and frozen artifacts

Before collecting held-out outcomes, record:

- git commit and dirty status;
- router and question revision;
- backend provider, model revision, quantization, serving engine, hardware, region, and replica count;
- tokenizer and context limit per backend;
- prices and the date retrieved;
- decoding parameters, tool configuration, and output limit;
- dataset checksum, split manifest, graders, and prompt templates;
- cache policy and whether each cell is cold or warm;
- arrival trace and random seeds;
- retry, timeout, and circuit-breaker configuration;
- client location and clock source.

The dataset must contain real task diversity, prompt-length buckets, expected-output-length buckets, repeated-prefix groups, tool/evidence requirements, and adversarial or ambiguous cases. Exact-match grading is suitable only for tasks with canonical answers. Code should use executable tests; extraction should use normalized structured comparison; open-ended tasks require a rubric validated against blinded human judgments. The judge cannot be one of the candidate models without a disclosed sensitivity analysis.

Use a deterministic hash split by semantic unit, such as user/task/conversation, so near-duplicates never cross train and test. Freeze at least **1,000 held-out requests overall and 100 per reported task × backend slice**. Smaller slices may be exploratory but cannot support release claims.

## 4. Experiment program

### E0 — Reproducibility and measurement audit

Run the same no-load cell five times from clean runtime state. Verify route decisions, request counts, grading, pricing, and timestamp ordering. Compare client latency with router and backend spans. Run both cold-prefix and deliberate warm-prefix modes.

**Accept when:** all requests have joinable IDs; no result is silently dropped; cost reconciles with provider usage within 2% or the provider's billing granularity; route distribution is deterministic where inputs/state are deterministic; clock-derived component times never exceed end-to-end time beyond 1 ms rounding tolerance.

### E1 — Full counterfactual response matrix

Run every training and held-out request against every eligible backend with fixed decoding. Preserve raw response hashes, token counts, latency, error, and grader evidence. Fit task quality priors only on training data. Evaluate on held-out data once.

Report each backend, every baseline, and the oracle. Plot quality versus actual cost and quality versus unloaded latency. Report oracle selection frequency and per-task router regret.

**Accept when:** matrix coverage is at least 99.5% after bounded retries; missingness and errors are reported as failures, not deleted; the held-out split has no prompt/template duplicate from training; SLO Router beats best-single or per-task routing on at least one preregistered objective and does not underperform both. Otherwise the right conclusion is that routing adds no measured value for this pool.

### E2 — Offered-load sweep

First measure each backend's sustainable rate under the target prompt/output mix. Then replay identical workloads under:

- steady Poisson arrivals at 25%, 50%, 75%, 90%, 100%, and 110% of aggregate estimated capacity;
- bursts of 1, 5, 10, 20, and 40 requests and at least one production-derived burst trace;
- two prompt mixes: short interactive and long-prefill;
- cold and warm prefix-cache conditions;
- at least three independent seeds per cell.

Each steady cell must run for at least 15 minutes and contain at least 1,000 completed or failed requests after warmup. Policy order should be randomized, and runtime state reset between policies. Do not use a concurrency cap as a hidden queue without reporting client queue time.

**Accept when:** in the declared supported-load region (through 90% offered capacity), SLO-aware routing's 95% Wilson lower bound for deadline attainment is at least 0.90 and its paired correct-in-SLO gain over quality-only is positive. At 100–110%, the report may show graceful overload rather than pass; error and queue growth must remain bounded by explicit admission control.

### E3 — SLO-target sweep

Use SLO targets anchored to unloaded endpoint behavior, not arbitrary round numbers: for example 1.25×, 2×, 4×, and 8× the fixed-strongest unloaded p50 end-to-end latency, plus product SLOs if they exist. For streaming, cross TTFT and TPOT targets rather than collapsing both into E2E.

**Accept when:** relaxing the SLO never systematically increases strong-backend use or expected cost after sampling noise; tighter SLOs produce monotonic or explainable route shifts; predicted feasibility bins match observed attainment within 5 percentage points for bins containing at least 100 requests.

### E4 — Quality and latency calibration

For quality, compare predicted probability with held-out correctness for each backend/task. For latency, compare predicted deadline probability with observed success under each load bucket. Plot residuals against prompt tokens, generated tokens, queue depth, task, and cache state.

**Accept when:** Brier score is at most 0.10, ECE is at most 0.05 with ten equal-mass bins, calibration slope lies in `[0.8, 1.2]`, and no large slice with at least 100 samples has absolute calibration error above 0.10. These are project acceptance thresholds, not universal research standards. If missed, recalibrate on training data and re-evaluate once on untouched test data.

### E5 — Failure injection

Inject one factor at a time and then a combined scenario:

| Fault | Levels | Required observations |
|---|---|---|
| backend 429 | 1%, 5%, 20%; burst of 20 consecutive | retries, alternate route, cost duplication, deadline result |
| backend transport timeout | 250 ms and above-SLO delay | cancellation, retry bound, queue release |
| backend 5xx/outage | one endpoint unavailable for 60 s | health detection and recovery time |
| Jev 429/529/timeout | 1%, 10%, 100% | lexical fallback, route parity, added latency |
| malformed Jev output | missing answer, invalid probability | validation and fallback |
| stale/incorrect queue metrics | lag of 0.5, 1, 5 s | hot-spot rate and deadline loss |
| context overflow | just below/above every backend limit | eligibility exclusion and explicit infeasibility |
| streaming disconnect | before first token and mid-stream | upstream cancellation and state cleanup |

**Accept when:** there are no unbounded retries; total attempts never exceed the configured bound; 100% Jev failure produces the same routing decisions as `slo_no_jev` for identical local features; no request is sent to a known ineligible backend; backend outage is avoided within two health intervals; recovery occurs within two healthy intervals; prompt or credentials never appear in fault logs. Under 10% injected feature/backend transient failures, completed-request rate must remain at least 99% where another feasible backend exists.

### E6 — Jev ablation ladder

Evaluate on the same held-out requests and live arrival traces:

1. local deterministic features only;
2. Jev single task Choice;
3. Jev atomic task/exactness/evidence questions;
4. atomic Jev features with confidence gating;
5. same atomic questions asked of a small conventional LLM;
6. Jev with shuffled or removed descriptions as a sensitivity control;
7. synchronous uncached Jev, warm cached Jev, and asynchronous precomputed Jev;
8. pinned question wording variants, Choice-versus-Noul where meaningful;
9. repeat pass for probability stability.

Report feature accuracy, calibration, route-change rate, beneficial/harmful/neutral route changes using the complete matrix, feature p50/p95/p99 latency, fallback rate, cost, and final correct-in-SLO metrics.

**Accept synchronous Jev only when all conditions hold on held-out data:**

- it changes at least 5% of otherwise eligible routes;
- beneficial route changes outnumber harmful changes with a paired 95% interval above zero;
- it improves correct-in-SLO rate by at least 2 percentage points **or** reduces cost per correct-in-SLO by at least 10%;
- the improvement includes Jev input cost and feature latency;
- Jev feature p95 consumes no more than 20% of the request SLO;
- its fallback path meets E5.

If it improves offline selection but fails the latency criterion, accept it only for asynchronous/precomputed use. If it does not beat local features, remove it from the default path.

### E7 — End-to-end policy comparison and statistical decision

Use paired requests wherever possible. For accuracy and deadline proportions, report Wilson intervals; for differences and cost ratios, use a stratified paired bootstrap over semantic units with at least 10,000 resamples. For paired binary errors, include McNemar's exact test. Report distributions and effect sizes rather than p-values alone.

The release claim “lower cost without sacrificing quality or SLO” passes only if, on the untouched test set and supported-load region:

1. **quality noninferiority:** lower bound of the paired accuracy difference versus fixed-strongest is greater than `-0.02`;
2. **deadline reliability:** lower 95% bound of correct-request SLO attainment is at least `0.90`;
3. **efficiency:** upper 95% bound of the cost-per-correct-in-SLO ratio versus fixed-strongest is below `0.90`;
4. **simple-baseline superiority:** correct-in-SLO gain versus quality-only has a lower confidence bound above zero;
5. **robustness:** no preregistered task or prompt-length slice with at least 100 examples loses more than five accuracy points without being disclosed;
6. **reproducibility:** at least three load-run seeds agree on the sign of the primary effects.

These margins are explicit project choices. Change them only before evaluation and document the operational reason.

## 5. Interpretation of current repository evidence

### Burst-load result

The checked-in ten-request, 400 ms synthetic burst is a valid mechanism test. Both simulated backends return the same correct answer, so it isolates queue-aware capacity allocation: quality-only achieved 40% SLO success, while SLO-aware routing moved six requests to the capacity backend and achieved 100%, at 36% lower configured cost than fixed-strongest. Five identical runs support deterministic integration behavior.

The broader checked-in sweep shows the same designed pattern through burst size 40. This does not estimate production tail behavior because service times, capacity, price, and quality are controlled constants; repeated simulator runs also have very low stochastic variance. It passes E0-style mechanism validation, not E2/E7 production acceptance.

### Live Jev result

The eight-request OpenRouter integration is a useful negative ablation. Sixteen feature calls succeeded without fallback, but Jev did not change any route relative to local features. On SLO-aware routing, p95 grew from 77.93 ms to 490.38 ms and predicted total cost increased. This fails the proposed E6 route-change, incremental-value, and latency criteria. The repository's current decision to keep local SLO routing as the baseline is supported.

The sample is too small for a general statement that Jev cannot help routing. The phishing benchmark shows that atomic Jev signals can be useful after held-out combination even when a single verdict is weak. E6 is designed to find that narrower value without crediting typed output as accuracy.

## 6. Threats to validity and counter-review

1. **Simulator fidelity.** Deterministic sleeps validate control flow but omit GPU batching, prefill/decode interference, token-length variance, engine scheduling, cache eviction, and provider jitter.
2. **Policy-induced queues.** Offline service times cannot fully predict a policy that changes arrival rates at each backend. Live replay is necessary.
3. **Label and judge validity.** A router can optimize grader artifacts. Preserve grader evidence, audit disagreements, and use human validation for subjective tasks.
4. **Training leakage.** Task priors or Jev questions tuned after reading test errors invalidate held-out claims. Version and freeze them before the final run.
5. **Tail sample size.** p99 from ten or forty requests is not a stable percentile. At least 1,000 samples per reported cell are required, and more are preferable for p99.
6. **Cache confounding.** Repeated prompts can create unrealistically warm prefix caches. Publish cold and warm results separately.
7. **Estimated versus billed cost.** Token-price arithmetic omits retries, feature calls, minimum charges, cached-token prices, and infrastructure amortization. Reconcile against actual usage records.
8. **Router overhead.** Feature extraction, token counting, metrics reads, and proxying must be included in client-observed latency.
9. **Provider drift.** Aliases, model revisions, and server load change. Pin versions where possible and record resolved models and timestamps.
10. **Jev endpoint maturity.** The OpenRouter Decisions endpoint is alpha. API and availability behavior may change; fallback evidence is part of the result.
11. **Multiple comparisons.** Many task/load/SLO slices invite cherry-picking. Identify one primary outcome, freeze secondary analyses, and disclose all cells.
12. **No universal production claim.** Passing one workload supports that workload, endpoint pool, hardware, price sheet, and SLO distribution only.

An opposing interpretation of the current work is that the result is simply “a queue estimator sends overflow to a less-congested server.” That interpretation is accurate for the simulator. The project becomes an LLM routing result only after E1 shows real backend complementarity and E2/E7 show that exploiting it improves correct-in-SLO economics under live load.

## 7. Release claim ladder

Use the strongest statement whose gate has passed:

| Gate | Permitted claim |
|---|---|
| Unit/integration tests only | “Implements an OpenAI-compatible SLO-routing prototype with bounded fallback.” |
| Current deterministic burst experiment | “Demonstrates queue-aware routing on controlled simulated backends.” |
| E1 passes | “Improves held-out cost–quality tradeoffs on the named model pool and dataset.” |
| E2–E5 pass | “Maintains the stated deadline and failure behavior on the named serving setup and load envelope.” |
| E7 passes | “Reduces cost per correct-in-SLO response by the measured amount on the frozen workload and deployment.” |
| E6 passes | “Jev features improve the named routing outcome after feature cost and latency.” |

Do not generalize simulated savings, one-region latency, or selected vendor benchmarks into universal production claims.

## 8. Required output artifacts

Every final campaign should publish:

- frozen dataset manifest and checksums;
- train/test group assignments;
- all-backend response matrix or a privacy-safe derivation;
- policy, backend, model, pricing, and hardware manifest;
- arrival traces and seeds;
- request-level results with IDs, chosen route, predictions, actual TTFT/TPOT/E2E, grade, error, attempts, token usage, and actual cost;
- aggregate tables with confidence intervals;
- calibration and risk–coverage plots;
- load, SLO, cache, failure, and Jev ablation tables;
- missing/error accounting;
- exact commands or one orchestration command;
- a limitations section preserving negative findings.

## 9. Source registry

All sources are public. Academic papers and official project documentation are preferred; the Jev benchmark is an independent public reproducibility artifact.

1. Hu et al., [RouterBench: A Benchmark for Multi-LLM Routing System](https://arxiv.org/abs/2403.12031), ICML 2024. **Academic;** all-model outcome matrix, cost/quality formulation, oracle.
2. Ong et al., [RouteLLM: Learning to Route LLMs with Preference Data](https://arxiv.org/abs/2406.18665), 2024/2025 revision. **Academic;** strong/weak routing and cost–quality threshold sweeps.
3. Li et al., [LLMRouterBench: A Massive Benchmark and Unified Framework for LLM Routing](https://aclanthology.org/2026.findings-acl.1881/), Findings of ACL 2026. **Academic;** large unified comparison, simple baselines, five-seed reporting, oracle gap, latency extension.
4. Zhong et al., [DistServe: Disaggregating Prefill and Decoding for Goodput-optimized Large Language Model Serving](https://www.usenix.org/conference/osdi24/presentation/zhong-yinmin), OSDI 2024. **Academic;** TTFT/TPOT SLOs and goodput.
5. Sun et al., [Llumnix: Dynamic Scheduling for Large Language Model Serving](https://www.usenix.org/conference/osdi24/presentation/sun-biao), OSDI 2024. **Academic;** heterogeneous load, queueing, tail latency, dynamic scheduling.
6. vLLM project, [Serving benchmark CLI documentation](https://github.com/vllm-project/vllm/blob/main/docs/benchmarking/cli.md). **Official project documentation;** client metrics, arrival controls, cache warnings, TTFT/TPOT/ITL formulas.
7. Kubernetes SIGs, [Gateway API Inference Extension](https://gateway-api-inference-extension.sigs.k8s.io/). **Official project documentation;** model-server metrics and endpoint selection.
8. Swaminathan and Joachims, [Counterfactual Risk Minimization: Learning from Logged Bandit Feedback](https://proceedings.mlr.press/v37/swaminathan15.html), ICML 2015. **Academic;** propensities and variance-aware logged-policy evaluation.
9. Dudík, Langford, and Li, [Doubly Robust Policy Evaluation and Learning](https://arxiv.org/abs/1103.4601), ICML 2011. **Academic;** direct, IPS, and doubly robust policy evaluation.
10. Guo et al., [On Calibration of Modern Neural Networks](https://proceedings.mlr.press/v70/guo17a.html), ICML 2017. **Academic;** reliability and post-hoc calibration.
11. Geifman and El-Yaniv, [Selective Classification for Deep Neural Networks](https://papers.nips.cc/paper_files/paper/2017/hash/4a8423d5e91fda00bb7e46540e2b0cf1-Abstract.html), NeurIPS 2017. **Academic;** risk–coverage evaluation and abstention.
12. TypeSafe AI, [Jev 1.13 jaggedness](https://docs.typesafe.ai/model-jaggedness/jev-1.13) and [Confidence](https://docs.typesafe.ai/confidence), reviewed 2026-09-17. **Official vendor documentation;** failure modes and threshold guidance.
13. anisselbd, [Jev phishing benchmark](https://github.com/anisselbd/jev-phishing-bench), 2026-09-17. **Independent reproducibility artifact;** 2,000-email direct verdict, decomposition, calibration, deterministic baseline, and held-out controls.

## Final decision

Keep the current deterministic burst result as a mechanism demonstration and the live Jev run as a negative integration ablation. The next publishable experiment is E1 followed by E2: a real, frozen all-backend response matrix and live arrival-rate replay. No learned router or additional feature service is justified until those results show material regret left by the existing per-task priors and local SLO policy.

