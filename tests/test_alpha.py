"""The alpha, end to end on scripted models: the scheduler issues orders from the board, workers write to the
record and return when it says they're done, a reviewer settles each question, the lead writes a report that
passes the record's check — and no model is ever called for anything mechanical."""
import asyncio
import json
from typing import Any

import pytest

from hypswarm import Budget, Pricing, Seat, Task, run
from hypswarm.messages import Message, Tool
from hypswarm.providers.stub import StubModel, calls_made, tool_outputs

TASK = Task(title="Does A beat B", mission="Two models were scored on the same items. Find out whether A beats B.",
            questions=[("Q1", "What is A's accuracy?"), ("Q2", "Is A significantly better than B?")],
            files={"items.csv": b"item,a,b\n1,1,0\n"})


def _order_code(messages) -> str:
    for m in messages:
        if m.role == "user" and "WORK ORDER" in m.content:
            return m.content.split()[2]
    return "?"


def _target(messages) -> str:
    for m in messages:
        if m.role == "user" and "TARGET" in m.content:
            line = next(l for l in m.content.splitlines() if l.startswith("TARGET"))
            return line.split()[1]
    return "?"


def worker_script(messages, tools):
    """Register a result, make a claim answering the question, return when the record says the order is met."""
    done = calls_made(messages)
    outs = tool_outputs(messages)
    if any("return_work now" in o for o in outs) and "return_work" not in done:
        return ("return_work", {"note": "answered from the file"})
    if "register_run" not in done:
        q = _target(messages)
        vals = {"acc_a": {"k": 812, "n": 1000}} if q == "Q1" else {"a": {"k": 812, "n": 1000}, "b": {"k": 800, "n": 1000}}
        return ("register_run", {"name": f"count for {q}", "result_summary": f"Counted the items for {q}.", "values": vals})
    if "graph_add" not in done:
        q = _target(messages)
        stmt = ("A is right on 812 of 1000 items." if q == "Q1" else
                "A is not significantly more accurate than B (812 of 1000 vs 800 of 1000).")
        return ("graph_add", {"type": "claim", "fields": {"statement": stmt, "scope": "The 1000 paired items."},
                              "links": [{"rel": "answers", "to": q}]})
    return None


def reviewer_script(messages, tools):
    done = calls_made(messages)
    outs = tool_outputs(messages)
    if any("return_work now" in o for o in outs) and "return_work" not in done:
        return ("return_work", {"note": "checked"})
    if "review" not in done:
        return ("review", {"node": _target(messages), "verdict": "checked", "method": "Recounted from items.csv.",
                           "notes": "The numbers hold."})
    return None


def lead_script(messages, tools):
    done = calls_made(messages)
    outs = tool_outputs(messages)
    if "report_facts" not in done:
        return ("report_facts", {})
    if "submit_report" not in done or (outs and outs[-1].startswith("report refused")):
        facts = next((o for o in outs if o.startswith("## Facts")), "")
        return ("submit_report", {"text": facts + "\n\n## Interpretation\n\nA is right on 812 of 1000 (CL1). "
                                  "A is not significantly better than B (CL2).\n\n```answers\n"
                                  + json.dumps({"Q1": 0.812, "Q2": "no"}) + "\n```"})
    return None


def make_models():
    return {"worker": StubModel(worker_script, "stub-worker"), "reviewer": StubModel(reviewer_script, "stub-reviewer"),
            "lead": StubModel(lead_script, "stub-lead")}


SEATS = [Seat("analyst", "worker", takes=("accuracy", "question")), Seat("stats", "worker", takes=("significant",)),
         Seat("critic", "reviewer"), Seat("lead", "lead")]


def test_a_swarm_settles_every_question_and_the_report_passes(tmp_path):
    models = make_models()
    r = asyncio.run(run(TASK, SEATS, models, record=tmp_path / "t.hypgraph", budget=Budget(max_calls=60),
                        pricing=Pricing(0.2, 0.006, 0.6)))
    assert r.stopped == "settled", r.scheduler.events
    assert {q["code"]: q["status"] for q in r.board} == {"Q1": "settled", "Q2": "settled"}
    assert r.report_accepted and r.answers() == {"Q1": 0.812, "Q2": "no"}
    st = [o["status"] for o in r.orders]
    assert st.count("accepted") == 4 and set(st) == {"accepted"}           # 2 answers + 2 reviews, all settled
    kinds = [e["kind"] for e in r.scheduler.events]
    assert kinds.count("settled") == 4 and "rework" not in kinds and "escalate" not in kinds
    assert r.scheduler.lead_calls == 2                                    # report_facts + submit_report, nothing else
    assert r.usage["calls"] == sum(w.calls for w in r.scheduler.workers) + r.scheduler.lead_calls
    assert r.usage["usd"] > 0 and r.usage["calls"] <= 60
    assert all(w.returned and not w.returned_by_record for w in r.scheduler.workers)
    assert r.run_node and r.record_path.endswith("t.hypgraph")


def test_parallel_workers_take_different_questions(tmp_path):
    models = make_models()
    r = asyncio.run(run(TASK, SEATS, models, record=None, budget=Budget(max_calls=60)))
    first_round = [e for e in r.scheduler.events if e["kind"] == "dispatch"][:2]
    assert {e["seat"] for e in first_round} == {"analyst", "stats"}        # both workers busy at once
    assert r.stopped == "settled"


def test_without_a_reviewer_questions_stay_answered_and_the_run_ends_honestly():
    models = make_models()
    seats = [Seat("analyst", "worker"), Seat("lead", "lead")]
    r = asyncio.run(run(TASK, seats, models, budget=Budget(max_calls=40)))
    assert r.stopped == "stuck"                                            # answered, nobody to check: not settled
    assert {q["status"] for q in r.board} == {"answered"}
    assert r.report_accepted                                               # the report still says what stands


def test_a_stuck_order_is_reworked_twice_then_escalated_to_the_lead():
    def lazy(messages, tools):
        return None                                                        # never writes anything

    def lead(messages, tools):
        done = calls_made(messages)
        if "cancel_work" not in done and any("EXCEPTION" in m.content for m in messages if m.role == "user"):
            code = next(m.content for m in messages if m.role == "user" and "EXCEPTION" in m.content).split("order ")[1].split()[0]
            return ("cancel_work", {"order": code, "why": "the worker can't do it; dropping the question"})
        return lead_script(messages, tools)
    models = {"worker": StubModel(lazy), "lead": StubModel(lead)}
    r = asyncio.run(run(Task("Nobody can", "A task nobody can do.", [("Q1", "Unanswerable?")]),
                        [Seat("analyst", "worker"), Seat("lead", "lead")], models, budget=Budget(max_calls=40)))
    kinds = [e["kind"] for e in r.scheduler.events]
    assert kinds.count("rework") == 2 and kinds.count("escalate") == 1
    assert any(o["status"] == "cancelled" for o in r.orders)
    assert all(w.returned_by_record for w in r.scheduler.workers)         # returned on the lazy worker's behalf


def test_the_budget_is_a_hard_stop():
    models = make_models()
    r = asyncio.run(run(TASK, SEATS, models, budget=Budget(max_calls=5)))
    assert r.stopped.startswith("budget") and r.usage["calls"] <= 5


def test_seats_are_validated_and_tools_come_from_signatures():
    with pytest.raises(ValueError):
        Seat("Lab")
    with pytest.raises(ValueError):
        Seat("lab")
    with pytest.raises(ValueError):
        Seat("x", "boss")

    def f(a: int, b: str = "x", c: list[str] | None = None) -> str:
        """Does f."""
        return f"{a}{b}{c}"
    t = Tool.from_function(f)
    assert t.parameters["required"] == ["a"] and t.parameters["properties"]["c"] == {"type": "array", "items": {"type": "string"}}
    assert t.description == "Does f."
    assert asyncio.run(t.call({"a": 1})) == "1xNone"
    assert asyncio.run(t.call({"zzz": 1})).startswith("error: bad arguments")


def test_data_tools_reach_workers_the_seat_allows(tmp_path):
    seen: list[str] = []

    def read_file(name: str) -> str:
        """Read a file."""
        seen.append(name)
        return "item,a,b"

    def peek(messages, tools):
        names = [t.name for t in tools]
        if "read_file" in names and "read_file" not in calls_made(messages):
            return ("read_file", {"name": "items.csv"})
        return worker_script(messages, tools)
    models = {"worker": StubModel(peek), "reviewer": StubModel(reviewer_script), "lead": StubModel(lead_script)}
    seats = [Seat("analyst", "worker", tools=("read_file",)), Seat("stats", "worker", tools=()),
             Seat("critic", "reviewer"), Seat("lead", "lead")]
    r = asyncio.run(run(TASK, seats, models, budget=Budget(max_calls=60), data_tools=[Tool.from_function(read_file)]))
    assert r.stopped == "settled" and seen == ["items.csv"]                # only the analyst was allowed the tool
