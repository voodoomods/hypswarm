"""A worker's reads of the record are capped per order, and a rework carries what the first attempt got accepted.
Measured on 18 real-model runs (2026-10-27, studies T2, T3, S3): orders that wrote read a median of 12 times first;
the ones that never wrote read 17-23, up to 41, and a third of reworks never attempted a write. More turns per order
and more calls per run both failed to move that."""
from __future__ import annotations

from hypswarm import Budget, Seat
from hypswarm.budget import Meter
from hypswarm.record import LocalRecord
from hypswarm.scheduler import Scheduler
from hypswarm.tools import READ_CAP, READ_CAP_MSG, worker_tools

SEATS = [Seat("analyst", "worker"), Seat("critic", "reviewer"), Seat("lead", "lead")]


def _record():
    r = LocalRecord(None, SEATS)
    inv = r.start("Does A beat B", "Two models were scored on the same items; find out whether A beats B.",
                  [("Q1", "Is A significantly better than B?")], profile="scientific@2")
    return r, inv


def _tools(r, inv, seat):
    order = r.issue_work(author="harness", inv=inv, target=r.resolve("Q1", inv), assignee=seat.name, role=seat.role,
                         objective="Find out whether A beats B on the items in the file.")["order"]
    return {t.name: t for t in worker_tools(r, seat, inv, order, Meter(Budget(max_calls=100)))}, order


def test_a_worker_past_the_cap_is_told_to_write_and_can_still_write():
    r, inv = _record()
    by, _ = _tools(r, inv, SEATS[0])
    for _ in range(READ_CAP):
        assert "read cap" not in by["show"].fn("Q1")
    assert by["find"].fn(text="A") == READ_CAP_MSG.format(n=READ_CAP)
    assert by["show"].fn("Q1") == READ_CAP_MSG.format(n=READ_CAP + 1)
    out = by["graph_add"].fn(type="hypothesis", fields={"statement": "A beats B on the items.", "predictions": ["A's accuracy is higher."]},
                             links=[{"rel": "answers", "to": "Q1"}])
    assert not out.startswith("refused") and "error" not in out.lower()


def test_a_reviewer_is_not_capped_and_each_order_counts_its_own():
    r, inv = _record()
    by, _ = _tools(r, inv, SEATS[1])
    for _ in range(READ_CAP + 3):
        assert "read cap" not in by["show"].fn("Q1")
    r2, inv2 = _record()
    by2, _ = _tools(r2, inv2, SEATS[0])                    # a fresh order for the worker: a fresh count
    assert "read cap" not in by2["show"].fn("Q1")


def test_a_rework_carries_what_the_first_attempt_got_accepted():
    r, inv = _record()
    s = Scheduler(r, inv, SEATS, model_for=lambda seat: None, meter=Meter(Budget(max_calls=100)))  # type: ignore[arg-type,return-value]
    s._dispatch = lambda seat, order, escalate=False: None   # type: ignore[method-assign]
    q = r.resolve("Q1", inv)
    o = r.issue_work(author="harness", inv=inv, target=q, assignee="analyst", role="worker",
                     objective="Move Q1 through conjectured and claimed: is A significantly better than B?",
                     done_when=[{"p": "hypothesis_stated"}, {"p": "claim_made"}])["order"]
    r.create(author="analyst", type="hypothesis", inv=inv, fields={"statement": "A beats B because its errors cluster on the hard items.",
             "predictions": ["A's accuracy is higher than B's."]}, links=[{"rel": "answers", "to": q}])
    r.return_work(author="analyst", order=o, note="The hypothesis is written; I ran out of turns before the claim.")
    s._settle_and_rework()
    rw = next(x for x in r.orders(inv) if x["status"] == "open")
    text = r.order_text(rw["id"])
    assert "ON THE RECORD ALREADY" in text and "H1 hypothesis: A beats B because its errors cluster" in text
    assert "no live claim" in text or "claim" in text.lower()
