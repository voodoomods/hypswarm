"""End to end with scripted seats: once both questions settle, each conclusion gets its reading; the reviewer objects
to Q2's answer by name (it cannot stand beside Q1's); the next work order on Q2 carries the objection; a worker that
re-files the same conclusion gets one more reading, then the question is capped and the objections stand on the
record."""
import asyncio

from hypswarm import Budget, Pricing, Seat, run
from hypswarm.providers.stub import StubModel, calls_made, tool_outputs
from hypswarm.scheduler import CONSISTENCY_MARK

from .test_alpha import TASK, _target, lead_script, worker_script

SEATS = [Seat("analyst", "worker", takes=("accuracy", "question")), Seat("stats", "worker", takes=("significant",)),
         Seat("critic", "reviewer"), Seat("lead", "lead")]


def _order_text(messages) -> str:
    return " ".join(m.content for m in messages if m.role == "user")


def reviewer_script(messages, tools):
    """Checks every ordinary review; on a reading, objects to the claim about significance and passes the other."""
    done = calls_made(messages)
    outs = tool_outputs(messages)
    if any("return_work now" in o for o in outs) and "return_work" not in done:
        return ("return_work", {"note": "reviewed"})
    if "review" in done:
        return None
    text = _order_text(messages)
    if CONSISTENCY_MARK in text and 'says: "A is not significantly' in text:   # the reading of Q2's own answer
        return ("review", {"node": _target(messages), "verdict": "objection",
                           "method": "Read the answer beside the record's other checked answers.",
                           "notes": "It cannot stand beside CL1: the honest answer to Q2 rests on a test the record "
                                    "does not hold."})
    if CONSISTENCY_MARK in text:
        return ("review", {"node": _target(messages), "verdict": "checked",
                           "method": "Read the answer beside the record's other checked answers.",
                           "notes": "They stand together: a count and a comparison of counts."})
    return ("review", {"node": _target(messages), "verdict": "checked", "method": "Recounted from items.csv.",
                       "notes": "The numbers hold."})


def test_each_conclusion_gets_its_reading_and_an_objection_reopens_the_question(tmp_path):
    models = {"worker": StubModel(worker_script, "stub-worker"), "reviewer": StubModel(reviewer_script, "stub-reviewer"),
              "lead": StubModel(lead_script, "stub-lead")}
    r = asyncio.run(run(TASK, SEATS, models, record=tmp_path / "t.hypgraph", budget=Budget(max_calls=80),
                        pricing=Pricing(0.2, 0.006, 0.6)))
    readings = [e for e in r.scheduler.events if e["kind"] == "consistency_order"]
    assert sorted(e["question"] for e in readings) == ["Q1", "Q2", "Q2"]    # Q2's second answer was read too, then capped
    assert all(e["seat"] == "critic" for e in readings)
    kinds = [e["kind"] for e in r.scheduler.events]
    assert "consistency_cap" in kinds
    orders = [o for o in r.orders if o["objective"].startswith(CONSISTENCY_MARK)]
    assert len(orders) == 3 and all(o["assignee"] == "critic" for o in orders)
    carried = [o for o in r.orders if o["assignee"] == "analyst" and "was objected to on reading" in o["objective"]]
    assert carried and "cannot stand beside CL1" in carried[0]["objective"]     # the next answer sees the objection
    status = {q["code"]: q["status"] for q in r.board}
    assert status["Q1"] == "settled"
    assert r.stopped != "stuck"
