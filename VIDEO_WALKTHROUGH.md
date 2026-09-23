# SLO Router walkthrough video

Target length: 4–5 minutes. Record at 1440p with the terminal font at 18–20 px. Keep the repository page, architecture file, terminal, and generated SVG open before recording.

## 0:00–0:20 — Hook

**Screen:** GitHub repository title and README headline.

**Say:**

> I built an SLO-aware inference router that uses Jev for typed workload classification, then chooses the lowest-cost model predicted to satisfy both quality and latency constraints under live backend load. Unlike a normal model router, it can change its decision when a cheap backend starts queueing.

## 0:20–1:00 — Request path

**Screen:** Open `diagrams/slo-router-architecture.excalidraw` in Excalidraw.

**Say:**

> The client sends a normal OpenAI-compatible request. Jev can classify the workload and produce bounded semantic signals such as task type and exactness. The constrained router combines those signals with model quality priors, cost, context limits, queue depth, and predicted execution time. It then chooses the cheapest backend that remains feasible for the request's latency objective.

> Jev is optional and cached. If it times out or fails, routing falls back to deterministic local features instead of blocking inference.

## 1:00–1:35 — Experiment setup

**Screen:** Show `config.video.json`, focusing on the two backends and the 400 ms default SLO.

**Say:**

> This experiment has two deterministic backends. The cheap backend costs one tenth as much but accepts one concurrent request. The capacity backend costs more but accepts sixteen. Both produce the same correct answers, so this isolates routing and queue behaviour rather than claiming a model benchmark.

> I send the exact same ten-request burst through four policies and reset router state between runs.

## 1:35–2:25 — Run it

**Screen:** A clean terminal at the repository root.

```sh
make video-demo
```

Pause on the printed table.

**Say:**

> Fixed-cheapest and quality-only send all ten requests to the cheap backend. Accuracy stays at one hundred percent, but only forty percent finish within 400 milliseconds and p95 rises above 800 milliseconds.

> Fixed-strongest meets every deadline, but sends all traffic to the expensive backend.

> The SLO policy observes the accumulating load, keeps four requests on the cheap backend, shifts six to available capacity, and reaches one hundred percent SLO success. Its predicted cost is lower than fixed-strongest because it uses expensive capacity only where the deadline requires it.

## 2:25–3:05 — Decision trace

**Screen:** Pretty-print the last SLO trace.

```sh
python3 - <<'PY'
import json
rows = [json.loads(line) for line in open("results/video-traces.jsonl")]
row = next(row for row in reversed(rows) if row["policy"] == "slo_no_jev")
print(json.dumps({
  "policy": row["policy"],
  "chosen_backend": row["chosen_backend"],
  "predicted_ms": row["predicted_ms"],
  "actual_ms": row["actual_ms"],
  "slo_met": row["slo_met"],
  "candidates": row["candidates"],
  "prompt_sha256": row["prompt_sha256"][:16] + "..."
}, indent=2))
PY
```

**Say:**

> Every route produces an auditable decision trace: the selected backend, every candidate estimate, the policy revision inputs, predicted and actual latency, and whether the SLO was met. The trace stores a prompt hash instead of raw prompt text so decisions can be grouped and replayed without writing the prompt into telemetry.

## 3:05–3:45 — Jev result

**Screen:** Open `results/live-jev-analysis.md` and highlight the result table.

**Say:**

> I also ran the feature stage against the real Jev 1.13 endpoint. All sixteen decision calls succeeded. On this tiny deterministic workload, Jev preserved the same routes and accuracy but increased p95 latency, so the repository reports that negative result directly. The production baseline remains local SLO routing; Jev becomes useful when its semantic decisions improve routing enough to justify the extra latency, or when features are precomputed and cached.

## 3:45–4:15 — Close

**Screen:** Return to GitHub and show the run commands and files.

**Say:**

> The repository includes the OpenAI-compatible proxy, local simulators, Jev integration, queue-aware routing, counterfactual matrix collection, policy replay, hashed traces, and reproducible reports. Clone it, replace the simulated endpoints with OpenRouter, vLLM, or another OpenAI-compatible backend, and fit the quality priors on your own workload.

On-screen final line:

> `github.com/zeeshan8281/slo-router`
