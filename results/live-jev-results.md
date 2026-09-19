# Replay benchmark report

> Results reflect the supplied replay file. The bundled demo uses deterministic simulated backends and is not a model benchmark.

| Policy | Completed | Accuracy | SLO success | p50 ms | p95 ms | Predicted cost | Cost / correct-in-SLO | Routes | Features |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| fixed_cheapest | 8/8 | 0.625 | 1.000 | 28.58 | 35.64 | $0.00013140 | $0.00002628 | fast=8 | lexical=8 |
| fixed_strongest | 8/8 | 1.000 | 1.000 | 69.23 | 69.47 | $0.00131400 | $0.00016425 | strong=8 | lexical=8 |
| quality_only | 8/8 | 1.000 | 1.000 | 777.64 | 1296.30 | $0.00086016 | $0.00010752 | fast=4, strong=4 | jev=8 |
| slo_no_jev | 8/8 | 1.000 | 1.000 | 56.10 | 77.93 | $0.00071190 | $0.00008899 | fast=4, strong=4 | lexical=8 |
| slo | 8/8 | 1.000 | 1.000 | 436.99 | 490.38 | $0.00086016 | $0.00010752 | fast=4, strong=4 | jev=8 |
