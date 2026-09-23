# Router sensitivity sweeps

Each point is three independent runs against deterministic simulated backends. Quality-only and SLO-aware policies receive identical requests, backend parameters, and reset runtime state. Latency MAE is the mean absolute error between the selected route's pre-dispatch prediction and observed end-to-end latency.

## Burst-size sweep

| Simultaneous requests | Policy | SLO success across 3 runs | Median p95 | Median latency MAE | Last-run routes |
| ---: | --- | ---: | ---: | ---: | --- |
| 1 | quality_only | 100% | 91.55 ms | 20.78 ms | cheap 1 |
| 1 | slo_no_jev | 100% | 90.06 ms | 22.27 ms | cheap 1 |
| 5 | quality_only | 80% | 424.37 ms | 15.09 ms | cheap 5 |
| 5 | slo_no_jev | 100% | 347.02 ms | 12.55 ms | cheap 4 / fast-capacity 1 |
| 10 | quality_only | 40% | 855.54 ms | 86.82 ms | cheap 10 |
| 10 | slo_no_jev | 100% | 345.89 ms | 16.92 ms | cheap 4 / fast-capacity 6 |
| 20 | quality_only | 20% | 1583.41 ms | 21.23 ms | cheap 20 |
| 20 | slo_no_jev | 100% | 281.43 ms | 15.32 ms | cheap 4 / fast-capacity 16 |
| 40 | quality_only | 10% | 3160.08 ms | 44.92 ms | cheap 40 |
| 40 | slo_no_jev | 100% | 295.60 ms | 27.86 ms | cheap 4 / fast-capacity 36 |

## SLO-target sweep

| SLO target | Policy | SLO success across 3 runs | Median p95 | Median latency MAE | Last-run routes |
| ---: | --- | ---: | ---: | ---: | --- |
| 150 ms | quality_only | 10% | 841.61 ms | 7.61 ms | cheap 10 |
| 150 ms | slo_no_jev | 100% | 131.38 ms | 18.89 ms | cheap 1 / fast-capacity 9 |
| 250 ms | quality_only | 20% | 846.71 ms | 7.58 ms | cheap 10 |
| 250 ms | slo_no_jev | 100% | 198.03 ms | 19.97 ms | cheap 2 / fast-capacity 8 |
| 400 ms | quality_only | 40% | 844.45 ms | 19.76 ms | cheap 10 |
| 400 ms | slo_no_jev | 100% | 359.48 ms | 23.75 ms | cheap 4 / fast-capacity 6 |
| 800 ms | quality_only | 90% | 840.03 ms | 9.02 ms | cheap 10 |
| 800 ms | slo_no_jev | 100% | 767.19 ms | 88.59 ms | cheap 9 / fast-capacity 1 |

## Arrival-pattern sweep

| Inter-arrival gap | Policy | SLO success across 3 runs | Median p95 | Median latency MAE | Last-run routes |
| ---: | --- | ---: | ---: | ---: | --- |
| 0 ms | quality_only | 20% | 1590.89 ms | 20.11 ms | cheap 20 |
| 0 ms | slo_no_jev | 100% | 283.40 ms | 15.21 ms | cheap 4 / fast-capacity 16 |
| 40 ms | quality_only | 40% | 862.84 ms | 46.10 ms | cheap 20 |
| 40 ms | slo_no_jev | 100% | 335.27 ms | 23.55 ms | cheap 13 / fast-capacity 7 |
| 80 ms | quality_only | 100% | 140.51 ms | 70.53 ms | cheap 20 |
| 80 ms | slo_no_jev | 100% | 142.92 ms | 66.15 ms | cheap 20 |
| 120 ms | quality_only | 100% | 97.72 ms | 17.54 ms | cheap 20 |
| 120 ms | slo_no_jev | 100% | 98.40 ms | 17.77 ms | cheap 20 |

These are mechanism and sensitivity tests, not real-model performance claims. The simulator does not reproduce GPU batching, token-level scheduling, network variance, or model-quality uncertainty.
