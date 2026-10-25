"""
OpenAI-compatible chat completions over httpx: DeepInfra, OpenAI, NVIDIA NIM, vLLM, Ollama, Together and most
gateways speak this. No streaming (nothing here needs it, and a stalled stream is the worst failure mode).
Retries on 429 / 5xx / timeouts with backoff. Headers per call come from ``headers(unit)`` so a host can label
calls for its own meter (PegasusDMZ's proxy reads X-Pegasus-* headers and strips them).
"""

from __future__ import annotations

import asyncio
import json
import os
import random
from collections.abc import Callable, Sequence
from typing import Any

import httpx

from ..messages import Message, Reply, Tool, ToolCall

RETRY_STATUS = {408, 409, 429, 500, 502, 503, 504}


class OpenAICompatible:
    def __init__(self, model: str, *, base_url: str = "", api_key: str = "", timeout_s: float = 180.0,
                 max_retries: int = 3, max_tokens: int | None = None, reasoning_effort: str = "",
                 headers: Callable[[str], dict[str, str]] | None = None, client: httpx.AsyncClient | None = None,
                 extra_body: dict[str, Any] | None = None):
        self.name = model
        self.base_url = (base_url or os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        self.max_tokens = max_tokens
        self.reasoning_effort = reasoning_effort
        self.headers = headers
        self.extra_body = extra_body or {}
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(timeout_s, connect=15.0))

    async def complete(self, messages: Sequence[Message], tools: Sequence[Tool], *, temperature: float | None = None,
                       unit: str = "") -> Reply:
        body: dict[str, Any] = {"model": self.name, "messages": [m.to_openai() for m in messages], **self.extra_body}
        if tools:
            body["tools"] = [t.to_openai() for t in tools]
            body["tool_choice"] = "auto"
        if temperature is not None:
            body["temperature"] = temperature
        if self.max_tokens:
            body["max_tokens"] = self.max_tokens
        if self.reasoning_effort:
            body["reasoning_effort"] = self.reasoning_effort
        hdr = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        if self.headers:
            hdr.update(self.headers(unit))
        last: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                r = await self._client.post(f"{self.base_url}/chat/completions", json=body, headers=hdr)
                if r.status_code in RETRY_STATUS:
                    raise httpx.HTTPStatusError(f"{r.status_code}: {r.text[:200]}", request=r.request, response=r)
                r.raise_for_status()
                return _parse(r.json())
            except (httpx.TimeoutException, httpx.HTTPStatusError, httpx.TransportError) as e:
                last = e
                if isinstance(e, httpx.HTTPStatusError) and e.response.status_code not in RETRY_STATUS:
                    raise
                if attempt < self.max_retries:
                    await asyncio.sleep(min(30.0, (2 ** attempt) + random.random()))
        raise RuntimeError(f"{self.name}: gave up after {self.max_retries + 1} attempts: {last}")

    async def aclose(self) -> None:
        await self._client.aclose()


def _parse(data: dict[str, Any]) -> Reply:
    choice = (data.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    calls: list[ToolCall] = []
    for tc in msg.get("tool_calls") or []:
        fn = tc.get("function") or {}
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except json.JSONDecodeError:
            args = {"_raw": fn.get("arguments")}
        calls.append(ToolCall(str(tc.get("id") or f"call_{len(calls)}"), str(fn.get("name") or ""), args or {}))
    usage = data.get("usage") or {}
    details = usage.get("prompt_tokens_details") or {}
    content = msg.get("content")
    if isinstance(content, list):
        content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
    return Reply(content=str(content or ""), tool_calls=tuple(calls), input_tokens=int(usage.get("prompt_tokens") or 0),
                 cached_tokens=int(details.get("cached_tokens") or 0),
                 output_tokens=int(usage.get("completion_tokens") or 0), raw=data)
