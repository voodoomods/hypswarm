"""
Anthropic's Messages API as a seat's model (the ``[anthropic]`` extra). Maps hypswarm's provider-neutral messages
and tools onto Anthropic's shape — system as its own field, tool calls as ``tool_use`` blocks, tool results as
``tool_result`` blocks grouped into one user turn — and reads usage back, prompt-cache reads included.
No streaming, no retries beyond the SDK's own. The API has no sampling temperature, so a seat's ``temperature``
is ignored here; ``thinking_budget`` turns extended thinking on.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ..messages import Message, Reply, Tool, ToolCall


def to_anthropic(messages: Sequence[Message]) -> tuple[str, list[dict[str, Any]]]:
    """(system text, messages) in Anthropic's shape. Consecutive tool results become one user turn; consecutive
    same-role turns are merged, since the API wants roles to alternate."""
    system: list[str] = []
    out: list[dict[str, Any]] = []

    def push(role: str, blocks: list[dict[str, Any]]) -> None:
        if out and out[-1]["role"] == role:
            out[-1]["content"].extend(blocks)
        else:
            out.append({"role": role, "content": blocks})
    for m in messages:
        if m.role == "system":
            system.append(m.content)
        elif m.role == "user":
            push("user", [{"type": "text", "text": m.content or "(continue)"}])
        elif m.role == "assistant":
            blocks: list[dict[str, Any]] = []
            if m.content.strip():
                blocks.append({"type": "text", "text": m.content})
            blocks += [{"type": "tool_use", "id": t.id, "name": t.name, "input": t.args} for t in m.tool_calls]
            push("assistant", blocks or [{"type": "text", "text": "(no content)"}])
        elif m.role == "tool":
            push("user", [{"type": "tool_result", "tool_use_id": m.tool_call_id, "content": m.content}])
    return "\n\n".join(system), out


def tools_to_anthropic(tools: Sequence[Tool]) -> list[dict[str, Any]]:
    return [{"name": t.name, "description": t.description[:1024], "input_schema": t.parameters} for t in tools]


def from_anthropic(msg: Any) -> Reply:
    text, calls = [], []
    for block in getattr(msg, "content", None) or []:
        kind = getattr(block, "type", None)
        if kind == "text":
            text.append(str(getattr(block, "text", "")))
        elif kind == "tool_use":
            calls.append(ToolCall(str(block.id), str(block.name), dict(block.input or {})))
    u = getattr(msg, "usage", None)
    return Reply(content="".join(text), tool_calls=tuple(calls),
                 input_tokens=int(getattr(u, "input_tokens", 0) or 0) + int(getattr(u, "cache_read_input_tokens", 0) or 0),
                 cached_tokens=int(getattr(u, "cache_read_input_tokens", 0) or 0),
                 output_tokens=int(getattr(u, "output_tokens", 0) or 0),
                 raw=msg.model_dump() if hasattr(msg, "model_dump") else {})


class Anthropic:
    """``Anthropic("claude-sonnet-5-5", api_key=…)``. Any keyword the SDK's ``AsyncAnthropic`` takes may be passed
    through ``client_kwargs`` (``http_client`` for a fake transport, ``base_url`` for a gateway)."""

    def __init__(self, model: str, *, api_key: str | None = None, max_tokens: int = 4096, thinking_budget: int = 0,
                 client: Any = None, **client_kwargs: Any):
        try:
            from anthropic import AsyncAnthropic
        except ImportError as e:  # pragma: no cover
            raise ImportError('the Anthropic adapter needs the SDK: pip install "hypswarm[anthropic]"') from e
        self.name = model
        self.max_tokens = max_tokens
        self.thinking_budget = thinking_budget
        self._client = client or AsyncAnthropic(api_key=api_key, **client_kwargs)

    async def complete(self, messages: Sequence[Message], tools: Sequence[Tool], *, temperature: float | None = None,
                       unit: str = "") -> Reply:
        system, msgs = to_anthropic(messages)
        kw: dict[str, Any] = {"model": self.name, "max_tokens": self.max_tokens, "messages": msgs,
                              "extra_headers": {"X-Hypswarm-Unit": unit[:80]} if unit else None}
        if system:
            kw["system"] = system
        if tools:
            kw["tools"] = tools_to_anthropic(tools)
        # the Messages API no longer takes a sampling temperature; a seat's temperature is not a knob here
        if self.thinking_budget:
            kw["thinking"] = {"type": "enabled", "budget_tokens": self.thinking_budget}
        msg = await self._client.messages.create(**{k: v for k, v in kw.items() if v is not None})
        return from_anthropic(msg)
