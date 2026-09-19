import hashlib
import json
import math
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import httpx
from pydantic import BaseModel, Field, HttpUrl, field_validator


TASKS = ("extraction", "summarization", "reasoning", "code_debugging", "other")
QUESTION_REVISION = "2026-09-19-v1"


class Backend(BaseModel):
    name: str
    url: HttpUrl
    model: str
    input_per_million: float = Field(ge=0)
    output_per_million: float = Field(ge=0)
    max_context_tokens: int = Field(gt=0)
    prefill_tokens_per_second: float = Field(gt=0)
    decode_tokens_per_second: float = Field(gt=0)
    base_latency_ms: float = Field(ge=0)
    quality: Dict[str, float]
    api_key_env: Optional[str] = None
    metrics_url: Optional[HttpUrl] = None
    supports_tools: bool = False

    @field_validator("quality")
    @classmethod
    def valid_quality(cls, value: Dict[str, float]) -> Dict[str, float]:
        if not all(k in value and 0 <= value[k] <= 1 for k in TASKS):
            raise ValueError("quality needs probabilities for every task")
        return value


class Settings(BaseModel):
    backends: List[Backend] = Field(min_length=1)
    default_slo_ms: int = Field(default=10000, gt=0)
    default_quality_floor: float = Field(default=0.7, ge=0, le=1)
    slo_success_floor: float = Field(default=0.8, ge=0, le=1)
    jev_timeout_ms: int = Field(default=700, gt=0)
    jev_input_per_million: float = Field(default=0.042, ge=0)
    jev_cache_ttl_seconds: int = Field(default=300, ge=0)
    trace_path: str = "traces.jsonl"

    @field_validator("backends")
    @classmethod
    def unique_names(cls, value: List[Backend]) -> List[Backend]:
        if len({b.name for b in value}) != len(value):
            raise ValueError("backend names must be unique")
        return value


@dataclass
class Features:
    task: str
    exactness: float
    source: str
    needs_evidence: float = 0.0
    latency_ms: float = 0.0
    cost_usd: float = 0.0
    raw: Dict[str, Any] = field(default_factory=dict)


def user_text(messages: List[Dict[str, Any]]) -> str:
    parts = []
    for message in messages:
        if message.get("role") != "user":
            continue
        content = message.get("content", "")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            parts.extend(x.get("text", "") for x in content if isinstance(x, dict) and x.get("type") == "text")
    return "\n".join(parts)


def lexical_features(messages: List[Dict[str, Any]]) -> Features:
    text = user_text(messages).lower()
    arithmetic = bool(re.search(r"(?:\d\s*[-+*/%^]\s*\d)|\b(calculate|compute|arithmetic)\b", text))
    if arithmetic:
        task = "reasoning"
    elif re.search(r"\b(cuda|kernel|stack trace|traceback|debug|bug|code|python|rust)\b", text):
        task = "code_debugging"
    elif re.search(r"\b(prove|reason|derive|why|analyze|compare)\b", text):
        task = "reasoning"
    elif re.search(r"\b(summarize|summary|tl;dr)\b", text):
        task = "summarization"
    elif re.search(r"\b(extract|find|which|what|list)\b", text):
        task = "extraction"
    else:
        task = "other"
    exactness = 0.9 if arithmetic or re.search(r"\b(exact|correct|proof|bug|debug|calculate)\b", text) else 0.3
    evidence = 0.9 if re.search(r"\b(latest|current|today|source|citation|verify|web|price|news)\b", text) else 0.1
    return Features(task=task, exactness=exactness, source="lexical", needs_evidence=evidence)


def count_tokens_approx(messages: List[Dict[str, Any]]) -> int:
    # Approximation only; configure a model tokenizer before claiming exact context eligibility.
    return max(1, math.ceil(len(json.dumps(messages, ensure_ascii=False)) / 2))


def prefix_key(messages: List[Dict[str, Any]], tenant: str) -> str:
    prefix = [m for m in messages if m.get("role") in ("system", "developer")]
    if not prefix:
        return ""
    payload = json.dumps([tenant, prefix], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def jev_payload(messages: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "model": "typesafe/jev-1.13",
        "state": {"user_request": user_text(messages)[-12000:]},
        "questions": {
            "task_type": {
                "type": "choice",
                "instructions": "Which task best describes the user's request?",
                "criteria": {
                    "extraction": "Extract explicit facts from provided text",
                    "summarization": "Condense or rewrite supplied material",
                    "reasoning": "Multi-step reasoning or explanation",
                    "code_debugging": "Diagnose or repair code or an inference system",
                    "other": "None of the above",
                },
            },
            "exactness": {
                "type": "noul",
                "instructions": "Would a materially approximate or mistaken answer be unacceptable for this request?",
            },
            "external_evidence": {
                "type": "noul",
                "instructions": "Does answering correctly require current external evidence, retrieval, or browsing beyond model memory?",
            },
        },
    }


async def get_features(client: httpx.AsyncClient, messages: List[Dict[str, Any]], key: Optional[str], timeout_ms: int,
                       input_per_million: float = 0.042) -> Features:
    if not key:
        return lexical_features(messages)
    start = time.perf_counter()
    try:
        response = await client.post(
            "https://openrouter.ai/api/alpha/decisions",
            headers={"Authorization": "Bearer " + key},
            json=jev_payload(messages),
            timeout=timeout_ms / 1000,
        )
        response.raise_for_status()
        body = response.json()
        answers = body["answers"]
        task = answers["task_type"]["choice"]
        exactness = float(answers["exactness"]["noul"])
        evidence = float(answers["external_evidence"]["noul"])
        if (task not in TASKS or not math.isfinite(exactness) or not 0 <= exactness <= 1
                or not math.isfinite(evidence) or not 0 <= evidence <= 1):
            raise ValueError("invalid Jev response")
        usage = body.get("usage") or {}
        input_tokens = float(usage.get("input_tokens", 0))
        reported_cost = usage.get("cost")
        feature_cost = (float(reported_cost) if reported_cost is not None
                        else input_tokens * input_per_million / 1_000_000)
        if not math.isfinite(feature_cost) or feature_cost < 0:
            raise ValueError("invalid Jev cost")
        return Features(task=task, exactness=exactness, source="jev", needs_evidence=evidence,
                        latency_ms=(time.perf_counter() - start) * 1000,
                        cost_usd=feature_cost, raw=body)
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        fallback = lexical_features(messages)
        fallback.source = "lexical_fallback"
        fallback.latency_ms = (time.perf_counter() - start) * 1000
        return fallback


@dataclass
class Runtime:
    active: int = 0
    waiting: int = 0
    recent_latencies_ms: List[float] = field(default_factory=list)
    prefixes: Dict[str, float] = field(default_factory=dict)
    healthy: bool = True
    unhealthy_until: float = 0.0

    def record(self, latency_ms: float, prefix: str) -> None:
        self.recent_latencies_ms.append(latency_ms)
        self.recent_latencies_ms = self.recent_latencies_ms[-200:]
        if prefix:
            self.prefixes[prefix] = time.monotonic()
        if len(self.prefixes) > 1000:
            oldest = min(self.prefixes, key=self.prefixes.get)
            del self.prefixes[oldest]


@dataclass
class Candidate:
    backend: Backend
    quality: float
    predicted_ms: float
    slo_probability: float
    cost_usd: float
    eligible: bool
    reason: str


def estimate(backend: Backend, runtime: Runtime, features: Features, input_tokens: int, output_tokens: int,
             slo_ms: int, prefix: str, has_tools: bool, overhead_ms: float) -> Candidate:
    if not runtime.healthy or time.monotonic() < runtime.unhealthy_until:
        return Candidate(backend, 0, math.inf, 0, math.inf, False, "unhealthy")
    if input_tokens + output_tokens > backend.max_context_tokens:
        return Candidate(backend, 0, math.inf, 0, math.inf, False, "context_exceeded")
    if has_tools and not backend.supports_tools:
        return Candidate(backend, 0, math.inf, 0, math.inf, False, "tools_unsupported")
    prefix_hit = bool(prefix) and prefix in runtime.prefixes and time.monotonic() - runtime.prefixes[prefix] < 120
    uncached = input_tokens * (0.55 if prefix_hit else 1.0)
    prefill_ms = 1000 * uncached / backend.prefill_tokens_per_second
    decode_ms = 1000 * output_tokens / backend.decode_tokens_per_second
    queue_ms = 1000 * (runtime.waiting + runtime.active) * output_tokens / backend.decode_tokens_per_second
    predicted = backend.base_latency_ms + queue_ms + prefill_ms + decode_ms + overhead_ms
    history = sorted(runtime.recent_latencies_ms)
    if len(history) >= 10:
        p50 = history[len(history) // 2]
        p90 = history[min(len(history) - 1, math.ceil(0.9 * len(history)) - 1)]
        uncertainty = max(50.0, p90 - p50)
    else:
        uncertainty = max(100.0, 0.25 * predicted)
    slo_prob = 1 / (1 + math.exp(max(-50, min(50, (predicted - slo_ms) / uncertainty))))
    quality = backend.quality[features.task]
    # Exactness changes the required floor in the caller; it is not a magic quality correction.
    cost = features.cost_usd + (input_tokens * backend.input_per_million
                                + output_tokens * backend.output_per_million) / 1_000_000
    return Candidate(backend, quality, predicted, slo_prob, cost, True, "ok")


def choose(candidates: List[Candidate], policy: str, quality_floor: float, slo_floor: float) -> Tuple[Optional[Candidate], str]:
    eligible = [c for c in candidates if c.eligible]
    if not eligible:
        return None, "no_eligible_backend"
    if policy == "fixed_cheapest":
        return min(eligible, key=lambda c: (c.cost_usd, c.backend.name)), "fixed_cheapest"
    if policy == "fixed_strongest":
        return max(eligible, key=lambda c: (sum(c.backend.quality.values()) / len(c.backend.quality),
                                             -c.cost_usd)), "fixed_strongest"
    if policy == "quality_only":
        valid = [c for c in eligible if c.quality >= quality_floor]
        return (min(valid, key=lambda c: (c.cost_usd, c.backend.name)), "quality_only") if valid else (None, "quality_infeasible")
    if policy != "slo":
        raise ValueError("unknown policy")
    valid = [c for c in eligible if c.quality >= quality_floor and c.slo_probability >= slo_floor]
    if not valid:
        return None, "quality_or_slo_infeasible"
    return min(valid, key=lambda c: (c.cost_usd, c.predicted_ms)), "slo"
