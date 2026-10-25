"""
Any LangChain chat model as a seat's model (the ``[langchain]`` extra): ``ChatOpenAI``, ``ChatAnthropic``,
``ChatBedrockConverse``, ``ChatOllama``, ``ChatGoogleGenerativeAI`` — anything that is a ``BaseChatModel`` with
``bind_tools``. The seat's tools are bound in OpenAI's function shape; the reply's ``tool_calls`` and
``usage_metadata`` are read back. This is the model-level bridge: the seat still runs hypswarm's own loop. To hand
a seat to a whole LangChain / LangGraph *agent* instead, see ``hypswarm.bridges.langchain``.

    from langchain_openai import ChatOpenAI
    from hypswarm.providers.langchain import LangChainModel
    model = LangChainModel(ChatOpenAI(model="gpt-4.1-mini"))
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ..messages import Message, Reply, Tool, ToolCall


def to_langchain(messages: Sequence[Message]) -> list[Any]:
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
    out: list[Any] = []
    for m in messages:
        if m.role == "system":
            out.append(SystemMessage(content=m.content))
        elif m.role == "user":
            out.append(HumanMessage(content=m.content))
        elif m.role == "assistant":
            out.append(AIMessage(content=m.content, tool_calls=[{"id": t.id, "name": t.name, "args": t.args, "type": "tool_call"}
                                                                 for t in m.tool_calls]))
        elif m.role == "tool":
            out.append(ToolMessage(content=m.content, tool_call_id=m.tool_call_id))
    return out


def from_langchain(msg: Any) -> Reply:
    content = getattr(msg, "content", "")
    if isinstance(content, list):
        content = "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in content)
    calls = tuple(ToolCall(str(tc.get("id") or f"call_{i}"), str(tc.get("name") or ""), dict(tc.get("args") or {}))
                  for i, tc in enumerate(getattr(msg, "tool_calls", None) or []))
    u = getattr(msg, "usage_metadata", None) or {}
    details = u.get("input_token_details") or {}
    return Reply(content=str(content or ""), tool_calls=calls, input_tokens=int(u.get("input_tokens") or 0),
                 cached_tokens=int(details.get("cache_read") or 0), output_tokens=int(u.get("output_tokens") or 0),
                 raw=msg.model_dump() if hasattr(msg, "model_dump") else {})


class LangChainModel:
    """``LangChainModel(chat_model, name="")``: ``name`` labels the seat's calls (defaults to the model's own
    ``model_name`` / ``model`` attribute). Temperature is whatever the chat model was built with — a seat's
    ``temperature`` is applied only when the model accepts ``bind(temperature=…)``."""

    def __init__(self, chat_model: Any, name: str = ""):
        self.chat_model = chat_model
        self.name = name or str(getattr(chat_model, "model_name", "") or getattr(chat_model, "model", "")
                                or type(chat_model).__name__)
        self._bound: dict[tuple[str, ...], Any] = {}

    def _with_tools(self, tools: Sequence[Tool]) -> Any:
        key = tuple(t.name for t in tools)
        if key not in self._bound:
            self._bound[key] = self.chat_model.bind_tools([t.to_openai() for t in tools]) if tools else self.chat_model
        return self._bound[key]

    async def complete(self, messages: Sequence[Message], tools: Sequence[Tool], *, temperature: float | None = None,
                       unit: str = "") -> Reply:
        model = self._with_tools(tools)
        if temperature is not None and hasattr(model, "bind"):
            try:
                model = model.bind(temperature=temperature)
            except Exception:  # noqa: BLE001 — a model that takes no temperature keeps its own
                model = self._with_tools(tools)
        msg = await model.ainvoke(to_langchain(messages), config={"tags": [f"hypswarm:{unit}"]} if unit else None)
        return from_langchain(msg)
