"""A scripted model for tests: no network, deterministic, counts like a real one. A script is a function of the
conversation so far that returns the next reply — text, or a tool call."""

from __future__ import annotations

from typing import Any, Callable, Sequence

from ..messages import Message, Reply, Tool, ToolCall

Script = Callable[[Sequence[Message], Sequence[Tool]], "str | tuple[str, dict[str, Any]] | None"]


class StubModel:
    def __init__(self, script: Script, name: str = "stub"):
        self.name = name
        self.script = script
        self.calls = 0

    async def complete(self, messages: Sequence[Message], tools: Sequence[Tool], *, temperature: float | None = None,
                       unit: str = "") -> Reply:
        self.calls += 1
        out = self.script(messages, tools)
        usage = {"input_tokens": 100 + 10 * len(messages), "cached_tokens": 50, "output_tokens": 20}
        if out is None or isinstance(out, str):
            return Reply(content=out or "done", **usage)
        name, args = out
        return Reply(content="", tool_calls=(ToolCall(f"c{self.calls}", name, args),), **usage)


def tool_outputs(messages: Sequence[Message]) -> list[str]:
    return [m.content for m in messages if m.role == "tool"]


def calls_made(messages: Sequence[Message]) -> list[str]:
    return [t.name for m in messages if m.role == "assistant" for t in m.tool_calls]
