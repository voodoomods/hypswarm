"""An answered question gets its review and nothing else. Under a workflow, the stage path issued the review of an
unchecked answer and, in the same round, a work order on the same question whenever an earlier gate still read open —
on a measured question the run gate read "no run executes an experiment" with the result and the claim both met, so a
`run` order went out at every round beside the review. S3 on the BC-250 (fx1 and fx2, 2026-11-07): the seats filed 11
claims on 3 questions, each new one unchecked, and nothing settled. The review decides what stands; more answers only
join the queue."""
from hypswarm import Budget, Seat
from hypswarm.budget import Meter
from hypswarm.record import LocalRecord
from hypswarm.scheduler import Scheduler

from .test_alpha import TASK
from .test_opposed_answers import _answer


def _rows(q1: str, claim_code: str, run_met: bool) -> list:
    def gate(stage, name, met, why="", evidence=(), who="worker"):
        return {"stage": stage, "gate": name, "met": met, "optional": False, "why": why, "evidence": list(evidence),
                "who": who}
    return [{"question": q1, "code": "Q1", "complete": False, "index": 4, "of": 8, "profile": "scientific@2",
             "gates": [gate("asked", "stated", True, evidence=["Q1"], who="lead"),
                       gate("run", "run_registered", run_met, "no run executes an experiment on Q1", who="worker, instrument"),
                       gate("evidenced", "result_exists", True, evidence=["RS1"], who="worker, instrument"),
                       gate("claimed", "claim_made", True, evidence=[claim_code]),
                       gate("reviewed", "reviewed", False, "no claim answering Q1 is checked", who="reviewer")]}]


def _scheduler():
    seats = [Seat("analyst", "worker"), Seat("stats", "worker"), Seat("critic", "reviewer")]
    rec = LocalRecord(None, seats)
    inv = rec.start(TASK.title, TASK.mission, TASK.questions, files=TASK.files, reviewers=["critic"])
    first = _answer(rec, inv, "analyst", "A is right on 812 of 1000 items.", 812)
    s = Scheduler(rec, inv, seats, model_for=lambda seat: None, meter=Meter(Budget(max_calls=10)))  # type: ignore[arg-type,return-value]
    sent: list[str] = []
    issued: list[tuple[str, str]] = []
    s._issue_review_on = lambda q, first_, target, code, text, busy, **kw: (sent.append(code), busy.add(target))  # type: ignore[method-assign]
    s._issue = lambda seat, target, objective, done_when=None: issued.append((seat.name, target)) or True  # type: ignore[method-assign]
    return rec, inv, first, s, sent, issued


def test_an_answered_question_gets_its_review_and_no_work_order_beside_it():
    rec, inv, first, s, sent, issued = _scheduler()
    s._assign_from_stages(_rows(rec.resolve("Q1", inv), first["code"], run_met=False))
    assert sent == [first["code"]]
    assert issued == [], issued                              # before: a `run` order to a worker in the same round


def test_with_the_review_already_in_flight_still_no_work_order():
    from hypswarm.scheduler import HARNESS
    rec, inv, first, s, sent, issued = _scheduler()
    q1 = rec.resolve("Q1", inv)
    rec.issue_work(author=HARNESS, inv=inv, target=first["id"], assignee="critic", role="reviewer",
                   objective="Review CL1: recount from items.csv.", done_when=[{"p": "reviewed"}])
    s._assign_from_stages(_rows(q1, first["code"], run_met=False))   # the review is on the board already
    assert sent == [] and issued == [], (sent, issued)


def test_an_open_question_still_gets_its_work_order():
    seats = [Seat("analyst", "worker"), Seat("critic", "reviewer")]
    rec = LocalRecord(None, seats)
    inv = rec.start(TASK.title, TASK.mission, TASK.questions, files=TASK.files, reviewers=["critic"])
    s = Scheduler(rec, inv, seats, model_for=lambda seat: None, meter=Meter(Budget(max_calls=10)))  # type: ignore[arg-type,return-value]
    issued: list[tuple[str, str]] = []
    s._issue = lambda seat, target, objective, done_when=None: issued.append((seat.name, target)) or True  # type: ignore[method-assign]
    q1 = rec.resolve("Q1", inv)
    rows = _rows(q1, "CL1", run_met=False)
    rows[0]["gates"][3]["met"] = False                       # no claim yet: the question is open, not answered
    rows[0]["gates"][3]["evidence"] = []
    s._assign_from_stages(rows)
    assert issued == [("analyst", q1)]
