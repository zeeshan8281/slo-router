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

SLO_SIM_TIER=fast SLO_SIM_LATENCY_MS=80 SLO_SIM_CONCURRENCY=1 \
  python3 -m uvicorn slo_router.sim_backend:app --host 127.0.0.1 --port 8101 \
  >"$log_dir/cheap.log" 2>&1 &
pids+=("$!")

SLO_SIM_TIER=strong SLO_SIM_LATENCY_MS=80 SLO_SIM_CONCURRENCY=16 \
  python3 -m uvicorn slo_router.sim_backend:app --host 127.0.0.1 --port 8102 \
  >"$log_dir/capacity.log" 2>&1 &
pids+=("$!")

SLO_ROUTER_API_KEY=demo SLO_ROUTER_CONFIG=config.video.json \
  python3 -m uvicorn slo_router.service:app --host 127.0.0.1 --port 8100 \
  >"$log_dir/router.log" 2>&1 &
pids+=("$!")

for _ in {1..50}; do
  if curl --silent --fail http://127.0.0.1:8100/health >/dev/null; then
    break
  fi
  sleep 0.1
done
curl --silent --fail http://127.0.0.1:8100/health >/dev/null || {
  cat "$log_dir/router.log"
  exit 1
}

python3 - <<'PY'
from pathlib import Path
for name in ("video-traces.jsonl", "video-replay.jsonl", "video-results.md", "video-results.svg"):
    Path("results", name).unlink(missing_ok=True)
PY

echo "Running the same 10-request burst through four routing policies..."
python3 -m slo_router.replay data/video-burst.jsonl \
  --router-key demo \
  --policies fixed_cheapest,fixed_strongest,quality_only,slo_no_jev \
  --output results/video-replay.jsonl

python3 -m slo_router.report results/video-replay.jsonl \
  --output results/video-results.md \
  --svg results/video-results.svg >/dev/null

echo
cat results/video-results.md
