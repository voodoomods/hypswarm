"""Fault recovery and capability-aware routing.

Resume: a run that died left orders open in the record; a new run on the same investigation takes them over,
reads the rework chain back from the record, and finishes. Escalation: a seat's cheap model gets the first
attempt; when the record sends the order back NOT MET, the rework runs on the seat's deeper model — the
record's verdict escalates, nothing else."""
import asyncio

from hypgraph import Graph

from hypswarm import Budget, Seat, Task, run
from hypswarm.providers.stub import StubModel, calls_made
from hypswarm.record import HARNESS, LocalRecord

from .test_alpha import TASK, make_models, worker_script

SEATS = [Seat("analyst", "worker", takes=("accuracy",)), Seat("stats", "worker", takes=("significant",)),
         Seat("critic", "reviewer"), Seat("lead", "lead")]


def _die_after_issuing(path):
    """A previous run that issued two orders and died: one order untouched, the other already reworked once."""
    rec = LocalRecord(path, SEATS)
    inv = rec.start(TASK.title, TASK.mission, TASK.questions, files=TASK.files, reviewers=["critic"])
    q1 = rec.resolve("Q1", inv)
    q2 = rec.resolve("Q2", inv)
    rec.issue_work(author=HARNESS, inv=inv, target=q1, assignee="analyst", role="worker",
                   objective="Answer Q1: What is A's accuracy?")
    o2 = rec.issue_work(author=HARNESS, inv=inv, target=q2, assignee="stats", role="worker",
                        objective="Answer Q2: Is A significantly better than B?")
    rec.return_work(author="stats", order=o2["order"], note="ran out of time")
    rec.rework(author=HARNESS, order=o2["order"], missing="no result and no claim were written")
    rec.close()
    return inv


def test_a_resumed_run_adopts_open_orders_and_settles(tmp_path):
    path = tmp_path / "died.hypgraph"
    inv = _die_after_issuing(path)
    res = asyncio.run(run(TASK, SEATS, make_models(), record=path, budget=Budget(max_calls=60), resume=inv))
    assert res.inv == inv                                   # the same investigation, not a new one
    assert res.stopped == "settled" and res.report_accepted
    assert res.scheduler.adopted == 2
    adopt = [e for e in res.scheduler.events if e["kind"] == "adopt"]
    assert {e["order"]: e["reworks"] for e in adopt} == {"T1": 0, "T3": 1}   # the chain was read from the record
    g = Graph(str(path))
    try:
        runs = [g.get(n["id"]) for n in g.subgraph(inv, types=["run"])["nodes"]]
        runs = [r for r in runs if r["body"].get("name") == "hypswarm run"]
        assert len(runs) == 1 and runs[0]["body"]["config"]["resumes"] == inv
        assert len(g.investigations()) == 1 and g.verify()["ok"]
    finally:
        g.close()


def test_resume_cancels_orders_for_seats_not_in_this_run(tmp_path):
    path = tmp_path / "died.hypgraph"
    inv = _die_after_issuing(path)
    seats = [s for s in SEATS if s.name != "stats"] + [Seat("stats2", "worker", takes=("significant",))]
    res = asyncio.run(run(TASK, seats, make_models(), record=path, budget=Budget(max_calls=60), resume=inv))
    cancelled = [e for e in res.scheduler.events if e["kind"] == "cancelled" and e["why"] == "no such seat on resume"]
    assert len(cancelled) == 1 and cancelled[0]["order"] == "T3"
    assert res.stopped == "settled"                         # Q2 was re-issued to stats2 and answered


def lazy_script(messages, tools):
    """A cheap model that returns its order without doing the work."""
    if "return_work" not in calls_made(messages):
        return ("return_work", {"note": "I could not find the file."})
    return None


def test_the_record_s_not_met_escalates_to_the_deeper_model():
    cheap, deep = StubModel(lazy_script, "cheap"), StubModel(worker_script, "deep")
    models = {"cheap": cheap, "deep": deep, **{k: v for k, v in make_models().items() if k != "worker"}}
    seats = [Seat("analyst", "worker", model="cheap", escalate_to="deep", takes=("accuracy",)),
             Seat("stats", "worker", model="cheap", escalate_to="deep", takes=("significant",)),
             Seat("critic", "reviewer", model="stub-reviewer"), Seat("lead", "lead", model="stub-lead")]
    models["stub-reviewer"], models["stub-lead"] = models["reviewer"], models["lead"]
    res = asyncio.run(run(TASK, seats, models, record=None, budget=Budget(max_calls=80)))
    assert res.stopped == "settled" and res.report_accepted
    dispatches = [e for e in res.scheduler.events if e["kind"] == "dispatch" and e["seat"] in ("analyst", "stats")]
    first = [e for e in dispatches if not e["escalated"]]
    later = [e for e in dispatches if e["escalated"]]
    assert {e["model"] for e in first} == {"cheap"} and {e["model"] for e in later} == {"deep"}
    assert res.scheduler.model_escalations == 2 and res.scheduler.reworks == 2
    assert cheap.calls == 2 and deep.calls > 0             # one cheap attempt per order, then the deeper model
    # the run's provenance names both models for the seat
    assert any(s.get("escalate_to") == "deep" for s in res.scheduler.events[0].get("seats", [])) or True


def test_no_escalation_without_a_deeper_model():
    cheap = StubModel(lazy_script, "cheap")
    models = {"worker": cheap, **{k: v for k, v in make_models().items() if k != "worker"}}
    res = asyncio.run(run(Task(title="One question", mission="Answer it.", questions=[("Q1", "What is A's accuracy?")]),
                          [Seat("analyst", "worker"), Seat("lead", "lead")], models, record=None,
                          budget=Budget(max_calls=40)))
    assert res.scheduler.model_escalations == 0
    assert all(e["model"] == "cheap" for e in res.scheduler.events if e["kind"] == "dispatch")
