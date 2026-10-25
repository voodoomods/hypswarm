"""Roles the record can't see but the scheduler must: a reviewer writes verdicts, not answers (a claim by the only
reviewer could never be reviewed); a question answered by an unreviewable claim is re-issued to a worker; and the
report phase has reading and submitting only. Found in pilot 4: both F7 hypswarm runs ended `stuck` because the
critic had written the answer claim and nobody could review it, while the lead spent its report turns planning."""
import asyncio
import time

from hypswarm import Budget, Seat, run
from hypswarm.providers.stub import StubModel, calls_made, tool_outputs
from hypswarm.record import LocalRecord

from .test_alpha import TASK, lead_script, make_models, reviewer_script

SEATS = [Seat("analyst", "worker", takes=("accuracy",)), Seat("stats", "worker", takes=("significant",)),
         Seat("critic", "reviewer"), Seat("lead", "lead")]


def eager_reviewer(messages, tools):
    """A reviewer that tries to write the answer itself before reviewing."""
    done = calls_made(messages)
    outs = tool_outputs(messages)
    if "graph_add" not in done:
        return ("graph_add", {"type": "claim", "fields": {"statement": "A is right on 812 of 1000 items.",
                                                          "scope": "The 1000 paired items."},
                              "links": [{"rel": "answers", "to": "Q1"}]})
    return reviewer_script(messages, tools)


def test_a_reviewer_cannot_write_a_claim():
    models = make_models()
    models["reviewer"] = StubModel(eager_reviewer, "eager-reviewer")
    res = asyncio.run(run(TASK, SEATS, models, record=None, budget=Budget(max_calls=60)))
    assert res.stopped == "settled"
    refused = [row for w in res.scheduler.workers if w.seat == "critic" for row in w.tool_log
               if row["tool"] == "graph_add"]
    assert refused and all(r["out"].startswith("refused: you are a reviewer") for r in refused)
    assert all(o["assignee"] != "critic" or o["target"].startswith("CL") for o in res.orders)   # reviews only


def test_an_unreviewable_answer_is_reissued_to_a_worker(tmp_path):
    """A record where the only reviewer already answered Q1 (as an outside seat could): the scheduler asks a worker
    for the answer instead of waiting on a review nobody may write."""
    path = tmp_path / "critic-answered.hypgraph"
    rec = LocalRecord(path, SEATS)
    inv = rec.start(TASK.title, TASK.mission, TASK.questions, files=TASK.files, reviewers=["critic"])
    r = rec.create(author="critic", type="run", inv=inv, fields={"kind": "agent", "name": "count", "state": "succeeded"})
    rs = rec.create(author="critic", type="result", inv=inv, fields={"summary": "Counted the paired items in the file.", "values": {"acc": {"k": 812, "n": 1000}}},
                    links=[{"rel": "produced", "from": r["id"]}])
    rec.create(author="critic", type="claim", inv=inv, fields={"statement": "A is right on 812 of 1000 items.",
                                                               "scope": "The 1000 paired items."},
               links=[{"rel": "answers", "to": rec.resolve("Q1", inv)}, {"rel": "derived_from", "to": rs["id"]}])
    rec.close()
    time.sleep(1.1)        # the record's "written after the order" rule has second resolution: age the critic's claim
    res = asyncio.run(run(TASK, SEATS, make_models(), record=path, budget=Budget(max_calls=80), resume=inv))
    assert res.stopped == "settled" and res.report_accepted
    ev = [e for e in res.scheduler.events if e["kind"] == "unreviewable"]
    assert len(ev) == 1 and ev[0]["claim"] == "CL1" and ev[0]["by"] == "critic" and ev[0]["reissued_to"] == "analyst"
    q1 = next(q for q in res.board if q["code"] == "Q1")
    assert q1["status"] == "settled" and not q1["by"].startswith("CL1 ")   # a worker's answer, reviewed by the critic


def planning_lead(messages, tools):
    """A lead that would rather plan than report: it tries add / rework / cancel, then reports."""
    done = calls_made(messages)
    names = {t.name for t in tools}
    assert not names & {"add", "rework", "cancel_work"}, f"planning tools in the report phase: {names}"
    return lead_script(messages, tools)


def test_the_report_phase_has_no_planning_tools():
    models = make_models()
    models["lead"] = StubModel(planning_lead, "planning-lead")
    res = asyncio.run(run(TASK, SEATS, models, record=None, budget=Budget(max_calls=60)))
    assert res.stopped == "settled" and res.report_accepted
