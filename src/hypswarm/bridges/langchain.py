"""
A LangChain / LangGraph agent as a seat.

    from langgraph.prebuilt import create_react_agent
    from hypswarm.bridges.langchain import langchain_agent
    Seat("analyst", "worker", agent=langchain_agent(lambda tools: create_react_agent(llm, tools)))

The factory gets the record's tools as LangChain ``StructuredTool``s and returns any Runnable that takes
``{"messages": [...]}`` and returns ``{"messages": [...]}`` (a LangGraph prebuilt agent, your own graph, an
AgentExecutor wrapped to that shape). The bridge invokes it with the seat's system prompt and the order, caps the
recursion at the calls left in the run, and reads usage from every ``AIMessage``'s ``usage_metadata``.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Sequence
from typing import Any

from ..agents import AgentFn, AgentOrder, AgentOutcome, async_fn, pydantic_args_model, sync_fn
from ..messages import Tool


def to_structured_tools(tools: Sequence[Tool]) -> list[Any]:
    from langchain_core.tools import StructuredTool
    out = []
    for t in tools:
        schema = pydantic_args_model(t)
        if inspect.iscoroutinefunction(t.fn):
            out.append(StructuredTool.from_function(func=sync_fn(t), coroutine=async_fn(t), name=t.name,
                                                    description=t.description, args_schema=schema))
        else:
            out.append(StructuredTool.from_function(func=sync_fn(t), coroutine=async_fn(t), name=t.name,
                                                    description=t.description, args_schema=schema))
    return out


def langchain_agent(factory: Callable[[list[Any]], Any], *, recursion_per_call: int = 2) -> AgentFn:
    """``factory(structured_tools) -> Runnable``. ``recursion_per_call``: LangGraph counts a model step and a tool
    step as two; the recursion limit is ``calls_left × recursion_per_call``."""
    async def agent(order: AgentOrder) -> AgentOutcome:
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
        runnable = factory(to_structured_tools(order.tools))
        config: dict[str, Any] = {"recursion_limit": max(4, order.calls_left * recursion_per_call),
                                  "tags": [f"hypswarm:{order.code}", f"seat:{order.seat.name}"]}
        state = {"messages": [SystemMessage(content=order.system), HumanMessage(content=order.text)]}
        result = await runnable.ainvoke(state, config=config)
        msgs = result.get("messages", []) if isinstance(result, dict) else []
        out = AgentOutcome(raw=result)
        for m in msgs:
            if isinstance(m, AIMessage):
                out.calls += 1
                u: dict[str, Any] = dict(m.usage_metadata or {})
                out.input_tokens += int(u.get("input_tokens") or 0)
                out.cached_tokens += int((u.get("input_token_details") or {}).get("cache_read") or 0)
                out.output_tokens += int(u.get("output_tokens") or 0)
                for tc in m.tool_calls or []:
                    out.log.append({"tool": tc.get("name"), "args": tc.get("args")})
        last = next((m for m in reversed(msgs) if isinstance(m, AIMessage) and str(m.content).strip()), None)
        if last is not None:
            c = last.content
            out.note = (c if isinstance(c, str) else " ".join(p.get("text", "") for p in c if isinstance(p, dict)))[:700]
        return out
    agent.__name__ = "langchain_agent"
    return agent


__all__ = ["langchain_agent", "to_structured_tools"]
