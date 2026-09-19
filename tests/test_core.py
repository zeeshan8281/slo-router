import asyncio
import json
from pathlib import Path

import httpx
import pytest

from slo_router.core import Features, Runtime, Settings, choose, estimate, get_features, prefix_key
from slo_router.core import lexical_features
from slo_router.service import ChatRequest, create_app


CONFIG = Path(__file__).parents[1] / "config.example.json"


def test_policy_respects_quality_context_and_slo():
    settings = Settings.model_validate_json(CONFIG.read_text())
    feature = Features("code_debugging", 0.9, "test")
    prefix = prefix_key([{"role": "user", "content": "debug"}], "a")
    candidates = [estimate(b, Runtime(), feature, 100, 100, 10000, prefix, False, 0) for b in settings.backends]
    selected, _ = choose(candidates, "slo", 0.85, 0.8)
    assert selected.backend.name == "strong"
    no_context = [estimate(b, Runtime(), feature, 40000, 100, 10000, prefix, False, 0) for b in settings.backends]
    assert choose(no_context, "slo", 0.85, 0.8)[0] is None
    assert choose(candidates, "slo", 0.85, 1.0)[0] is None
    assert lexical_features([{"role": "user", "content": "What is 9*7?"}]).exactness == 0.9


@pytest.mark.asyncio
async def test_jev_decision_and_fallback():
    def handler(request):
        assert request.url.path == "/api/alpha/decisions"
        return httpx.Response(200, json={"answers": {"task_type": {"choice": "code_debugging"},
                                                     "exactness": {"noul": 0.94},
                                                     "external_evidence": {"noul": 0.1}},
                                         "usage": {"input_tokens": 100}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await get_features(client, [{"role": "user", "content": "Fix kernel"}], "key", 100)
        assert (result.task, result.exactness, result.source) == ("code_debugging", 0.94, "jev")
        assert result.cost_usd == pytest.approx(0.0000042)

    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(429))) as client:
        result = await get_features(client, [{"role": "user", "content": "Debug CUDA"}], "key", 100)
        assert result.source == "lexical_fallback"


@pytest.mark.asyncio
async def test_proxy_nonstream_and_stream(tmp_path, monkeypatch):
    settings = json.loads(CONFIG.read_text())
    settings["trace_path"] = str(tmp_path / "traces.jsonl")
    path = tmp_path / "config.json"
    path.write_text(json.dumps(settings))
    app = create_app(str(path))

    def backend(request):
        if request.url.path == "/metrics":
            return httpx.Response(200, text="vllm:num_requests_waiting 0\n")
        assert request.url.path == "/v1/chat/completions"
        body = json.loads(request.content)
        assert body["model"] in ("fast-model", "strong-model")
        assert "slo_ms" not in body
        if body.get("stream"):
            return httpx.Response(200, headers={"content-type": "text/event-stream"},
                                  content=b'data: {"choices":[{"delta":{"content":"ok"}}]}\n\ndata: [DONE]\n\n')
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}], "usage": {"total_tokens": 3}})

    await app.state.router.client.aclose()
    app.state.router.client = httpx.AsyncClient(transport=httpx.MockTransport(backend))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://router") as client:
        request = {"messages": [{"role": "user", "content": "Extract this"}], "policy": "fixed_cheapest"}
        response = await client.post("/v1/chat/completions", json=request)
        assert response.status_code == 200
        assert response.headers["X-SLO-Route"] == "fast"
        assert response.json()["choices"][0]["message"]["content"] == "ok"
        streamed = await client.post("/v1/chat/completions", json={**request, "stream": True})
        assert streamed.status_code == 200
        assert "data: [DONE]" in streamed.text
        invalid = await client.post("/v1/chat/completions", json={**request, "policy": "bad"})
        assert invalid.status_code == 400
        evidence = await client.post("/v1/chat/completions", json={
            "messages": [{"role": "user", "content": "What is the latest price today?"}],
            "policy": "fixed_cheapest",
        })
        assert evidence.status_code == 503
        assert all(item["reason"] == "tools_unsupported" for item in evidence.json()["detail"]["candidates"])
    await app.state.router.close()
    traces = [json.loads(x) for x in (tmp_path / "traces.jsonl").read_text().splitlines()]
    assert len(traces) == 2
    assert all("prompt_sha256" in x and "messages" not in x for x in traces)
    assert traces[0]["feature_vector"]["task"] == "extraction"
    assert traces[0]["feature_vector"]["task_probabilities"] is None


@pytest.mark.asyncio
async def test_jev_cache_is_revisioned_and_tenant_scoped(tmp_path):
    settings = json.loads(CONFIG.read_text())
    settings["trace_path"] = str(tmp_path / "traces.jsonl")
    path = tmp_path / "config.json"
    path.write_text(json.dumps(settings))
    app = create_app(str(path))
    calls = 0

    def jev(request):
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={
            "answers": {"task_type": {"choice": "reasoning"}, "exactness": {"noul": 0.7},
                        "external_evidence": {"noul": 0.2}},
            "usage": {"input_tokens": 50},
        })

    await app.state.router.client.aclose()
    app.state.router.client = httpx.AsyncClient(transport=httpx.MockTransport(jev))
    base = {"messages": [{"role": "user", "content": "Why?"}], "policy": "slo"}
    first = await app.state.router.features(ChatRequest(**base, tenant="a"), "key")
    cached = await app.state.router.features(ChatRequest(**base, tenant="a"), "key")
    isolated = await app.state.router.features(ChatRequest(**base, tenant="b"), "key")
    assert (first.source, cached.source, isolated.source) == ("jev", "jev_cache", "jev")
    assert cached.cost_usd == 0
    assert calls == 2
    await app.state.router.close()


@pytest.mark.asyncio
async def test_backend_overload_falls_back_before_response_starts(tmp_path):
    settings = json.loads(CONFIG.read_text())
    settings["trace_path"] = str(tmp_path / "traces.jsonl")
    path = tmp_path / "config.json"
    path.write_text(json.dumps(settings))
    app = create_app(str(path))

    def backend(request):
        if request.url.path == "/metrics":
            return httpx.Response(200, text="vllm:num_requests_waiting 0\n")
        if request.url.port == 8101:
            return httpx.Response(503, text="overloaded")
        return httpx.Response(200, json={"choices": [{"message": {"content": "strong"}}],
                                         "usage": {"prompt_tokens": 2, "completion_tokens": 1}})

    await app.state.router.client.aclose()
    app.state.router.client = httpx.AsyncClient(transport=httpx.MockTransport(backend))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://router") as client:
        response = await client.post("/v1/chat/completions", json={
            "messages": [{"role": "user", "content": "Extract this"}], "policy": "fixed_cheapest"
        })
    assert response.status_code == 200
    assert response.headers["X-SLO-Route"] == "strong"
    trace = json.loads((tmp_path / "traces.jsonl").read_text())
    assert trace["failed_attempts"][0]["backend"] == "fast"
    assert app.state.router.runtime["fast"].active == 0
    await app.state.router.close()
