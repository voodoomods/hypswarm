"""A checked answer beside a live unchecked one doesn't settle a question (hypgraph: every live answer must be
checked). The scheduler sends the review to the unchecked answer — not again to the checked one — and tells the
reviewer what it sits beside: a re-run confirms numbers, not what they mean (studies T1, run 5)."""
import asyncio
import time

import pytest

from hypswarm import Budget, run
from hypswarm.record import LocalRecord

from .test_alpha import TASK, make_models
from .test_roles import SEATS

hypgraph_derive = pytest.importorskip("hypgraph.derive")
pytestmark = pytest.mark.skipif(not hasattr(hypgraph_derive, "unchecked_answers"),
                                reason="needs hypgraph with opposed-answer settlement")


def _answer(rec, inv, author, statement, k):
    r = rec.create(author=author, type="run", inv=inv, fields={"kind": "agent", "name": "count", "state": "succeeded"})
    rs = rec.create(author=author, type="result", inv=inv, fields={"summary": "Counted the paired items in the file.",
                    "values": {"acc": {"k": k, "n": 1000}}}, links=[{"rel": "produced", "from": r["id"]}])
    return rec.create(author=author, type="claim", inv=inv, fields={"statement": statement,
                      "scope": "The 1000 paired items."},
                      links=[{"rel": "answers", "to": rec.resolve("Q1", inv)}, {"rel": "derived_from", "to": rs["id"]}])


def test_the_second_answer_is_reviewed_with_what_it_sits_beside(tmp_path):
    path = tmp_path / "two-answers.hypgraph"
    rec = LocalRecord(path, SEATS)
    inv = rec.start(TASK.title, TASK.mission, TASK.questions, files=TASK.files, reviewers=["critic"])
    first = _answer(rec, inv, "analyst", "A is right on 812 of 1000 items.", 812)
    rec.review(author="critic", target=first["id"], verdict="checked", method="Recounted the file.",
               notes="812 of 1000, as stated.")
    second = _answer(rec, inv, "stats", "A is right on 798 of 1000 items.", 798)
    row = next(b for b in rec.question_board(inv) if b["code"] == "Q1")
    assert row["status"] == "answered" and row["unchecked"] == [second["code"]]
    rec.close()
    time.sleep(1.1)
    res = asyncio.run(run(TASK, SEATS, make_models(), record=path, budget=Budget(max_calls=80), resume=inv))
    reviews = [o for o in res.orders if o["target"] == second["code"]]
    assert reviews and reviews[0]["assignee"] == "critic"
    assert not [o for o in res.orders if o["target"] == first["code"]]          # the checked one isn't reviewed again
    assert "sits beside " + first["code"] in reviews[0]["objective"]


def test_an_unchecked_answer_from_another_order_is_reviewed_under_a_workflow():
    """O2 (evening): the modeller, working on Q1, also answered Q2. That claim was in no gate's evidence, so the review
    stage went to the newest claim (already checked) and the run stopped stuck with Q2 held open."""
    from hypswarm import Seat
    from hypswarm.budget import Meter
    from hypswarm.scheduler import Scheduler
    seats = [Seat("analyst", "worker"), Seat("stats", "worker"), Seat("critic", "reviewer")]
    rec = LocalRecord(None, seats)
    inv = rec.start(TASK.title, TASK.mission, TASK.questions, files=TASK.files, reviewers=["critic"])
    first = _answer(rec, inv, "analyst", "A is right on 812 of 1000 items.", 812)
    rec.review(author="critic", target=first["id"], verdict="checked", method="Recounted the file.",
               notes="812 of 1000, as stated.")
    second = _answer(rec, inv, "stats", "A is right on 812 of 1000 items, counted again.", 812)
    s = Scheduler(rec, inv, seats, model_for=lambda seat: None, meter=Meter(Budget(max_calls=10)))  # type: ignore[arg-type,return-value]
    sent: list[str] = []
    s._issue_review_on = lambda q, first_, target, code, text, busy: sent.append(code)  # type: ignore[method-assign]
    gates = [{"gate": "claim_made", "met": True, "evidence": [first["code"]], "who": "analyst"},
             {"gate": "reviewed", "met": False, "evidence": [], "who": "critic", "stage": "reviewed"}]
    q = {"question": rec.resolve("Q1", inv), "code": "Q1"}
    s._issue_review_stage(q, gates, 1, "What is A's accuracy?", set())
    assert sent == [second["code"]]
