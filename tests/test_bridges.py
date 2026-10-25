"""The framework bridges on scripted models — no network, no spend. Each test is skipped when its framework is
not installed (pip install "hypswarm[langgraph]" / "[pydantic-ai]" / "[crewai]")."""
import asyncio
import json
from typing import ClassVar

import pytest

from hypswarm import Budget, Seat, run
from hypswarm.messages import Message, Tool
from hypswarm.providers.stub import StubModel

from .test_alpha import TASK, lead_script, reviewer_script


def run_args(order_text: str) -> dict:
    """The register_run call a worker makes for the order's target (Q1 or Q2), with the claim in the same call."""
    q = next((l.split()[1] for l in str(order_text).splitlines() if l.startswith("TARGET")), "Q1")
    if q == "Q2":
        return {"name": "compare for Q2", "result_summary": "Compared A and B on the same items.",
                "values": {"a": {"k": 812, "n": 1000}, "b": {"k": 800, "n": 1000}},
                "claim": "A is not significantly more accurate than B (812 of 1000 vs 800 of 1000).", "answers": "Q2",
                "scope": "The 1000 paired items."}
    return {"name": "count for Q1", "result_summary": "Counted the items for Q1.", "values": {"acc_a": {"k": 812, "n": 1000}},
            "claim": "A is right on 812 of 1000 items.", "answers": "Q1", "scope": "The 1000 paired items."}


def _order_text(messages) -> str:
    for m in messages:
        c = getattr(m, "content", None)
        if isinstance(c, str) and "WORK ORDER" in c:
            return c
        for part in getattr(m, "parts", []) or []:
            pc = getattr(part, "content", None)
            if isinstance(pc, str) and "WORK ORDER" in pc:
                return pc
    return ""
def SEATS(agent):
    return [Seat("analyst", "worker", agent=agent), Seat("critic", "reviewer"), Seat("lead", "lead")]


def MODELS():
    return {"reviewer": StubModel(reviewer_script), "lead": StubModel(lead_script)}


def _settled(r):
    assert r.stopped == "settled" and r.report_accepted, r.scheduler.events
    w = next(w for w in r.scheduler.workers if w.seat == "analyst")
    assert w.returned and not w.returned_by_record and w.calls >= 2
    q1 = next(q for q in r.board if q["code"] == "Q1")
    assert q1["status"] == "settled"
    return w


# ── the LangChain model adapter ──────────────────────────────────────────────
def test_langchain_model_adapter():
    pytest.importorskip("langchain_core")
    from langchain_core.language_models import BaseChatModel
    from langchain_core.messages import AIMessage
    from langchain_core.outputs import ChatGeneration, ChatResult

    from hypswarm.providers.langchain import LangChainModel

    class FakeChat(BaseChatModel):
        bound: ClassVar[list] = []

        @property
        def _llm_type(self):
            return "fake"

        def bind_tools(self, tools, **kw):
            type(self).bound = list(tools)
            return self

        def _generate(self, messages, stop=None, run_manager=None, **kw):
            assert messages[0].type == "system" and messages[-1].type == "tool"
            msg = AIMessage(content="", tool_calls=[{"id": "c1", "name": "register_run", "args": {"name": "x"}, "type": "tool_call"}],
                            usage_metadata={"input_tokens": 50, "output_tokens": 5, "total_tokens": 55, "input_token_details": {"cache_read": 20}})
            return ChatResult(generations=[ChatGeneration(message=msg)])

    def register_run(name: str) -> str:
        """r"""
        return "ok"
    m = LangChainModel(FakeChat(), name="fake")
    r = asyncio.run(m.complete([Message("system", "s"), Message("assistant", "", tool_calls=()), Message("tool", "t", tool_call_id="c0")],
                               [Tool.from_function(register_run)], unit="T1"))
    assert r.tool_calls[0].name == "register_run" and r.tool_calls[0].args == {"name": "x"}
    assert (r.input_tokens, r.cached_tokens, r.output_tokens) == (50, 20, 5)
    assert FakeChat.bound[0]["function"]["name"] == "register_run"


# ── LangGraph agent as a seat ────────────────────────────────────────────────
def test_langgraph_agent_holds_a_seat():
    pytest.importorskip("langgraph")
    from langchain_core.language_models import BaseChatModel
    from langchain_core.messages import AIMessage, ToolMessage
    from langchain_core.outputs import ChatGeneration, ChatResult

    from hypswarm.bridges.langchain import langchain_agent
    try:
        from langgraph.prebuilt import create_react_agent as make
    except Exception:  # noqa: BLE001 — langgraph absent or blocked: the smallest tool loop that is a Runnable
        from langchain_core.runnables import RunnableLambda

        def make(model, tools):
            by = {t.name: t for t in tools}

            async def loop(state):
                msgs = list(state["messages"])
                for _ in range(10):
                    ai = await model.bind_tools(tools).ainvoke(msgs)
                    msgs.append(ai)
                    if not ai.tool_calls:
                        break
                    for tc in ai.tool_calls:
                        out = await by[tc["name"]].ainvoke(tc["args"])
                        msgs.append(ToolMessage(content=str(out), tool_call_id=tc["id"]))
                return {"messages": msgs}
            return RunnableLambda(loop)

    class Scripted(BaseChatModel):
        @property
        def _llm_type(self):
            return "scripted"

        def bind_tools(self, tools, **kw):
            return self

        def _generate(self, messages, stop=None, run_manager=None, **kw):
            tool_msgs = [m for m in messages if isinstance(m, ToolMessage)]
            done = [tc["name"] for m in messages if isinstance(m, AIMessage) for tc in m.tool_calls]
            if "register_run" not in done:
                msg = AIMessage(content="", tool_calls=[{"id": "c1", "name": "register_run", "args": run_args(_order_text(messages)), "type": "tool_call"}],
                                usage_metadata={"input_tokens": 100, "output_tokens": 10, "total_tokens": 110})
            elif any("return_work now" in str(t.content) for t in tool_msgs) and "return_work" not in done:
                msg = AIMessage(content="", tool_calls=[{"id": "c2", "name": "return_work", "args": {"note": "answered"}, "type": "tool_call"}],
                                usage_metadata={"input_tokens": 120, "output_tokens": 8, "total_tokens": 128})
            else:
                msg = AIMessage(content="Registered the count and returned the order.",
                                usage_metadata={"input_tokens": 130, "output_tokens": 12, "total_tokens": 142})
            return ChatResult(generations=[ChatGeneration(message=msg)])

    agent = langchain_agent(lambda tools: make(Scripted(), tools))
    r = asyncio.run(run(TASK, SEATS(agent), MODELS(), record=None, budget=Budget(max_calls=40)))
    w = _settled(r)
    assert w.calls == 3 and [x["tool"] for x in w.tool_log[:2]] == ["register_run", "return_work"]
    assert r.usage["input_tokens"] >= 350


# ── PydanticAI agent as a seat ───────────────────────────────────────────────
def test_pydantic_ai_agent_holds_a_seat():
    pytest.importorskip("pydantic_ai")
    from pydantic_ai import Agent
    from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart, ToolReturnPart
    from pydantic_ai.models.function import FunctionModel

    from hypswarm.bridges.pydantic_ai import pydantic_ai_agent

    def script(messages, info):
        done = [p.tool_name for m in messages for p in getattr(m, "parts", []) if isinstance(p, ToolCallPart)]
        outs = [str(p.content) for m in messages for p in getattr(m, "parts", []) if isinstance(p, ToolReturnPart)]
        if "register_run" not in done:
            return ModelResponse(parts=[ToolCallPart(tool_name="register_run", args=run_args(_order_text(messages)))])
        if any("return_work now" in o for o in outs) and "return_work" not in done:
            return ModelResponse(parts=[ToolCallPart(tool_name="return_work", args={"note": "answered"})])
        return ModelResponse(parts=[TextPart(content="Registered and returned.")])

    agent = pydantic_ai_agent(lambda tools: Agent(FunctionModel(script), tools=tools))
    r = asyncio.run(run(TASK, SEATS(agent), MODELS(), record=None, budget=Budget(max_calls=40)))
    w = _settled(r)
    assert w.calls == 3 and [x["tool"] for x in w.tool_log[:2]] == ["register_run", "return_work"]


# ── CrewAI agent as a seat ───────────────────────────────────────────────────
def test_crewai_agent_holds_a_seat():
    pytest.importorskip("crewai")
    from crewai import Agent, Crew, Task
    from crewai.llm import BaseLLM

    from hypswarm.bridges.crewai import crewai_agent

    class ScriptedLLM(BaseLLM):
        """Answers CrewAI's native tool-calling loop: a list of tool calls until the record says the order is done,
        then text. The executor runs the tools itself and feeds their output back as messages."""
        def __init__(self):
            super().__init__(model="scripted")
            self.n = 0

        def supports_function_calling(self):
            return True

        @staticmethod
        def _call(name, args):
            return {"id": f"c-{name}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}

        def call(self, messages, tools=None, callbacks=None, available_functions=None, from_task=None, from_agent=None,
                 response_model=None):
            self.n += 1
            self._track_token_usage_internal({"prompt_tokens": 200, "completion_tokens": 20, "total_tokens": 220})
            msgs = messages if isinstance(messages, list) else [{"role": "user", "content": str(messages)}]
            done = [tc.get("function", {}).get("name") for m in msgs if isinstance(m, dict) for tc in (m.get("tool_calls") or [])]
            text = "\n".join(str(m.get("content", "")) for m in msgs if isinstance(m, dict))
            if "register_run" not in done:
                return [self._call("register_run", run_args(text))]
            if "return_work now" in text and "return_work" not in done:
                return [self._call("return_work", {"note": "answered from the file"})]
            return "Registered the count and returned the order."

    def crew(tools, order):
        a = Agent(role="Analyst", goal="Work the order.", backstory=order.system[:400], tools=tools, llm=ScriptedLLM(),
                  verbose=False, max_iter=6)
        return Crew(agents=[a], tasks=[Task(description=order.text, expected_output="A note of at most 120 words.", agent=a)],
                    verbose=False)

    r = asyncio.run(run(TASK, SEATS(crewai_agent(crew)), MODELS(), record=None, budget=Budget(max_calls=40)))
    w = _settled(r)
    assert w.calls == 3 and r.usage["input_tokens"] >= 1200          # three LLM calls per order, read from crew.usage_metrics
