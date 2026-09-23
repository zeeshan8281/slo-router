# Research plan

1. Define routing evaluation metrics and baselines from RouterBench, RouteLLM, serving/goodput research, vLLM metrics, and Kubernetes inference routing.
2. Audit current code and artifacts for reproducibility, counterfactual coverage, timing validity, and privacy.
3. Execute repeated burst-load and SLO-target sweeps on the deterministic harness.
4. Add controlled backend failure and recovery, Jev cache/fallback, and steady-arrival experiments where supported.
5. Compare findings against fixed cheapest, fixed strongest, quality-only, and no-Jev SLO-aware baselines.
6. Perform adversarial counter-review: simulator fidelity, small sample size, predicted versus actual cost, route-induced feedback, and absence of real-model quality.
7. Publish a complete report, source registry, and only verified README tables.
