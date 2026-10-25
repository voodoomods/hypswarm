"""
A PydanticAI agent as a seat.

    from pydantic_ai import Agent
    from hypswarm.bridges.pydantic_ai import pydantic_ai_agent
    Seat("researcher", "worker", agent=pydantic_ai_agent(lambda tools: Agent("openai:gpt-4.1-mini", tools=tools)))

The factory gets the record's tools as ``pydantic_ai.Tool``s (schemas inferred from the same typed signatures a
native seat's tools have) and returns an ``Agent``. The bridge runs it on the order with the seat's system prompt
as instructions, limits requests to the calls left in the run, and reads ``result.usage()``.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from ..agents import AgentFn, AgentOrder, AgentOutcome, async_fn, usage_from
from ..messages import Tool


def to_pydantic_tools(tools: Sequence[Tool]) -> list[Any]:
    from pydantic_ai import Tool as PTool
    return [PTool(async_fn(t), name=t.name, description=t.description, takes_ctx=False) for t in tools]


def pydantic_ai_agent(factory: Callable[[list[Any]], Any]) -> AgentFn:
    """``factory(pydantic_tools) -> pydantic_ai.Agent``. Build the Agent without ``system_prompt``: the seat's
    system prompt is passed per run as ``instructions`` (or prepended to the prompt on versions without it)."""
    async def agent(order: AgentOrder) -> AgentOutcome:
        from pydantic_ai import Agent
        a = factory(to_pydantic_tools(order.tools))
        if not isinstance(a, Agent):
            raise TypeError("the factory must return a pydantic_ai.Agent")
        limits = None
        try:
            from pydantic_ai.usage import UsageLimits
            limits = UsageLimits(request_limit=max(1, order.calls_left))
        except Exception:  # noqa: BLE001 — older releases: no limits object
            limits = None
        kw: dict[str, Any] = {"usage_limits": limits} if limits else {}
        try:
            res = await a.run(order.text, instructions=order.system, **kw)
        except TypeError:                                   # no per-run instructions on this version
            res = await a.run(order.system + "\n\n" + order.text, **kw)
        u = res.usage
        calls, inp, cached, outp = usage_from(u() if callable(u) else u)
        note = str(getattr(res, "output", None) or getattr(res, "data", "") or "")[:700]
        log = []
        for m in getattr(res, "all_messages", list)():
            for part in getattr(m, "parts", []) or []:
                if type(part).__name__ == "ToolCallPart":
                    log.append({"tool": getattr(part, "tool_name", ""), "args": getattr(part, "args", None)})
        return AgentOutcome(note=note, calls=calls, input_tokens=inp, cached_tokens=cached, output_tokens=outp,
                            log=log, raw=res)
    agent.__name__ = "pydantic_ai_agent"
    return agent


__all__ = ["pydantic_ai_agent", "to_pydantic_tools"]
