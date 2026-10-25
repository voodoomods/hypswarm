"""The Bedrock Converse adapter against a fake client: request shape (system list, alternating roles, toolSpec,
toolResult grouping, no empty text block) and the reply read back (toolUse → ToolCall, cache reads in usage)."""
import asyncio

from hypswarm.messages import Message, Tool, ToolCall
from hypswarm.providers.bedrock import Bedrock, from_converse, to_converse, tools_to_converse


class FakeClient:
    def __init__(self, reply):
        self.reply = reply
        self.calls: list = []

    def converse(self, **kw):
        self.calls.append(kw)
        return self.reply


def _tool():
    def register_run(name: str, values: dict | None = None) -> str:
        """Record a run."""
        return "ok"
    return Tool.from_function(register_run)


def test_request_shape():
    msgs = [Message("system", "You are quant."), Message("user", "WORK ORDER T1"),
            Message("assistant", "", tool_calls=(ToolCall("tu1", "register_run", {"name": "x"}),)),
            Message("tool", "run RUN1", tool_call_id="tu1"), Message("tool", "second", tool_call_id="tu2"),
            Message("user", "continue")]
    system, out = to_converse(msgs)
    assert system == [{"text": "You are quant."}]
    assert [m["role"] for m in out] == ["user", "assistant", "user"]           # tool results + user merged
    assert out[1]["content"] == [{"text": "(no content)"}, {"toolUse": {"toolUseId": "tu1", "name": "register_run", "input": {"name": "x"}}}][1:] \
        or out[1]["content"][0]["toolUse"]["toolUseId"] == "tu1"
    assert out[2]["content"][0]["toolResult"]["toolUseId"] == "tu1" and out[2]["content"][2] == {"text": "continue"}
    tc = tools_to_converse([_tool()])
    assert tc["tools"][0]["toolSpec"]["name"] == "register_run"
    assert tc["tools"][0]["toolSpec"]["inputSchema"]["json"]["required"] == ["name"]


def test_reply_and_usage():
    reply = {"output": {"message": {"role": "assistant", "content": [
                 {"text": "Counting."}, {"toolUse": {"toolUseId": "tu9", "name": "register_run", "input": {"name": "c"}}}]}},
             "usage": {"inputTokens": 900, "outputTokens": 40, "cacheReadInputTokens": 600}, "stopReason": "tool_use",
             "ResponseMetadata": {"HTTPStatusCode": 200}}
    r = from_converse(reply)
    assert r.content == "Counting." and r.tool_calls == (ToolCall("tu9", "register_run", {"name": "c"}),)
    assert (r.input_tokens, r.cached_tokens, r.output_tokens) == (1500, 600, 40) and "ResponseMetadata" not in r.raw


def test_adapter_calls_converse_with_tools_and_temperature():
    client = FakeClient({"output": {"message": {"content": [{"text": "done"}]}}, "usage": {"inputTokens": 10, "outputTokens": 2}})
    m = Bedrock("amazon.nova-pro-v1:0", client=client, max_tokens=512)
    r = asyncio.run(m.complete([Message("system", "s"), Message("user", "u")], [_tool()], temperature=0.2, unit="T1"))
    assert r.content == "done" and r.input_tokens == 10
    kw = client.calls[0]
    assert kw["modelId"] == "amazon.nova-pro-v1:0" and kw["system"] == [{"text": "s"}]
    assert kw["inferenceConfig"] == {"maxTokens": 512, "temperature": 0.2} and "toolConfig" in kw
