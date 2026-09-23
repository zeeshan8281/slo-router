# Source registry

| ID | Source | Type | Grade | Used for |
| --- | --- | --- | --- | --- |
| S1 | [RouterBench](https://arxiv.org/abs/2403.12031) | ICML 2024 research | A | All-model outcome matrix, cost-quality frontier, oracle |
| S2 | [RouteLLM](https://arxiv.org/abs/2406.18665) | ICLR 2025 research | A | Strong/weak routing, threshold sweeps, held-out evaluation |
| S3 | [LLMRouterBench](https://aclanthology.org/2026.findings-acl.1881/) | Findings of ACL 2026 research | A | Simple baselines, five-seed comparison, Pareto and oracle gaps |
| S4 | [DistServe](https://arxiv.org/abs/2401.09670) | OSDI 2024 research | A | TTFT/TPOT constraints and goodput |
| S5 | [Llumnix](https://www.usenix.org/conference/osdi24/presentation/sun-biao) | OSDI 2024 research | A | Dynamic scheduling and tail latency under heterogeneous load |
| S6 | [vLLM serving benchmark](https://github.com/vllm-project/vllm/blob/main/docs/benchmarking/cli.md) | Official project documentation | A- | Client measurement, arrivals, TTFT/TPOT/ITL, cache cautions |
| S7 | [vLLM metrics](https://docs.vllm.ai/en/latest/design/metrics/) | Official project documentation | A- | Queue, cache, and serving telemetry |
| S8 | [Gateway API Inference Extension](https://gateway-api-inference-extension.sigs.k8s.io/) | Official Kubernetes project | A- | Endpoint selection from queue, model, and cache state |
| S9 | [Counterfactual Risk Minimization](https://proceedings.mlr.press/v37/swaminathan15.html) | ICML 2015 research | A | Logged propensities and IPS variance |
| S10 | [Doubly Robust Policy Evaluation](https://arxiv.org/abs/1103.4601) | ICML 2011 research | A | Direct, IPS, and doubly robust evaluation |
| S11 | [Calibration of Modern Neural Networks](https://proceedings.mlr.press/v70/guo17a.html) | ICML 2017 research | A | Reliability metrics and post-hoc calibration |
| S12 | [Selective Classification](https://papers.nips.cc/paper_files/paper/2017/hash/4a8423d5e91fda00bb7e46540e2b0cf1-Abstract.html) | NeurIPS 2017 research | A | Risk-coverage analysis |
| S13 | [TypeSafe Jev 1.13 limitations](https://docs.typesafe.ai/model-jaggedness/jev-1.13) | Official vendor documentation | B+ | Literal, arithmetic, date, indirection, and adversarial limits |
| S14 | [TypeSafe confidence](https://docs.typesafe.ai/confidence) | Official vendor documentation | B+ | Group calibration and workload-specific thresholds |
| S15 | [TypeSafe Decisions API](https://docs.typesafe.ai/api) | Official vendor documentation | B+ | Typed questions, probabilities, and usage fields |
| S16 | [OpenRouter Jev 1.13](https://openrouter.ai/typesafe/jev-1.13/) | Provider model page | B | Model availability, context, and provider metadata |
| S17 | [Independent Jev phishing benchmark](https://github.com/anisselbd/jev-phishing-bench) | Public reproducibility artifact | B- | Direct-verdict versus decomposed-feature counterexample |

Grades describe source fitness for the claim, not a universal ranking. The repository's request-level artifacts remain the only evidence used for its measured results.
