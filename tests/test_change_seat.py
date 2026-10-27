"""The seat a change stage names (software: the implementer, on diff_registered) isn't the fallback for another stage,
and a stage that only reads the code says so. With the tester busy, a counting question's claim stage went to the
implementer, who rewrote the code under test: the new head made every check stale and nothing settled (studies E4,
evening run). A value in seconds is a timing only when the code measures time."""
from __future__ import annotations

from hypswarm import Budget, Seat
from hypswarm.budget import Meter
from hypswarm.record import LocalRecord
from hypswarm.scheduler import READ_ONLY, Scheduler, _changers
from hypswarm.tools import worker_tools

SEATS = [Seat("implementer", "worker"), Seat("tester", "worker"), Seat("reviewer", "reviewer"), Seat("lead", "lead")]


def _scheduler() -> tuple[LocalRecord, str, Scheduler]:
    r = LocalRecord(None, SEATS)
    inv = r.start("parse_duration against its contract", "Check every case.",
                  [("Q1", "How many of the 12 cases does parse_duration satisfy?", "measure")], profile="software@2")
    return r, inv, Scheduler(r, inv, SEATS, model_for=lambda s: None, meter=Meter(Budget(max_calls=10)))  # type: ignore[arg-type,return-value]


def test_the_change_seat_is_named_by_the_software_workflow():
    _r, _inv, s = _scheduler()
    rows = s._stage_rows()
    assert rows and _changers(rows[0]["gates"]) == {"implementer"}


def test_a_read_only_stage_waits_for_its_seat_rather_than_go_to_the_implementer():
    _r, _inv, s = _scheduler()
    gates = s._stage_rows()[0]["gates"]
    s.busy["tester"] = "elsewhere"
    assert s._pick_for_stage(s.workers, "tester", "How many cases pass?").name == "implementer"   # the old fallback
    assert s._pick_for_stage(s.workers, "tester", "How many cases pass?", avoid=_changers(gates)) is None
    del s.busy["tester"]
    assert s._pick_for_stage(s.workers, "tester", "How many cases pass?", avoid=_changers(gates)).name == "tester"


def test_the_claim_order_goes_to_the_tester_and_says_not_to_edit():
    r, inv, s = _scheduler()
    s._dispatch = lambda seat, order, escalate=False: None   # type: ignore[method-assign]   # issue, don't run
    s._assign_from_stages(s._stage_rows())
    o = next(o for o in r.orders(inv) if o["status"] == "open")
    assert o["assignee"] == "tester" and READ_ONLY.strip() in str(o.get("objective"))


def test_a_value_in_seconds_is_data_unless_the_code_measures_time():
    r = LocalRecord(None, [Seat("tester", "worker"), Seat("critic", "reviewer")])
    inv = r.start("parse_duration", "Check parse_duration against its spec.", [("Q1", "What does parse_duration('2.6s') return?")])
    order = r.issue_work(author="harness", inv=inv, target=r.resolve("Q1", inv), assignee="tester",
                         objective="Check what parse_duration returns for each case in the spec.")["order"]
    reg = next(t for t in worker_tools(r, Seat("tester", "worker"), inv, order, Meter(Budget(max_calls=10)))
               if t.name == "register_run")
    ok = reg.fn(name="case8", result_summary="parse_duration('2.6s') returned 2 seconds; the spec expects 3.",
                code="from duration import parse_duration\nprint('case8_returned_seconds', parse_duration('2.6s'))",
                values={"case8_returned_seconds": {"value": 2, "unit": "s"}, "case8_expected_seconds": {"value": 3, "unit": "s"}})
    assert ok.startswith("run "), ok
    timed = reg.fn(name="t", result_summary="Timed it.", values={"elapsed_s": {"value": 0.002, "unit": "s"}},
                   code="import time\nt = time.perf_counter()\nprint('elapsed_s', time.perf_counter() - t)")
    assert timed.startswith("refused") and "spread" in timed
