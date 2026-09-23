# Evidence table

| Finding | Direct evidence | Confidence | Boundary |
| --- | --- | --- | --- |
| The OpenAI-compatible proxy and core routing paths execute | `tests/test_core.py`; five tests pass | High for covered code paths | Small functional suite, not production reliability evidence |
| SLO routing reacts to burst pressure | `results/sweep-replay.jsonl`; 1,176 request rows across three sensitivity sweeps | High for the deterministic fixture | Service time, capacity, answers, and price are controlled constants |
| At a 10-request burst and 400 ms target, SLO routing improves deadline attainment | Three sweep repeats: 100% versus 40%; latest video run: 10/10 versus 4/10 | High for the fixture | Does not establish a production effect |
| The controller shifts traffic monotonically as the target tightens | Capacity routes rise from 1/10 at 800 ms to 9/10 at 150 ms | High for the fixture | Targets and latency model were chosen for this topology |
| The controller stops buying capacity when arrivals are sustainable | At 80 and 120 ms gaps both policies send all 20 requests to the cheap backend and achieve 100% | High for the fixture | No GPU batching, background load, or network variance |
| The 10-request SLO route mix costs less than fixed-capacity routing | Configured estimate: $0.0003392 versus $0.0005300, 36% lower | High arithmetically | Configured token-price estimate, not provider billing |
| Live Jev integration completed | 16/16 dated OpenRouter decision calls succeeded | High for that run | Eight prompts; alpha endpoint; no availability claim |
| Jev improved routing on the tested workload | No route changed; SLO-aware p95 rose from 77.93 ms to 490.38 ms | High negative finding for that fixture | Too small to infer that Jev never helps |
| Backend quality estimates are calibrated | No held-out reliability analysis exists | Unsupported | Requires a real all-backend response matrix |
| The router improves real-model quality or production economics | No real completion-model/load experiment exists | Unsupported | Requires real endpoints, actual usage, stronger baselines, and held-out labels |
| Traces omit raw prompts | Zero `messages` keys in 40 video and 1,176 sweep traces | High for checked artifacts | SHA-256 identifiers remain linkable pseudonyms |

Evidence grades follow the report convention: repository artifacts are primary evidence for what this implementation did; peer-reviewed papers and official specifications support evaluation methods; vendor documentation supports Jev/API behavior; vendor marketing is not used to establish router efficacy.
