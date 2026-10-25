"""
Amazon Bedrock's Converse API as a seat's model (the ``[bedrock]`` extra). One adapter for every model Bedrock
serves with tool use — Anthropic Claude, Amazon Nova, Meta Llama, Mistral, Cohere, DeepSeek — because Converse
gives them one shape: ``system`` as its own list, tool calls as ``toolUse`` blocks, tool results as ``toolResult``
blocks grouped into one user turn, usage with cache reads. boto3 is synchronous, so each call runs in a thread.

    from hypswarm.providers.bedrock import Bedrock
    model = Bedrock("anthropic.claude-sonnet-4-5-20250929-v1:0", region="us-east-1")

Credentials come from the usual AWS chain (environment, profile, instance role); nothing here reads a key.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any

from ..messages import Message, Reply, Tool, ToolCall


def to_converse(messages: Sequence[Message]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(system blocks, messages) in Converse's shape. Roles must alternate, so consecutive same-role turns are
    merged and consecutive tool results become one user turn. Bedrock refuses an empty text block, so an
    assistant turn with nothing to say carries a placeholder."""
    system: list[dict[str, Any]] = []
    out: list[dict[str, Any]] = []

    def push(role: str, blocks: list[dict[str, Any]]) -> None:
        if out and out[-1]["role"] == role:
            out[-1]["content"].extend(blocks)
        else:
            out.append({"role": role, "content": blocks})
    for m in messages:
        if m.role == "system":
            if m.content.strip():
                system.append({"text": m.content})
        elif m.role == "user":
            push("user", [{"text": m.content or "(continue)"}])
        elif m.role == "assistant":
            blocks: list[dict[str, Any]] = []
            if m.content.strip():
                blocks.append({"text": m.content})
            blocks += [{"toolUse": {"toolUseId": t.id, "name": t.name, "input": t.args}} for t in m.tool_calls]
            push("assistant", blocks or [{"text": "(no content)"}])
        elif m.role == "tool":
            push("user", [{"toolResult": {"toolUseId": m.tool_call_id, "content": [{"text": m.content or "(empty)"}]}}])
    return system, out


def tools_to_converse(tools: Sequence[Tool]) -> dict[str, Any]:
    return {"tools": [{"toolSpec": {"name": t.name, "description": t.description[:1024] or t.name,
                                    "inputSchema": {"json": t.parameters}}} for t in tools]}


def from_converse(data: dict[str, Any]) -> Reply:
    text: list[str] = []
    calls: list[ToolCall] = []
    for block in ((data.get("output") or {}).get("message") or {}).get("content") or []:
        if "text" in block:
            text.append(str(block["text"]))
        elif "toolUse" in block:
            tu = block["toolUse"]
            calls.append(ToolCall(str(tu.get("toolUseId") or f"call_{len(calls)}"), str(tu.get("name") or ""),
                                  dict(tu.get("input") or {})))
    u = data.get("usage") or {}
    cached = int(u.get("cacheReadInputTokens") or 0)
    return Reply(content="".join(text), tool_calls=tuple(calls),
                 input_tokens=int(u.get("inputTokens") or 0) + cached, cached_tokens=cached,
                 output_tokens=int(u.get("outputTokens") or 0), raw={k: v for k, v in data.items() if k != "ResponseMetadata"})


class Bedrock:
    """``Bedrock(model_id, region=…)``. ``client`` takes a ready ``bedrock-runtime`` client (or a fake with a
    ``converse`` method); ``client_kwargs`` go to ``boto3.client``. ``max_tokens`` caps each reply."""

    def __init__(self, model: str, *, region: str = "", max_tokens: int = 4096, client: Any = None,
                 extra_fields: dict[str, Any] | None = None, **client_kwargs: Any):
        self.name = model
        self.max_tokens = max_tokens
        self.extra_fields = extra_fields or {}          # additionalModelRequestFields, e.g. thinking for Claude
        if client is None:
            try:
                import boto3
            except ImportError as e:  # pragma: no cover
                raise ImportError('the Bedrock adapter needs boto3: pip install "hypswarm[bedrock]"') from e
            if region:
                client_kwargs["region_name"] = region
            client = boto3.client("bedrock-runtime", **client_kwargs)
        self._client = client

    def _call(self, kw: dict[str, Any]) -> dict[str, Any]:
        return dict(self._client.converse(**kw))

    async def complete(self, messages: Sequence[Message], tools: Sequence[Tool], *, temperature: float | None = None,
                       unit: str = "") -> Reply:
        system, msgs = to_converse(messages)
        kw: dict[str, Any] = {"modelId": self.name, "messages": msgs,
                              "inferenceConfig": {"maxTokens": self.max_tokens}}
        if system:
            kw["system"] = system
        if tools:
            kw["toolConfig"] = tools_to_converse(tools)
        if temperature is not None:
            kw["inferenceConfig"]["temperature"] = temperature
        if self.extra_fields:
            kw["additionalModelRequestFields"] = self.extra_fields
        data = await asyncio.to_thread(self._call, kw)
        return from_converse(data)
