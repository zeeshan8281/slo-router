#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

log_dir="$(mktemp -d)"
pids=()
cleanup() {
  if ((${#pids[@]})); then
    kill "${pids[@]}" 2>/dev/null || true
    wait "${pids[@]}" 2>/dev/null || true
  fi
  python3 -c 'import shutil,sys; shutil.rmtree(sys.argv[1], ignore_errors=True)' "$log_dir"
}
trap cleanup EXIT INT TERM

python3 - "$log_dir/config.json" <<'PY'
import json, sys
config = json.load(open("config.video.json"))
config["trace_path"] = "results/sweep-traces.jsonl"
json.dump(config, open(sys.argv[1], "w"))
PY

SLO_SIM_TIER=fast SLO_SIM_LATENCY_MS=80 SLO_SIM_CONCURRENCY=1 \
  python3 -m uvicorn slo_router.sim_backend:app --host 127.0.0.1 --port 8101 \
  >"$log_dir/cheap.log" 2>&1 &
pids+=("$!")

SLO_SIM_TIER=strong SLO_SIM_LATENCY_MS=80 SLO_SIM_CONCURRENCY=16 \
  python3 -m uvicorn slo_router.sim_backend:app --host 127.0.0.1 --port 8102 \
  >"$log_dir/capacity.log" 2>&1 &
pids+=("$!")

SLO_ROUTER_API_KEY=demo SLO_ROUTER_CONFIG="$log_dir/config.json" \
  python3 -m uvicorn slo_router.service:app --host 127.0.0.1 --port 8100 \
  >"$log_dir/router.log" 2>&1 &
pids+=("$!")

for _ in {1..50}; do
  curl --silent --fail http://127.0.0.1:8100/health >/dev/null && break
  sleep 0.1
done
curl --silent --fail http://127.0.0.1:8100/health >/dev/null || {
  cat "$log_dir/router.log"
  exit 1
}

rm -f results/sweep-traces.jsonl results/sweep-replay.jsonl \
  results/sweep-summary.json results/sweep-analysis.md
PYTHONPATH=. python3 scripts/experiment_sweeps.py
