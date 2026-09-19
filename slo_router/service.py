import asyncio
import hashlib
import json
import os
import re
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from .core import QUESTION_REVISION, Backend, Runtime, Settings, choose, count_tokens_approx, estimate, get_features, lexical_features, prefix_key


class ChatRequest(BaseModel):
    messages: List[Dict[str, Any]] = Field(min_length=1)
    model: str = "auto"
    stream: bool = False
    max_tokens: int = Field(default=256, gt=0)
    temperature: Optional[float] = None
    tools: Optional[List[Dict[str, Any]]] = None
    slo_ms: Optional[int] = Field(default=None, gt=0)
    quality_floor: Optional[float] = Field(default=None, ge=0, le=1)
    tenant: str = "default"
    policy: str = "slo"


def load_settings(path: str) -> Settings:
    return Settings.model_validate_json(Path(path).read_text())


class Router:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.runtime = {b.name: Runtime() for b in settings.backends}
        self.client = httpx.AsyncClient(timeout=60)
        self.last_metrics_poll = {b.name: 0.0 for b in settings.backends}
        self.feature_cache: Dict[str, Any] = {}
        self.trace_path = Path(settings.trace_path)
        self.trace_path.parent.mkdir(parents=True, exist_ok=True)
        self.trace_lock = asyncio.Lock()

    async def close(self) -> None:
        await self.client.aclose()

    async def poll_metrics(self, backend: Backend) -> None:
        if not backend.metrics_url or time.monotonic() - self.last_metrics_poll[backend.name] < 1:
            return
        self.last_metrics_poll[backend.name] = time.monotonic()
        try:
            response = await self.client.get(str(backend.metrics_url), timeout=0.3)
            response.raise_for_status()
            matches = re.findall(r"^vllm:num_requests_waiting(?:\{[^}]*\})?\s+([\d.]+)$", response.text, re.M)
            self.runtime[backend.name].waiting = int(sum(float(x) for x in matches))
        except (httpx.HTTPError, ValueError):
            pass

    async def trace(self, record: Dict[str, Any]) -> None:
        async with self.trace_lock:
            with self.trace_path.open("a") as handle:
                handle.write(json.dumps(record, separators=(",", ":")) + "\n")

    async def features(self, body: ChatRequest, jev_key: Optional[str]):
        if body.policy in ("fixed_cheapest", "fixed_strongest", "slo_no_jev") or not jev_key:
            return lexical_features(body.messages)
        cache_payload = json.dumps([QUESTION_REVISION, body.tenant, body.messages], sort_keys=True, ensure_ascii=False)
        cache_key = hashlib.sha256(cache_payload.encode()).hexdigest()
        cached = self.feature_cache.get(cache_key)
        if cached and time.monotonic() - cached[0] <= self.settings.jev_cache_ttl_seconds:
            return replace(cached[1], source="jev_cache", latency_ms=0.0, cost_usd=0.0)
        result = await get_features(self.client, body.messages, jev_key, self.settings.jev_timeout_ms,
                                    self.settings.jev_input_per_million)
        if result.source == "jev" and self.settings.jev_cache_ttl_seconds:
            self.feature_cache[cache_key] = (time.monotonic(), result)
            if len(self.feature_cache) > 1000:
                oldest = min(self.feature_cache, key=lambda key: self.feature_cache[key][0])
                del self.feature_cache[oldest]
        return result

    async def prepare(self, body: ChatRequest, jev_key: Optional[str]) -> Dict[str, Any]:
        if body.model != "auto":
            raise HTTPException(400, "model must be 'auto'; backend models are internal")
        if body.policy not in ("slo", "fixed_cheapest", "fixed_strongest", "quality_only", "slo_no_jev"):
            raise HTTPException(400, "unknown policy")
        if not body.tenant or len(body.tenant) > 128:
            raise HTTPException(400, "invalid tenant")
        policy = "slo" if body.policy == "slo_no_jev" else body.policy
        features = await self.features(body, jev_key)
        input_tokens = count_tokens_approx(body.messages)
        prefix = prefix_key(body.messages, body.tenant)
        await asyncio.gather(*(self.poll_metrics(b) for b in self.settings.backends))
        slo_ms = body.slo_ms or self.settings.default_slo_ms
        quality_floor = body.quality_floor if body.quality_floor is not None else self.settings.default_quality_floor
        # Exact requests should not be silently sent to a backend below the configured bar.
        if features.exactness >= 0.8:
            quality_floor = max(quality_floor, 0.85)
        requires_tools = bool(body.tools) or features.needs_evidence >= 0.8
        candidates = [estimate(b, self.runtime[b.name], features, input_tokens, body.max_tokens, slo_ms, prefix,
                               requires_tools, features.latency_ms) for b in self.settings.backends]
        selected, reason = choose(candidates, policy, quality_floor, self.settings.slo_success_floor)
        return {
            "features": features, "input_tokens": input_tokens, "prefix": prefix,
            "selected": selected, "reason": reason, "candidates": candidates,
            "quality_floor": quality_floor, "slo_ms": slo_ms,
        }


def create_app(settings_path: Optional[str] = None) -> FastAPI:
    path = settings_path or os.environ.get("SLO_ROUTER_CONFIG", "config.example.json")
    router = Router(load_settings(path))
    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        await router.close()

    app = FastAPI(title="SLO Router", version="0.1.0", lifespan=lifespan)
    app.state.router = router

    @app.get("/health")
    async def health() -> Dict[str, Any]:
        return {"ok": True, "backends": [b.name for b in router.settings.backends]}

    @app.post("/admin/reset")
    async def reset(authorization: Optional[str] = Header(default=None)) -> Dict[str, bool]:
        router_key = os.environ.get("SLO_ROUTER_API_KEY")
        if not router_key or authorization != "Bearer " + router_key:
            raise HTTPException(401, "admin reset requires SLO_ROUTER_API_KEY")
        if any(runtime.active for runtime in router.runtime.values()):
            raise HTTPException(409, "cannot reset while requests are active")
        router.runtime = {b.name: Runtime() for b in router.settings.backends}
        router.feature_cache.clear()
        return {"reset": True}

    @app.post("/v1/chat/completions")
    async def chat(body: ChatRequest, request: Request, authorization: Optional[str] = Header(default=None)):
        router_key = os.environ.get("SLO_ROUTER_API_KEY")
        if router_key and authorization != "Bearer " + router_key:
            raise HTTPException(401, "invalid router key")
        started = time.perf_counter()
        prepared = await router.prepare(body, os.environ.get("OPENROUTER_API_KEY"))
        selected = prepared["selected"]
        if selected is None:
            raise HTTPException(503, {"error": prepared["reason"], "candidates": [
                {"backend": c.backend.name, "reason": c.reason, "quality": c.quality,
                 "slo_probability": c.slo_probability} for c in prepared["candidates"]]})
        request_id = str(uuid.uuid4())
        prompt_hash = hashlib.sha256(json.dumps(body.messages, sort_keys=True).encode()).hexdigest()
        attempted = []
        upstream = None
        payload = body.model_dump(exclude={"slo_ms", "quality_floor", "tenant", "policy"}, exclude_none=True)
        route_policy = "slo" if body.policy == "slo_no_jev" else body.policy
        while selected is not None:
            backend = selected.backend
            runtime = router.runtime[backend.name]
            payload["model"] = backend.model
            headers = {"Content-Type": "application/json"}
            if backend.api_key_env and os.environ.get(backend.api_key_env):
                headers["Authorization"] = "Bearer " + os.environ[backend.api_key_env]
            runtime.active += 1
            try:
                upstream_request = router.client.build_request(
                    "POST", str(backend.url).rstrip("/") + "/v1/chat/completions", json=payload, headers=headers
                )
                upstream = await router.client.send(upstream_request, stream=True)
                if upstream.status_code == 429 or upstream.status_code >= 500:
                    failure_body = (await upstream.aread()).decode(errors="replace")[:500]
                    await upstream.aclose()
                    runtime.active -= 1
                    runtime.unhealthy_until = time.monotonic() + 5
                    attempted.append({"backend": backend.name, "status": upstream.status_code,
                                      "detail": failure_body})
                    upstream = None
                else:
                    break
            except httpx.HTTPError as exc:
                runtime.active -= 1
                runtime.unhealthy_until = time.monotonic() + 5
                attempted.append({"backend": backend.name, "error": type(exc).__name__})
            remaining = [candidate for candidate in prepared["candidates"]
                         if candidate.backend.name not in {attempt["backend"] for attempt in attempted}]
            selected, _ = choose(remaining, route_policy, prepared["quality_floor"],
                                 router.settings.slo_success_floor)
        if selected is None or upstream is None:
            await router.trace({
                "request_id": request_id, "timestamp": time.time(), "prompt_sha256": prompt_hash,
                "tenant_sha256": hashlib.sha256(body.tenant.encode()).hexdigest(),
                "policy": body.policy, "error": "all_backends_failed", "attempted": attempted,
                "actual_ms": (time.perf_counter() - started) * 1000,
            })
            raise HTTPException(502, {"error": "all_backends_failed", "attempted": attempted})
        backend = selected.backend
        runtime = router.runtime[backend.name]
        common = {
            "request_id": request_id, "timestamp": time.time(), "prompt_sha256": prompt_hash,
            "tenant_sha256": hashlib.sha256(body.tenant.encode()).hexdigest(),
            "policy": body.policy, "chosen_backend": backend.name, "task": prepared["features"].task,
            "feature_source": prepared["features"].source, "feature_latency_ms": prepared["features"].latency_ms,
            "feature_cost_usd": prepared["features"].cost_usd,
            "needs_external_evidence": prepared["features"].needs_evidence,
            "feature_vector": {
                "task": prepared["features"].task,
                "exactness": prepared["features"].exactness,
                "needs_external_evidence": prepared["features"].needs_evidence,
                "task_probabilities": ((prepared["features"].raw.get("answers") or {})
                                       .get("task_type", {}).get("probabilities")),
            },
            "input_tokens_estimate": prepared["input_tokens"], "output_tokens_budget": body.max_tokens,
            "predicted_ms": selected.predicted_ms, "predicted_slo_probability": selected.slo_probability,
            "predicted_quality": selected.quality, "predicted_cost_usd": selected.cost_usd,
            "slo_ms": prepared["slo_ms"], "quality_floor": prepared["quality_floor"],
            "failed_attempts": attempted,
            "candidates": [{"backend": c.backend.name, "eligible": c.eligible, "reason": c.reason,
                            "quality": c.quality, "predicted_ms": c.predicted_ms,
                            "slo_probability": c.slo_probability, "cost_usd": c.cost_usd}
                           for c in prepared["candidates"]],
        }
        response_headers = {"X-SLO-Route": backend.name, "X-SLO-Request-ID": request_id}
        response_headers.update({
            "X-SLO-Predicted-Latency-Ms": "%.3f" % selected.predicted_ms,
            "X-SLO-Predicted-Quality": "%.6f" % selected.quality,
            "X-SLO-Predicted-Cost-Usd": "%.9f" % selected.cost_usd,
            "X-SLO-Feature-Source": prepared["features"].source,
        })
        if upstream.status_code >= 400:
            data = await upstream.aread()
            await upstream.aclose()
            runtime.active -= 1
            await router.trace({**common, "upstream_status": upstream.status_code,
                                "actual_ms": (time.perf_counter() - started) * 1000})
            return JSONResponse(status_code=upstream.status_code,
                                content={"error": "backend returned error", "detail": data.decode(errors="replace")[:2000]},
                                headers=response_headers)
        if not body.stream:
            try:
                data = await upstream.aread()
                response = json.loads(data)
                if not isinstance(response, dict) or not isinstance(response.get("choices"), list):
                    raise ValueError("invalid OpenAI response shape")
            except (httpx.HTTPError, ValueError) as exc:
                await router.trace({**common, "error": type(exc).__name__})
                raise HTTPException(502, "invalid backend response") from exc
            finally:
                await upstream.aclose()
                runtime.active -= 1
            actual_ms = (time.perf_counter() - started) * 1000
            usage = response.get("usage") or {}
            if not isinstance(usage, dict):
                usage = {}
            actual_cost = prepared["features"].cost_usd + (
                float(usage.get("prompt_tokens", prepared["input_tokens"])) * backend.input_per_million
                + float(usage.get("completion_tokens", body.max_tokens)) * backend.output_per_million
            ) / 1_000_000
            runtime.record(actual_ms, prepared["prefix"])
            await router.trace({**common, "upstream_status": upstream.status_code, "actual_ms": actual_ms,
                                "slo_met": actual_ms <= prepared["slo_ms"], "usage": usage,
                                "actual_cost_usd": actual_cost})
            return JSONResponse(content=response, headers=response_headers)

        async def stream():
            first_token_ms = None
            disconnected = False
            try:
                async for chunk in upstream.aiter_bytes():
                    if await request.is_disconnected():
                        disconnected = True
                        break
                    if first_token_ms is None and chunk:
                        first_token_ms = (time.perf_counter() - started) * 1000
                    yield chunk
            finally:
                await upstream.aclose()
                runtime.active -= 1
                actual_ms = (time.perf_counter() - started) * 1000
                if not disconnected:
                    runtime.record(actual_ms, prepared["prefix"])
                await router.trace({**common, "upstream_status": upstream.status_code, "actual_ms": actual_ms,
                                    "ttft_ms": first_token_ms, "disconnected": disconnected,
                                    "slo_met": actual_ms <= prepared["slo_ms"] if not disconnected else None})

        return StreamingResponse(stream(), media_type=upstream.headers.get("content-type", "text/event-stream"),
                                 headers=response_headers)

    return app


app = create_app() if os.environ.get("SLO_ROUTER_CONFIG") else None
