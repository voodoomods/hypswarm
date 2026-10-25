"""The model-facing surface: messages, tool specs built from Python functions, replies. Provider-neutral."""

from __future__ import annotations

import inspect
import json
import typing
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

_JSON = {str: "string", int: "integer", float: "number", bool: "boolean", list: "array", dict: "object"}


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    args: dict[str, Any]


@dataclass(frozen=True)
class Message:
    role: str                              # system | user | assistant | tool
    content: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str = ""

    def to_openai(self) -> dict[str, Any]:
        m: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.tool_calls:
            m["tool_calls"] = [{"id": t.id, "type": "function",
                                "function": {"name": t.name, "arguments": json.dumps(t.args)}} for t in self.tool_calls]
        if self.role == "tool":
            m["tool_call_id"] = self.tool_call_id
        return m


@dataclass(frozen=True)
class Reply:
    content: str
    tool_calls: tuple[ToolCall, ...] = ()
    input_tokens: int = 0
    cached_tokens: int = 0
    output_tokens: int = 0
    raw: dict[str, Any] = field(default_factory=dict)

    def as_message(self) -> Message:
        return Message("assistant", self.content, self.tool_calls)


def _schema(t: Any) -> dict[str, Any]:
    origin = typing.get_origin(t)
    if origin is typing.Union or str(origin) == "<class 'types.UnionType'>":
        args = [a for a in typing.get_args(t) if a is not type(None)]
        return _schema(args[0]) if len(args) == 1 else {}
    if origin in (list, tuple):
        inner = typing.get_args(t)
        return {"type": "array", "items": _schema(inner[0]) if inner else {}}
    if origin is dict:
        return {"type": "object"}
    if t in _JSON:
        return {"type": _JSON[t]}
    if t is Any or t is inspect.Parameter.empty:
        return {}
    return {"type": "string"}


@dataclass
class Tool:
    """A tool the model may call: a JSON-schema spec built from a Python function's signature and docstring."""
    name: str
    description: str
    parameters: dict[str, Any]
    fn: Callable[..., Any]

    @classmethod
    def from_function(cls, fn: Callable[..., Any], name: str = "", description: str = "") -> Tool:
        sig = inspect.signature(fn)
        hints = typing.get_type_hints(fn) if hasattr(fn, "__annotations__") else {}
        props, required = {}, []
        for p in sig.parameters.values():
            if p.name in ("self", "cls"):
                continue
            props[p.name] = _schema(hints.get(p.name, p.annotation))
            if p.default is inspect.Parameter.empty:
                required.append(p.name)
        return cls(name or fn.__name__, (description or inspect.getdoc(fn) or "").strip(),
                   {"type": "object", "properties": props, "required": required}, fn)

    def to_openai(self) -> dict[str, Any]:
        return {"type": "function", "function": {"name": self.name, "description": self.description[:1024],
                                                 "parameters": self.parameters}}

    async def call(self, args: dict[str, Any]) -> str:
        """Run the function (sync or async) and return text; errors come back as text, as in production."""
        try:
            out = self.fn(**args)
            if inspect.isawaitable(out):
                out = await out
        except TypeError as e:
            return f"error: bad arguments for {self.name}: {e}"
        except Exception as e:  # noqa: BLE001 — the model sees the error and decides
            return f"error: {type(e).__name__}: {e}"
        return out if isinstance(out, str) else json.dumps(out, default=str)


ToolFn = Callable[..., Any | Awaitable[Any]]
