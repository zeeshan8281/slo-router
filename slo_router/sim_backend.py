"""Deterministic backend for exercising the full proxy/replay path without API keys."""
import asyncio
import json
import os
import time
from typing import Any, Dict

from fastapi import FastAPI
from fastapi.responses import StreamingResponse


ANSWERS = {
    "What is 2+2?": "4",
    "Extract the color from: the car is blue.": "blue",
    "Summarize: Alice moved to Paris on Tuesday.": "Alice moved to Paris.",
    "Why does a CUDA barrier inside a divergent branch deadlock?": "Some threads never reach the barrier.",
    "Explain why a cache key must include the tenant.": "It prevents cross-tenant cache reuse.",
    "Extract the city from: Bob lives in Rome.": "Rome",
    "What is 9*7?": "63",
    "Summarize: The service restarted after memory exhaustion.": "The service restarted after OOM.",
}


def create_app(tier: str = "fast") -> FastAPI:
    app = FastAPI(title="SLO Router simulated " + tier)
    latency_seconds = float(os.environ.get("SLO_SIM_LATENCY_MS", "25" if tier == "fast" else "65")) / 1000
    capacity = int(os.environ.get("SLO_SIM_CONCURRENCY", "1000"))
    if latency_seconds < 0 or capacity < 1:
        raise ValueError("simulator latency must be non-negative and concurrency must be positive")
    slots = asyncio.Semaphore(capacity)
    active = 0
    waiting = 0

    @app.get("/health")
    async def health():
        return {"ok": True, "tier": tier}

    @app.get("/metrics")
    async def metrics():
        return "vllm:num_requests_waiting %d\nvllm:num_requests_running %d\n" % (waiting, active)

    @app.post("/v1/chat/completions")
    async def completion(body: Dict[str, Any]):
        nonlocal active, waiting
        waiting += 1
        await slots.acquire()
        waiting -= 1
        active += 1
        try:
            prompt = next((m.get("content", "") for m in reversed(body.get("messages", [])) if m.get("role") == "user"), "")
            answer = ANSWERS.get(prompt, "unknown")
            if tier == "fast" and ("CUDA" in prompt or "cache key" in prompt or "9*7" in prompt):
                answer = "I am not sure."
            await asyncio.sleep(latency_seconds)
            response = {
                "id": "sim-" + str(time.time_ns()), "object": "chat.completion", "model": tier,
                "choices": [{"index": 0, "message": {"role": "assistant", "content": answer}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": max(1, len(prompt) // 4), "completion_tokens": max(1, len(answer) // 4),
                          "total_tokens": max(2, (len(prompt) + len(answer)) // 4)},
            }
            if not body.get("stream"):
                return response

            async def events():
                yield "data: " + json.dumps({"choices": [{"delta": {"content": answer}}]}) + "\n\n"
                yield "data: [DONE]\n\n"

            return StreamingResponse(events(), media_type="text/event-stream")
        finally:
            active -= 1
            slots.release()

    return app


app = create_app(os.environ.get("SLO_SIM_TIER", "fast"))
