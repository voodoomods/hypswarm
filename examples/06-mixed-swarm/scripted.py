"""
Scripted models for each framework, so the mixed swarm runs offline. Each one answers through its framework's own
tool-calling path — a LangChain BaseChatModel, a PydanticAI FunctionModel, a CrewAI BaseLLM — and the bridges
translate the record's tools for them exactly as they would for a real model. What you cannot see here is a model
reasoning badly; what you can see is every framework meeting the same record.
"""
from __future__ import annotations

import json
import math
import time
from typing import Any


def _args(order_text: str, ka: int, kb: int, n: int) -> dict[str, Any]:
    q = next((ln.split()[1] for ln in order_text.splitlines() if ln.startswith("TARGET")), "Q1")
    if q == "Q2":
        p = (ka + kb) / (2 * n)
        se = math.sqrt(p * (1 - p) * 2 / n)
        z = (ka - kb) / n / se
        pv = 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))
        code = ("import csv, math\nrows = list(csv.DictReader(open('items.csv')))\nn = len(rows)\nka = sum(int(r['a']) for r in rows); kb = sum(int(r['b']) for r in rows)\n"
                "p = (ka + kb) / (2 * n); se = math.sqrt(p * (1 - p) * 2 / n); z = (ka - kb) / n / se\n"
                "pv = 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))\nprint('a', ka, 'of', n); print('b', kb, 'of', n); print('p', round(pv, 4))")
        sig = pv < 0.05
        return {"name": "Q2 comparison", "result_summary": "Q2: Compared A and B with a two-sided two-proportion z-test.",
                "values": {"a": {"k": ka, "n": n}, "b": {"k": kb, "n": n}, "p": {"value": round(pv, 4)}}, "code": code,
                "claim": (f"A is significantly more accurate than B ({ka} of {n} vs {kb} of {n}, p = {pv:.4f})." if sig else
                          f"A is not significantly more accurate than B ({ka} of {n} vs {kb} of {n}, p = {pv:.2f})."),
                "answers": "Q2", "scope": "The 1,000 paired items in items.csv; two-sided test at 0.05."}
    return {"name": "Q1 count", "result_summary": "Q1: Counted A's correct items in items.csv.", "values": {"acc_a": {"k": ka, "n": n}},
            "code": "import csv\nrows = list(csv.DictReader(open('items.csv')))\nk = sum(int(r['a']) for r in rows); n = len(rows)\nprint('acc_a', k, 'of', n)",
            "claim": f"A is right on {ka} of {n} items.", "answers": "Q1", "scope": "The 1,000 paired items in items.csv."}


def _order_text(texts: list[str]) -> str:
    return next((t for t in texts if "WORK ORDER" in t), "")


# ── LangChain: a BaseChatModel that scripts tool calls ───────────────────────
def langchain_model(ka: int, kb: int, n: int) -> Any:
    from langchain_core.language_models import BaseChatModel
    from langchain_core.messages import AIMessage, ToolMessage
    from langchain_core.outputs import ChatGeneration, ChatResult

    class Scripted(BaseChatModel):
        @property
        def _llm_type(self) -> str:
            return "scripted-langchain"

        def bind_tools(self, tools, **kw):
            return self

        def _generate(self, messages, stop=None, run_manager=None, **kw):
            done = [tc["name"] for m in messages if isinstance(m, AIMessage) for tc in m.tool_calls]
            outs = [str(m.content) for m in messages if isinstance(m, ToolMessage)]
            if not done:
                time.sleep(1.05)
                a = _args(_order_text([str(m.content) for m in messages]), ka, kb, n)
                msg = AIMessage(content="", tool_calls=[{"id": "c1", "name": "register_run", "args": a, "type": "tool_call"}],
                                usage_metadata={"input_tokens": 900, "output_tokens": 120, "total_tokens": 1020})
            elif any("return_work now" in o for o in outs) and "return_work" not in done:
                msg = AIMessage(content="", tool_calls=[{"id": "c2", "name": "return_work", "args": {"note": "counted from items.csv with python"}, "type": "tool_call"}],
                                usage_metadata={"input_tokens": 1100, "output_tokens": 30, "total_tokens": 1130})
            else:
                msg = AIMessage(content="Registered the count and returned the order.", usage_metadata={"input_tokens": 1150, "output_tokens": 15, "total_tokens": 1165})
            return ChatResult(generations=[ChatGeneration(message=msg)])
    return Scripted()


def minimal_runnable(model: Any, tools: list[Any]) -> Any:
    """The smallest LangChain tool loop that is a Runnable over {"messages"} — used when langgraph isn't importable."""
    from langchain_core.messages import ToolMessage
    from langchain_core.runnables import RunnableLambda
    by = {t.name: t for t in tools}

    async def loop(state):
        msgs = list(state["messages"])
        for _ in range(12):
            ai = await model.bind_tools(tools).ainvoke(msgs)
            msgs.append(ai)
            if not ai.tool_calls:
                break
            for tc in ai.tool_calls:
                out = await by[tc["name"]].ainvoke(tc["args"])
                msgs.append(ToolMessage(content=str(out), tool_call_id=tc["id"]))
        return {"messages": msgs}
    return RunnableLambda(loop)


# ── PydanticAI: a FunctionModel ───────────────────────────────────────────────
def pydantic_model(ka: int, kb: int, n: int) -> Any:
    from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart, ToolReturnPart
    from pydantic_ai.models.function import FunctionModel

    def script(messages, info):
        done = [p.tool_name for m in messages for p in getattr(m, "parts", []) if isinstance(p, ToolCallPart)]
        outs = [str(p.content) for m in messages for p in getattr(m, "parts", []) if isinstance(p, ToolReturnPart)]
        texts = [str(getattr(p, "content", "")) for m in messages for p in getattr(m, "parts", [])]
        if not done:
            time.sleep(1.05)
            return ModelResponse(parts=[ToolCallPart(tool_name="register_run", args=_args(_order_text(texts), ka, kb, n))])
        if any("return_work now" in o for o in outs) and "return_work" not in done:
            return ModelResponse(parts=[ToolCallPart(tool_name="return_work", args={"note": "compared with a z-test in python"})])
        return ModelResponse(parts=[TextPart(content="Registered the comparison and returned the order.")])
    return FunctionModel(script)


# ── CrewAI: a BaseLLM that returns native tool calls ─────────────────────────
def crewai_llm() -> Any:
    from crewai.llm import BaseLLM

    class Scripted(BaseLLM):
        def __init__(self):
            super().__init__(model="scripted-crewai")

        def supports_function_calling(self) -> bool:
            return True

        @staticmethod
        def _call(name, args):
            return {"id": f"c-{name}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}

        def call(self, messages, tools=None, callbacks=None, available_functions=None, from_task=None, from_agent=None, response_model=None):
            self._track_token_usage_internal({"prompt_tokens": 1400, "completion_tokens": 60, "total_tokens": 1460})
            msgs = messages if isinstance(messages, list) else [{"role": "user", "content": str(messages)}]
            done = [tc.get("function", {}).get("name") for m in msgs if isinstance(m, dict) for tc in (m.get("tool_calls") or [])]
            text = "\n".join(str(m.get("content", "")) for m in msgs if isinstance(m, dict))
            target = next((ln.split()[1] for ln in text.splitlines() if ln.startswith("TARGET")), "")
            if "review" not in done:
                time.sleep(1.05)
                return [self._call("review", {"node": target, "verdict": "checked",
                                              "method": "Read the result's code and the instrument's re-run; recomputed nothing it confirmed.",
                                              "notes": "The claim says what the result says; the scope names the items and the test."})]
            if "return_work now" in text and "return_work" not in done:
                return [self._call("return_work", {"note": "checked"})]
            return "Reviewed the claim and returned the order."
    return Scripted()


def bridges(ka: int, kb: int, n: int) -> tuple[Any, Any, Any]:
    from hypswarm.bridges.crewai import crewai_agent
    from hypswarm.bridges.langchain import langchain_agent
    from hypswarm.bridges.pydantic_ai import pydantic_ai_agent

    def lc_factory(tools):
        try:
            from langgraph.prebuilt import create_react_agent
            return create_react_agent(langchain_model(ka, kb, n), tools)
        except Exception:  # noqa: BLE001 — langgraph absent or blocked on this machine
            return minimal_runnable(langchain_model(ka, kb, n), tools)

    def pai_factory(tools):
        from pydantic_ai import Agent
        return Agent(pydantic_model(ka, kb, n), tools=tools)

    def crew_factory(tools, order):
        from crewai import Agent, Crew, Task
        a = Agent(role="Critic", goal="Review the claim the order names.", backstory=order.system[:600], tools=tools,
                  llm=crewai_llm(), verbose=False, max_iter=6)
        return Crew(agents=[a], tasks=[Task(description=order.text, expected_output="A note of at most 120 words.", agent=a)], verbose=False)
    return langchain_agent(lc_factory), pydantic_ai_agent(pai_factory), crewai_agent(crew_factory)


def lead_script(ka: int, kb: int, n: int):
    from hypswarm.providers.stub import calls_made, tool_outputs

    def lead(messages, tools):
        done, outs = calls_made(messages), tool_outputs(messages)
        if "report_facts" not in done:
            return ("report_facts", {})
        if "submit_report" not in done or (outs and outs[-1].startswith("report refused")):
            facts = next((o for o in outs if o.startswith("## Facts")), "")
            p = (ka + kb) / (2 * n)
            z = (ka - kb) / n / math.sqrt(p * (1 - p) * 2 / n)
            pv = 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))
            return ("submit_report", {"text": facts + "\n\n## Interpretation\n\nThe answers below are the claims the facts list, as the "
                                      "record holds them.\n\n```answers\n" + json.dumps({"Q1": round(ka / n, 3), "Q2": "yes" if pv < 0.05 else "no"}) + "\n```"})
        return None
    return lead
