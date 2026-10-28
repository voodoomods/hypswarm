"""An order's turns scale with the gates it carries. Every stage order got the seat's 14 turns whatever it carried: of
78 worker orders measured in trading and scientific runs (studies T2, T3, S3), most ended at exactly 14 with "turns",
a four- or five-gate order was reworked into a fresh context that spent its turns rediscovering what the first
attempt wrote (12-26 `show`s), and the question never settled (item 49)."""
from __future__ import annotations

import asyncio

from hypswarm import Budget, Seat
from hypswarm.budget import Meter
from hypswarm.providers.stub import StubModel
from hypswarm.record import LocalRecord
from hypswarm.scheduler import TURNS_PER_GATE, Scheduler
from hypswarm.worker import run_order

SEATS = [Seat("analyst", "worker"), Seat("critic", "reviewer"), Seat("lead", "lead")]


def _scheduler(profile: str, question, budget: Budget | None = None):
    r = LocalRecord(None, SEATS)
    inv = r.start("Does A beat B", "Two models were scored on the same items; find out whether A beats B.", [question],
                  profile=profile)
    s = Scheduler(r, inv, SEATS, model_for=lambda seat: None, meter=Meter(budget or Budget(max_calls=160)))  # type: ignore[arg-type,return-value]
    s._dispatch = lambda seat, order, escalate=False: None   # type: ignore[method-assign]   # issue, don't run
    s._assign_from_stages(s._stage_rows())
    o = next(o for o in r.orders(inv) if o["status"] == "open")
    return r, s, o


def test_a_five_gate_scientific_order_gets_more_turns_than_a_one_gate_one():
    r, s, o = _scheduler("scientific@2", ("Q1", "Is A significantly better than B?"))
    n = len(r.check_work(o["id"])["predicates"])
    assert n == 5                                                 # hypothesis, preregistered, run, result, claim
    assert s._turns_for(SEATS[0], o["id"]) == 14 + 4 * TURNS_PER_GATE == 30
    r1, s1, o1 = _scheduler("scientific@2", ("Q1", "What is A's accuracy?", "measure"))
    assert len(r1.check_work(o1["id"])["predicates"]) == 3        # the measure question skips two gates
    assert s1._turns_for(SEATS[0], o1["id"]) == 14 + 2 * TURNS_PER_GATE


def test_turns_are_capped_by_the_calls_per_order_and_a_bare_order_keeps_max_turns():
    _r, s, o = _scheduler("scientific@2", ("Q1", "Is A significantly better than B?"), Budget(max_calls=160, per_order_calls=20))
    assert s._turns_for(SEATS[0], o["id"]) == 20
    assert s._turns_for(SEATS[0], "no-such-order") == 14          # unreadable → the seat's own limit


def test_the_worker_runs_the_turns_it_is_given():
    r = LocalRecord(None, SEATS)
    inv = r.start("Does A beat B", "Two models were scored on the same items; find out whether A beats B.",
                  [("Q1", "Is A significantly better than B?")])
    order = r.issue_work(author="harness", inv=inv, target=r.resolve("Q1", inv), assignee="analyst",
                         objective="Find out whether A beats B on the items.")["order"]
    model = StubModel(lambda messages, tools: ("find", {"text": "accuracy"}))   # reads every turn, never returns

    def go(**kw):
        return asyncio.run(run_order(SEATS[0], model, r, inv, order, meter=Meter(Budget(max_calls=200)), **kw))
    assert go(turns=5).turns == 5
    assert go().turns == 14 and go().stopped == "turns"
