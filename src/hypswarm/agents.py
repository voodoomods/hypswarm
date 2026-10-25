"""
Agent seats: a seat held by a whole agent from another framework (LangChain / LangGraph, PydanticAI, CrewAI, or
anything you write), run in-process. hypswarm hands it the order and the record's tools; the agent runs its own
loop with its own model; the record judges whether the order is done exactly as for a native seat, refuses the
same overclaims, and the run's budget counts the calls the agent reports.

    Seat("quant", "worker", agent=langchain_agent(lambda tools: create_react_agent(llm, tools)))

An agent is ``async (AgentOrder) -> AgentOutcome | str | None``. It gets the order text, the system prompt a native
seat would get, the tools as hypswarm ``Tool`` objects (name, description, JSON-schema parameters, fn) for the
bridge to translate, and how many calls are left. It returns what it used — calls and tokens — and a note; if it
did not call ``return_work`` itself, hypswarm returns the order with that note. The framework-specific bridges in
``hypswarm.bridges`` do the translation and the usage accounting.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from .messages import Tool


@dataclass
class AgentOrder:
    seat: Any                       # the Seat
    code: str                       # order code (T3)
    order: str                      # order node id
    text: str                       # the work order, as a native seat reads it
    system: str                     # the system prompt a native seat would get (identity, rules, mission, notices)
    tools: list[Tool]               # record tools + the host's data tools the seat may use
    calls_left: int                 # the run's remaining call budget: cap your loop at or under this
    record: Any = None
    inv: str = ""

    def returned(self) -> bool:
        """Whether the agent already called return_work through the tools."""
        for t in self.tools:
            st = t.fn.__dict__.get("_state")
            if st is not None:
                return bool(st.get("returned"))
        return False


@dataclass
class AgentOutcome:
    note: str = ""                  # ≤ 120 words: what was done, what could not be — used to return the order
    calls: int = 0                  # model calls the agent made
    input_tokens: int = 0
    cached_tokens: int = 0
    output_tokens: int = 0
    log: list[dict[str, Any]] = field(default_factory=list)   # tool calls the bridge saw, if it saw them
    raw: Any = None


AgentFn = Callable[[AgentOrder], "Awaitable[AgentOutcome | str | None] | AgentOutcome | str | None"]


async def call_agent(agent: AgentFn, order: AgentOrder) -> AgentOutcome:
    out = agent(order)
    if inspect.isawaitable(out):
        out = await out
    if out is None:
        return AgentOutcome()
    if isinstance(out, str):
        return AgentOutcome(note=out)
    return out


def tool_signature(tool: Tool) -> inspect.Signature:
    return inspect.signature(tool.fn)


def py_type(schema: dict[str, Any]) -> Any:
    """A Python annotation for a JSON-schema fragment — enough for a framework to build its own schema."""
    t = schema.get("type")
    return {"string": str, "integer": int, "number": float, "boolean": bool, "object": dict, "array": list}.get(
        str(t), Any)


def pydantic_args_model(tool: Tool, model_name: str = "") -> Any:
    """A pydantic model of the tool's parameters (type + default from the function's own signature), for
    frameworks that take ``args_schema``."""
    from pydantic import Field, create_model
    sig = tool_signature(tool)
    props = tool.parameters.get("properties") or {}
    fields: dict[str, Any] = {}
    for name, schema in props.items():
        p = sig.parameters.get(name)
        default = ... if p is None or p.default is inspect.Parameter.empty else p.default
        fields[name] = (py_type(schema) if default is ... else py_type(schema) | None,
                        Field(default, description=schema.get("description", "")))
    return create_model(model_name or f"{tool.name}_args", **fields)


def sync_fn(tool: Tool) -> Callable[..., str]:
    """The tool as a plain synchronous function returning text (an async fn runs on a fresh loop in a thread, so it
    is safe to call from inside a framework's own event loop)."""
    import asyncio
    import concurrent.futures

    def run(**kw: Any) -> str:
        if inspect.iscoroutinefunction(tool.fn):
            with concurrent.futures.ThreadPoolExecutor(1) as ex:
                return ex.submit(asyncio.run, tool.call(kw)).result()
        out = tool.fn(**kw)
        if inspect.isawaitable(out):
            with concurrent.futures.ThreadPoolExecutor(1) as ex:
                return str(ex.submit(asyncio.run, _await(out)).result())
        return out if isinstance(out, str) else _json(out)
    run.__name__ = tool.name
    run.__doc__ = tool.description
    return run


async def _await(x: Awaitable[Any]) -> Any:
    return await x


def _json(x: Any) -> str:
    import json
    return json.dumps(x, default=str)


def async_fn(tool: Tool) -> Callable[..., Awaitable[str]]:
    async def run(**kw: Any) -> str:
        return await tool.call(kw)
    run.__name__ = tool.name
    run.__doc__ = tool.description
    return run


def usage_from(obj: Any) -> tuple[int, int, int, int]:
    """(calls, input, cached, output) from the usage objects the frameworks return, whatever their field names."""
    def g(*names: str) -> int:
        for n in names:
            v = getattr(obj, n, None)
            if v is None and isinstance(obj, dict):
                v = obj.get(n)
            if isinstance(v, (int, float)):
                return int(v)
        return 0
    details = getattr(obj, "details", None) or (obj.get("details") if isinstance(obj, dict) else None) or {}
    cached = g("cache_read_tokens", "cached_tokens", "cached_prompt_tokens") or int(
        (details.get("cache_read_input_tokens") or details.get("cached_tokens") or 0) if isinstance(details, dict) else 0)
    return (g("requests", "successful_requests", "calls"), g("input_tokens", "request_tokens", "prompt_tokens"),
            cached, g("output_tokens", "response_tokens", "completion_tokens"))


def describe_tools(tools: Sequence[Tool]) -> str:
    return "\n".join(f"- {t.name}: {t.description.splitlines()[0][:120]}" for t in tools)


__all__ = ["AgentFn", "AgentOrder", "AgentOutcome", "async_fn", "call_agent", "describe_tools", "pydantic_args_model",
           "sync_fn", "usage_from"]
