"""An agent seat: a whole agent from any framework holds a seat. It gets the order and the record's tools, runs its
own loop, reports what it used; the record judges done, the budget counts the reported calls, and an agent that
stops without returning is returned on its behalf. No framework here — a plain async function is an agent."""
import asyncio

from hypswarm import AgentOrder, AgentOutcome, Budget, Seat, run
from hypswarm.providers.stub import StubModel

from .test_alpha import TASK, lead_script, reviewer_script


def _tool(order: AgentOrder, name):
    return next(t for t in order.tools if t.name == name)


async def honest_agent(order: AgentOrder) -> AgentOutcome:
    """Reads the order, registers a result with a claim in one call, returns when the reply says so."""
    assert "WORK ORDER" in order.text and "DONE WHEN" in order.text
    assert order.system.startswith("You are ") and "MISSION" in order.system
    q = next(l for l in order.text.splitlines() if l.startswith("TARGET")).split()[1]
    vals = {"acc_a": {"k": 812, "n": 1000}} if q == "Q1" else {"a": {"k": 812, "n": 1000}, "b": {"k": 800, "n": 1000}}
    stmt = ("A is right on 812 of 1000 items." if q == "Q1"
            else "A is not significantly more accurate than B (812 of 1000 vs 800 of 1000).")
    out = await _tool(order, "register_run").call({"name": f"count {q}", "result_summary": f"Counted for {q}.",
                                                   "values": vals, "claim": stmt, "answers": q,
                                                   "scope": "The 1000 paired items."})
    assert "claim CL" in out, out
    log = [{"tool": "register_run", "args": {"answers": q}}]
    if "return_work now" in out:
        await _tool(order, "return_work").call({"note": "answered from the file"})
        log.append({"tool": "return_work", "args": {}})
    return AgentOutcome(note="done", calls=3, input_tokens=3000, cached_tokens=1000, output_tokens=300, log=log)


async def overclaiming_agent(order: AgentOrder) -> str:
    """An agent that tries 'never', gets refused, and hands back a note without returning itself."""
    t = _tool(order, "graph_add")
    out = await t.call({"type": "claim", "fields": {"statement": "A never fails.", "scope": "items.csv"},
                        "links": [{"rel": "answers", "to": "Q1"}]})
    assert out.startswith("refused:") and "ABSOLUTE" in out, out
    return "could not write the claim: " + out[:80]


SEATS = [Seat("analyst", "worker", takes=("accuracy",), agent=honest_agent),
         Seat("stats", "worker", takes=("significant",), agent=honest_agent),
         Seat("critic", "reviewer"), Seat("lead", "lead")]


def test_agent_seats_settle_the_board_and_are_metered(tmp_path):
    models = {"reviewer": StubModel(reviewer_script), "lead": StubModel(lead_script)}
    r = asyncio.run(run(TASK, SEATS, models, record=tmp_path / "a.hypgraph", budget=Budget(max_calls=60)))
    assert r.stopped == "settled" and r.report_accepted, r.scheduler.events
    assert {q["code"]: q["status"] for q in r.board} == {"Q1": "settled", "Q2": "settled"}
    ws = [w for w in r.scheduler.workers if w.seat in ("analyst", "stats")]
    assert len(ws) == 2 and all(w.returned and not w.returned_by_record and w.calls == 3 for w in ws)
    assert r.usage["calls"] == 6 + sum(w.calls for w in r.scheduler.workers if w.seat == "critic") + r.scheduler.lead_calls
    assert r.usage["input_tokens"] >= 6000 and r.usage["cached_tokens"] >= 2000
    d = next(e for e in r.scheduler.events if e["kind"] == "dispatch" and e["seat"] == "analyst")
    assert d["model"] == "agent:honest_agent"
    assert any(s["model"] == "agent:honest_agent" for s in r.scheduler.config["seats"]) if hasattr(r.scheduler, "config") else True


def test_a_refused_agent_is_returned_with_its_note_and_the_question_is_not_settled():
    seats = [Seat("analyst", "worker", agent=overclaiming_agent), Seat("critic", "reviewer"), Seat("lead", "lead")]
    models = {"reviewer": StubModel(reviewer_script), "lead": StubModel(lead_script)}
    r = asyncio.run(run(TASK, seats, models, record=None, budget=Budget(max_calls=20, per_order_calls=5)))
    w = next(w for w in r.scheduler.workers if w.seat == "analyst")
    assert w.returned and not w.returned_by_record            # the bridge returned it with the agent's note
    assert w.tool_log[-1]["tool"] == "return_work" and "NOT every predicate met" in w.tool_log[-1]["out"]
    o = next(o for o in r.orders if o["assignee"] == "analyst")
    assert "could not write the claim" in (o.get("note") or "") or o["status"] in ("returned", "reworked", "cancelled")


def test_a_crashing_agent_is_returned_by_the_record():
    async def boom(order: AgentOrder):
        raise RuntimeError("framework exploded")
    seats = [Seat("analyst", "worker", agent=boom), Seat("critic", "reviewer"), Seat("lead", "lead")]
    models = {"reviewer": StubModel(reviewer_script), "lead": StubModel(lead_script)}
    r = asyncio.run(run(TASK, seats, models, record=None, budget=Budget(max_calls=20, per_order_calls=4)))
    w = next(w for w in r.scheduler.workers if w.seat == "analyst")
    assert w.returned_by_record and w.stopped.startswith("error: RuntimeError") and w.calls == 0


def test_an_agent_is_never_started_past_the_budget():
    started = []

    async def counting(order: AgentOrder):
        started.append(order.code)
        return AgentOutcome(note="x", calls=1)
    seats = [Seat("analyst", "worker", agent=counting), Seat("critic", "reviewer"), Seat("lead", "lead")]
    models = {"reviewer": StubModel(reviewer_script), "lead": StubModel(lead_script)}
    r = asyncio.run(run(TASK, seats, models, record=None, budget=Budget(max_calls=1)))
    assert r.stopped.startswith("budget") and len(started) <= 1
