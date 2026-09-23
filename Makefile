.PHONY: test sim-fast sim-strong serve matrix fit replay report video-demo

test:
	python3 -m pytest -q

sim-fast:
	python3 -m uvicorn slo_router.sim_backend:app --host 127.0.0.1 --port 8101

sim-strong:
	SLO_SIM_TIER=strong python3 -m uvicorn slo_router.sim_backend:app --host 127.0.0.1 --port 8102

serve:
	SLO_ROUTER_CONFIG=config.example.json python3 -m uvicorn slo_router.service:app --host 127.0.0.1 --port 8100

matrix:
	python3 -m slo_router.matrix collect data/demo.jsonl --output matrix.jsonl

fit:
	python3 -m slo_router.matrix fit matrix.jsonl --output config.fitted.json --report fit-report.json

replay:
	python3 -m slo_router.replay data/demo.jsonl --router-key "$${SLO_ROUTER_API_KEY}" --output replay-results.jsonl

report:
	python3 -m slo_router.report replay-results.jsonl

video-demo:
	./scripts/video-demo.sh
