"""
A CrewAI agent as a seat.

    from crewai import Agent, Crew, Task
    from hypswarm.bridges.crewai import crewai_agent

    def crew(tools, order):
        a = Agent(role="Quant", goal="Answer the order from the files; write to the record.", backstory="…",
                  tools=tools, llm="openai/gpt-4.1-mini")
        return Crew(agents=[a], tasks=[Task(description=order.text, expected_output="A note of ≤120 words", agent=a)])

    Seat("quant", "worker", agent=crewai_agent(crew))

The factory gets the record's tools as CrewAI ``BaseTool``s and the order, and returns a ``Crew`` (one agent, one
task is the usual shape; more is fine — they all write as this seat). The bridge kicks it off, reads
``crew.usage_metrics`` and returns the final output as the note. CrewAI's loop is synchronous; it runs in a thread.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from ..agents import AgentFn, AgentOrder, AgentOutcome, pydantic_args_model, sync_fn, usage_from
from ..messages import Tool


def _crewai_tool(t: Tool) -> Any:
    from crewai.tools import BaseTool
    schema = pydantic_args_model(t)
    fn = sync_fn(t)

    class _T(BaseTool):  # type: ignore[misc]  # BaseTool is untyped here
        name: str = t.name
        description: str = t.description[:1024] or t.name
        args_schema: type = schema

        def _run(self, **kwargs: Any) -> str:
            return fn(**kwargs)
    _T.__name__ = f"{t.name}_tool"
    return _T()


def to_crewai_tools(tools: Sequence[Tool]) -> list[Any]:
    return [_crewai_tool(t) for t in tools]      # one closure per tool (a loop-local class would share the last fn)


def crewai_agent(factory: Callable[[list[Any], AgentOrder], Any]) -> AgentFn:
    """``factory(crewai_tools, order) -> Crew``. Put ``order.system`` into the agent's backstory or goal if you want
    the seat's identity and rules in the prompt; the order text goes into the task description."""
    async def agent(order: AgentOrder) -> AgentOutcome:
        import asyncio
        crew = factory(to_crewai_tools(order.tools), order)
        if hasattr(crew, "kickoff_async"):
            result = await crew.kickoff_async()
        else:
            result = await asyncio.to_thread(crew.kickoff)
        um = getattr(result, "token_usage", None) or getattr(crew, "usage_metrics", None)
        calls, inp, cached, outp = usage_from(um) if um is not None else (0, 0, 0, 0)
        note = str(getattr(result, "raw", None) or result or "")[:700]
        return AgentOutcome(note=note, calls=calls, input_tokens=inp, cached_tokens=cached, output_tokens=outp,
                            raw=result)
    agent.__name__ = "crewai_agent"
    return agent


__all__ = ["crewai_agent", "to_crewai_tools"]
