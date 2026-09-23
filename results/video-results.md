# Replay benchmark report

> Results reflect the supplied replay file. The bundled demo uses deterministic simulated backends and is not a model benchmark.

| Policy | Completed | Accuracy | SLO success | p50 ms | p95 ms | Predicted cost | Cost / correct-in-SLO | Routes | Features |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| fixed_cheapest | 10/10 | 1.000 | 0.400 | 471.83 | 842.54 | $0.00005300 | $0.00001325 | cheap=10 | lexical=10 |
| fixed_strongest | 10/10 | 1.000 | 1.000 | 114.26 | 124.41 | $0.00053000 | $0.00005300 | fast-capacity=10 | lexical=10 |
| quality_only | 10/10 | 1.000 | 0.400 | 467.82 | 837.45 | $0.00005300 | $0.00001325 | cheap=10 | lexical=10 |
| slo_no_jev | 10/10 | 1.000 | 1.000 | 112.23 | 347.18 | $0.00033920 | $0.00003392 | cheap=4, fast-capacity=6 | lexical=10 |
