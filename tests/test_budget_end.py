"""The end of the run's budget, not only the end of an order's turns, is where verdicts go missing. In the pa1 sweep
on the BC-250 (2026-11-07) three of four budget stops ended with a live answer on the board that nobody had checked:
S2's reviewer had 14 turns on paper, was cut off by the run after 9 calls and never reviewed (the closing turns are
keyed on turns); S3 and T3 stopped at the warning threshold with an unchecked claim and calls to spare before the
report's hold (nothing is issued past the threshold). Two rules: a worker's closing turns count the run's remaining
calls too, and past the threshold a review of a live answer is still issued — never new work."""
import asyncio
import sys
from pathlib import Path

from hypswarm import Budget, Seat, Task, run
from hypswarm.providers.stub import StubModel, calls_made, tool_outputs

from .test_alpha import SEATS, TASK, make_models
from .test_reviewer_closing import OFFERED, browsing_reviewer

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples"))
from _common import scripted


def _events(res, kind):
    return [e for e in res.scheduler.events if e["kind"] == kind]


def test_a_reviewer_cut_off_by_the_run_budget_still_gives_its_verdict():
    """16 calls, 3 held for the report: the two answers take 6, so the first review has 7 — on a 14-turn order. The
    reviewer browses until the closing turns, which now come from the run's budget, and reviews; Q1 settles."""
    OFFERED.clear()
    models = make_models()
    models["reviewer"] = StubModel(browsing_reviewer, "browsing-reviewer")
    seats = [Seat("analyst", "worker", takes=("accuracy", "question")), Seat("stats", "worker", takes=("significant",)),
             Seat("critic", "reviewer", max_turns=14), Seat("lead", "lead")]
    res = asyncio.run(run(TASK, seats, models, record=None, budget=Budget(max_calls=16)))
    reviews = [w for w in res.scheduler.workers if w.seat == "critic" and w.calls]
    assert reviews and reviews[0].returned and not reviews[0].returned_by_record
    assert reviews[0].calls < 14 and reviews[0].stopped == ""                  # closed by the budget, not by turns
    assert ["review"] in OFFERED
    assert {q["code"]: q["status"] for q in res.board}["Q1"] == "settled"


def test_past_the_warning_threshold_a_review_of_a_live_answer_is_still_issued():
    """Both answers are in by call 6 and Q1 is checked by call 8; the threshold sits at 7.5. Q2's review is issued
    past it — and the run settles instead of draining with Q2 answered."""
    res = asyncio.run(run(TASK, SEATS, make_models(), record=None, budget=Budget(max_calls=30, warn_at=0.25)))
    assert res.stopped == "settled", res.scheduler.events
    assert {q["status"] for q in res.board} == {"settled"}
    late = _events(res, "late_review")
    assert late and late[-1]["question"] == "Q2" and late[-1]["seat"] == "critic"


def test_past_the_warning_threshold_no_work_is_issued():
    res = asyncio.run(run(TASK, SEATS, make_models(), record=None, budget=Budget(max_calls=30, warn_at=0.0)))
    assert res.stopped == "budget: warning threshold"
    assert res.scheduler.orders_issued == 0 and not _events(res, "late_review")
    assert {q["status"] for q in res.board} == {"open"}


def test_the_calls_left_to_an_order_are_its_share_among_the_orders_in_flight():
    """20 calls, 4 held: 16 for orders, 6 spent → 10 left. Alone, T1 can have all 10; with T2 and T3 running too,
    each gets 3 — they spend the 10 three at a time. A unit the scheduler hasn't registered counts itself."""
    from hypswarm.budget import Meter
    m = Meter(Budget(max_calls=20, report_calls=4))
    for _ in range(6):
        m.add("T0", 1, 0, 1)
    assert m.left_for("T1") == 10
    m.in_flight.update({"T1", "T2", "T3"})
    assert m.left_for("T1") == 3 and m.left_for("T2") == 3
    m.in_flight.discard("T1")
    assert m.left_for("T1") == 3                                                 # counts itself beside T2 and T3
    m.in_flight.clear()
    m.in_flight.add("T2")
    assert m.left_for("T1") == 5
    m.reserve("T2")
    assert m.left_for("T1") == 4                                                 # the call in flight is spent


class _Interleaved:
    """A stub that yields to the event loop on every call, so orders in flight really take turns."""
    def __init__(self, inner):
        self.inner, self.name = inner, inner.name

    async def complete(self, messages, tools, *, temperature=None, unit=""):
        await asyncio.sleep(0)
        return await self.inner.complete(messages, tools, temperature=temperature, unit=unit)


def test_a_reviewer_sharing_the_last_calls_with_two_browsing_workers_still_gives_its_verdict():
    """Three orders in flight: the analyst answers Q1 in three calls; two workers browse Q2 and Q3 to the end; the
    critic reviews CL1 and needs both closing turns (its first review names a node that isn't there). Before the
    share, each of the three was told the whole remainder, spent it three at a time, and the critic was cut off
    mid-review (fx1 S3: 13 calls, no verdict). Now Q1 settles."""
    from .test_alpha import _target, worker_script
    OFFERED.clear()
    task = Task(title="Does A beat B", mission="Two models were scored on the same items. Find out whether A beats B.",
                questions=[("Q1", "What is A's accuracy?"), ("Q2", "Is A significantly better than B?"),
                           ("Q3", "How many items are there?")], files={"items.csv": b"item,a,b\n1,1,0\n"})

    def browsing_worker(messages, tools):
        return ("show", {"node": _target(messages)})

    def fumbling_reviewer(messages, tools):
        names = [t.name for t in tools]
        OFFERED.append(names)
        if any("return_work now" in o for o in tool_outputs(messages)) and "return_work" not in calls_made(messages):
            return ("return_work", {"note": "checked"})
        if names == ["review"]:
            node = "CL99" if "review" not in calls_made(messages) else _target(messages)
            return ("review", {"node": node, "verdict": "checked", "method": "Recounted from items.csv.",
                               "notes": "The numbers hold as stated."})
        return ("show", {"node": _target(messages)})

    models = make_models()
    models["analyst"] = _Interleaved(StubModel(worker_script, "stub-analyst"))
    models["browser"] = _Interleaved(StubModel(browsing_worker, "stub-browser"))
    models["reviewer"] = _Interleaved(StubModel(fumbling_reviewer, "fumbling-reviewer"))
    seats = [Seat("analyst", "worker", takes=("accuracy",), model="analyst"),
             Seat("stats", "worker", takes=("significant",), model="browser", max_turns=30),
             Seat("counter", "worker", takes=("many",), model="browser", max_turns=30),
             Seat("critic", "reviewer", max_turns=30), Seat("lead", "lead")]
    res = asyncio.run(run(task, seats, models, record=None, budget=Budget(max_calls=40, report_calls=8)))
    reviews = [w for w in res.scheduler.workers if w.seat == "critic" and w.calls]
    assert reviews and reviews[0].returned and not reviews[0].returned_by_record, reviews
    assert OFFERED.count(["review"]) >= 2                                       # both closing turns came
    assert {q["code"]: q["status"] for q in res.board}["Q1"] == "settled"


def _python(folder: Path) -> list:
    from hypswarm.messages import Tool
    from hypswarm.sandbox import python_subprocess
    return [Tool.from_function(python_subprocess(folder), name="python")]


def test_under_a_workflow_the_review_stage_is_issued_past_the_threshold(tmp_path):
    """The stage path (profiles @2): the analyst's stage order spends the calls that cross the threshold; the review
    stage is still issued, and the question completes."""
    task = Task(title="Does A beat B", mission="Count A's accuracy from items.csv.", questions=[("Q1", "What is A's accuracy?")],
                files={"items.csv": b"item,a\n1,1\n"}, profile="scientific")
    answers = {"Q1": {"summary": "Counted A's correct items in items.csv.", "values": {"acc_a": {"k": 812, "n": 1000}},
                      "code": "print('acc_a', 812, 'of', 1000)", "claim": "A is right on 812 of 1000 items.",
                      "scope": "The 1,000 items in items.csv.", "answer": 0.812}}
    seats = [Seat("analyst", "worker", takes=("accuracy", "counts")), Seat("critic", "reviewer"), Seat("lead", "lead")]
    res = asyncio.run(run(task, seats, scripted(answers), record=tmp_path / "s.hypgraph",
                          budget=Budget(max_calls=40, warn_at=0.1), data_tools=_python(tmp_path)))
    assert res.stopped == "settled", res.scheduler.events
    late = _events(res, "late_review")
    assert late and late[-1]["question"] == "Q1" and late[-1]["seat"] == "critic"
    assert not any(e["kind"] == "stage_order" and e["gates"] != ["reviewed"] and e["t"] > late[0]["t"]
                   for e in res.scheduler.events)                            # no work order after the threshold
