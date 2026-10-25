"""The Anthropic adapter on a fake transport: what it sends, what it reads back, and that a worker loop runs on
it — no network, no key, no spend."""
import asyncio
import json

import httpx
import pytest

from hypswarm.messages import Message, Tool, ToolCall
from hypswarm.providers.anthropic import to_anthropic

anthropic = pytest.importorskip("anthropic")
from hypswarm.providers.anthropic import Anthropic


def python(code: str) -> str:
    """Run python code."""
    return "ok"


def fake(script):
    """A transport that answers /v1/messages from a script of canned replies and records every request body."""
    sent = []
    try:                                                          # SDK 2.x ships its own httpx fork
        import httpx2 as hx
    except ImportError:                                           # pragma: no cover
        hx = httpx

    def handler(request):
        body = json.loads(request.content)
        sent.append(body)
        reply = script[min(len(sent) - 1, len(script) - 1)]
        return hx.Response(200, json={
            "id": "msg_1", "type": "message", "role": "assistant", "model": body["model"], "stop_reason": "end_turn",
            "stop_sequence": None, "content": reply["content"],
            "usage": {"input_tokens": 120, "output_tokens": 9, "cache_read_input_tokens": 100,
                      "cache_creation_input_tokens": 0}})
    client = anthropic.AsyncAnthropic(api_key="not-a-key", http_client=hx.AsyncClient(transport=hx.MockTransport(handler)))
    return Anthropic("claude-sonnet-5-5", client=client, max_tokens=512), sent


def test_mapping_puts_system_apart_and_groups_tool_results():
    msgs = [Message("system", "Be careful."), Message("user", "Count the rows."),
            Message("assistant", "", (ToolCall("t1", "python", {"code": "print(1)"}), ToolCall("t2", "python", {"code": "print(2)"}))),
            Message("tool", "1", tool_call_id="t1"), Message("tool", "2", tool_call_id="t2"),
            Message("assistant", "Two rows.")]
    system, out = to_anthropic(msgs)
    assert system == "Be careful."
    assert [m["role"] for m in out] == ["user", "assistant", "user", "assistant"]
    assert [b["type"] for b in out[1]["content"]] == ["tool_use", "tool_use"]
    assert [b["tool_use_id"] for b in out[2]["content"]] == ["t1", "t2"]       # both results in one user turn
    assert out[3]["content"] == [{"type": "text", "text": "Two rows."}]


def test_a_tool_call_round_trip_on_the_fake_transport():
    model, sent = fake([
        {"content": [{"type": "text", "text": "Counting."},
                     {"type": "tool_use", "id": "toolu_1", "name": "python", "input": {"code": "print(3)"}}]},
        {"content": [{"type": "text", "text": "There are 3 rows."}]},
    ])
    tools = [Tool.from_function(python)]
    msgs = [Message("system", "You are an analyst."), Message("user", "How many rows?")]
    r1 = asyncio.run(model.complete(msgs, tools, temperature=0.2, unit="T1"))
    assert r1.tool_calls == (ToolCall("toolu_1", "python", {"code": "print(3)"}),)
    assert r1.content == "Counting." and r1.input_tokens == 220 and r1.cached_tokens == 100 and r1.output_tokens == 9
    body = sent[0]
    assert body["system"] == "You are an analyst." and body["model"] == "claude-sonnet-5-5"
    assert body["tools"][0]["name"] == "python" and body["tools"][0]["input_schema"]["required"] == ["code"]
    assert "temperature" not in body and body["max_tokens"] == 512          # the API has no temperature
    msgs += [r1.as_message(), Message("tool", "3", tool_call_id="toolu_1")]
    r2 = asyncio.run(model.complete(msgs, tools))
    assert r2.content == "There are 3 rows." and not r2.tool_calls
    assert sent[1]["messages"][-1] == {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_1", "content": "3"}]}


def test_it_is_a_seat_model_like_any_other():
    from hypswarm import Budget, Seat, Task, run
    from hypswarm.providers.stub import StubModel

    from .test_alpha import lead_script, reviewer_script
    model, sent = fake([
        {"content": [{"type": "tool_use", "id": "a", "name": "register_run",
                      "input": {"name": "count", "result_summary": "A right on 812 of 1000 items.",
                                "values": {"acc_a": {"k": 812, "n": 1000}}}}]},
        {"content": [{"type": "tool_use", "id": "b", "name": "graph_add",
                      "input": {"type": "claim", "fields": {"statement": "A is right on 812 of 1000 items.", "scope": "The 1000 items."},
                                "links": [{"rel": "answers", "to": "Q1"}]}}]},
        {"content": [{"type": "tool_use", "id": "c", "name": "return_work", "input": {"note": "done"}}]},
    ])
    task = Task("Does A beat B", "Two models were scored on the same items.", [("Q1", "What is A's accuracy?")])
    seats = [Seat("analyst", "worker"), Seat("critic", "reviewer"), Seat("lead", "lead")]
    r = asyncio.run(run(task, seats, {"analyst": model, "reviewer": StubModel(reviewer_script), "lead": StubModel(lead_script)},
                        budget=Budget(max_calls=30)))
    assert r.stopped == "settled" and len(sent) == 3
    assert sent[0]["system"].startswith("You are analyst (worker).")           # the seat prompt went as system
