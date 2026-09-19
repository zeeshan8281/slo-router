# Replay benchmark report

> Results reflect the supplied replay file. The bundled demo uses deterministic simulated backends and is not a model benchmark.

| Policy | Completed | Accuracy | SLO success | p50 ms | p95 ms | Predicted cost | Cost / correct-in-SLO | Routes | Features |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| fixed_cheapest | 8/8 | 0.625 | 1.000 | 28.81 | 33.49 | $0.00013140 | $0.00002628 | fast=8 | lexical=8 |
| fixed_strongest | 8/8 | 1.000 | 1.000 | 70.57 | 71.18 | $0.00131400 | $0.00016425 | strong=8 | lexical=8 |
| quality_only | 8/8 | 1.000 | 1.000 | 51.40 | 71.87 | $0.00071190 | $0.00008899 | fast=4, strong=4 | lexical=8 |
| slo_no_jev | 8/8 | 1.000 | 1.000 | 52.03 | 71.59 | $0.00071190 | $0.00008899 | fast=4, strong=4 | lexical=8 |
| slo | 8/8 | 1.000 | 1.000 | 51.40 | 72.85 | $0.00071190 | $0.00008899 | fast=4, strong=4 | lexical=8 |
