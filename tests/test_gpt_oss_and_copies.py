"""Two fixes from running a swarm on gpt-oss-20b (llama.cpp, BC-250, 2026-11-04).

1. gpt-oss (harmony) must see its own reasoning from earlier steps of a tool-calling turn. The OpenAI-compatible
   provider dropped ``reasoning_content`` when it sent the conversation back; the model then wrote broken channel
   headers (llama.cpp HTTP 500) or degenerate text in 5-7 % of calls. Replaying captured requests: 7-17 of 24 failed
   under every server and sampling setting, 0 of 24 with the reasoning sent back.
2. A question stays "answered" until every answer to it is checked. A seat that registered a number with no code
   could never put code behind it (a new result was refused as a restatement), so it filed copies of its claim until
   the budget ran out, and the unchecked copies held the question open.
"""
from __future__ import annotations

import asyncio
import json

import httpx

from hypswarm import Budget, Seat
from hypswarm.budget import Meter
from hypswarm.messages import Message, ToolCall
from hypswarm.providers.openai_compat import OpenAICompatible
from hypswarm.record import LocalRecord
from hypswarm.reproduce import reproduce_result
from hypswarm.tools import worker_tools

from .test_reproduce import exec_reproducer

# ── 1. reasoning sent back ───────────────────────────────────────────────────


def _provider(model: str, sent: list[dict], **kw) -> OpenAICompatible:
    def handler(req: httpx.Request) -> httpx.Response:
        sent.append(json.loads(req.content))
        return httpx.Response(200, json={"choices": [{"message": {
            "role": "assistant", "content": "", "reasoning_content": "count the 1s in column a",
            "tool_calls": [{"id": "c1", "type": "function",
                            "function": {"name": "python", "arguments": "{\"code\": \"print(1)\"}"}}]}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5}})
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return OpenAICompatible(model, base_url="http://box/v1", api_key="x", client=client, **kw)


def _turn(p: OpenAICompatible) -> list[dict]:
    """One reply, then a second request that carries it back: what the second request sent."""
    async def go():
        msgs = [Message("system", "s"), Message("user", "u")]
        reply = await p.complete(msgs, [])
        assert reply.reasoning == "count the 1s in column a"
        msgs += [reply.as_message(), Message("tool", "1", tool_call_id="c1")]
        await p.complete(msgs, [])
        await p.aclose()
    asyncio.run(go())
    return []


def test_gpt_oss_gets_its_reasoning_back_on_tool_calls():
    sent: list[dict] = []
    _turn(_provider("gpt-oss-20b", sent))
    back = sent[1]["messages"][2]
    assert back["role"] == "assistant" and back["tool_calls"]
    assert back["reasoning_content"] == "count the 1s in column a"


def test_other_models_dont_unless_asked():
    sent: list[dict] = []
    _turn(_provider("deepseek-ai/DeepSeek-V3.2", sent))
    assert "reasoning_content" not in sent[1]["messages"][2]
    sent2: list[dict] = []
    _turn(_provider("some-model", sent2, return_reasoning=True))
    assert sent2[1]["messages"][2]["reasoning_content"] == "count the 1s in column a"
    sent3: list[dict] = []
    _turn(_provider("gpt-oss-20b", sent3, return_reasoning=False))
    assert "reasoning_content" not in sent3[1]["messages"][2]


def test_a_final_answers_reasoning_is_not_carried():
    m = Message("assistant", "the answer is 0.814", reasoning="thinking")
    assert "reasoning_content" not in m.to_openai(reasoning=True)
    t = Message("assistant", "", (ToolCall("c1", "python", {"code": "1"}),), reasoning="thinking")
    assert t.to_openai(reasoning=True)["reasoning_content"] == "thinking"
    assert "reasoning_content" not in t.to_openai()


# ── 2. code behind a bare result; no copies of an answer ─────────────────────

CODE = "k, n = 814, 1000\nprint('acc_a', k, 'of', n, '=', k / n)\n"
VALUES = {"acc_a": {"k": 814, "n": 1000}}


def _setup():
    seats = [Seat("analyst", "worker"), Seat("critic", "reviewer")]
    r = LocalRecord(None, seats)
    inv = r.start("Does A beat B", "Score A and B on the same items.", [("Q1", "What is A's accuracy?")])
    order = r.issue_work(author="harness", inv=inv, target=r.resolve("Q1", inv), assignee="analyst",
                         objective="Find A's accuracy on items.csv.")["order"]
    tools = {t.name: t.fn for t in worker_tools(r, seats[0], inv, order, Meter(Budget(max_calls=40)))}
    return r, inv, tools


def _producers(r, inv, code):
    res = r.get(r.resolve(code, inv))
    return [r.get(e["src"]) for e in res["in"] if e["rel"] == "produced"]


def test_code_registered_after_a_bare_result_becomes_its_code():
    r, inv, t = _setup()
    first = t["register_run"](name="count", result_summary="Counted A's correct items.", values=VALUES)
    assert first.startswith("run ") and "RS1" in first
    assert not any((p["body"].get("config") or {}).get("source") for p in _producers(r, inv, "RS1"))
    again = t["register_run"](name="count with code", result_summary="Counted A's correct items.", values=VALUES,
                              code=CODE)
    assert again.startswith("run ") and "result RS1" in again and "is now its code" in again, again
    assert any((p["body"].get("config") or {}).get("source") == CODE for p in _producers(r, inv, "RS1"))
    # the instrument re-runs that code against RS1's own values
    out = asyncio.run(reproduce_result(r, inv, r.resolve("RS1", inv), exec_reproducer))
    assert out and out["ok"], out


def test_a_real_restatement_is_still_refused():
    r, inv, t = _setup()
    assert t["register_run"](name="count", result_summary="Counted A's correct items.", values=VALUES, code=CODE).startswith("run ")
    again = t["register_run"](name="count again", result_summary="Counted A's correct items.", values=VALUES, code=CODE)
    assert again.startswith("refused") and "RESULT_RESTATES" in again


def test_a_copy_of_an_answer_is_refused_and_a_different_one_is_not():
    r, inv, t = _setup()
    first = t["register_run"](name="count", result_summary="Counted A's correct items in items.csv.", values=VALUES,
                              code=CODE, claim="A is right on 814 of 1000 items.", answers="Q1",
                              scope="The 1000 items in items.csv.")
    assert "→ claim CL1" in first, first
    copy = t["graph_add"]("claim", {"statement": "A gets 814 of the 1000 items right.",
                                    "scope": "The 1000 items in items.csv."},
                          [{"rel": "answers", "to": "Q1"}, {"rel": "derived_from", "to": "RS1"}])
    assert copy.startswith("refused") and "CL1 already answers Q1" in copy, copy
    other = t["graph_add"]("claim", {"statement": "A gets 815 of the 1000 items right.",
                                     "scope": "The 1000 items in items.csv."},
                           [{"rel": "answers", "to": "Q1"}, {"rel": "derived_from", "to": "RS1"}])
    assert "already answers" not in other
    via_run = t["register_run"](name="recount", result_summary="Recounted.", values={"acc": {"value": 0.814}},
                                code="print('acc', 0.814)", claim="A's accuracy is 81.4 %.", answers="Q1")
    assert "already answers" not in via_run          # 0.814 is not among CL1's figures (814, 1000)
