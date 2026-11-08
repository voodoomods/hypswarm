"""A complete question whose answer is a conclusion gets one focused reading before it stands: can its checked answer
be the record's answer while the checked answers to the other questions stand? With the siblings only listed inside
the ordinary review order (#55) the critic read them and wrote "no conflict" — S3's "the arm has a lower mean steps_k"
beside "none remain significant after Holm", T1's "take a paper position" beside "the signal depends on future prices"
(BC-250 re1, re2, 2026-11-07). The reading is a separate order with one question."""
from hypswarm import Budget, Seat
from hypswarm.budget import Meter
from hypswarm.record import LocalRecord
from hypswarm.scheduler import CONSISTENCY_MARK, OBJECTIVE_MAX, Scheduler

SEATS = [Seat("analyst", "worker"), Seat("stats", "worker"), Seat("critic", "reviewer")]
TWO_REVIEWERS = SEATS + [Seat("auditor", "reviewer")]
QUESTIONS = [("Q1", "Which outcomes differ between the arms at p < 0.05 without correction?", "measure"),
             ("Q2", "After correcting for the 20 outcomes tested, which differences remain significant?", "measure"),
             ("Q3", "Does the supplement change steps_k?")]
MISSION = "PRESS.md announces a trial result; trial.csv has every participant's arm and 20 measured outcomes, so analyse it."
REVIEW = {"method": "Recomputed every number from trial.csv.", "notes": "Every number holds and the method answers the question."}


def _answer(rec, inv, author, q, statement):
    r = rec.create(author=author, type="run", inv=inv, fields={"kind": "agent", "name": "stats", "state": "succeeded"})
    rs = rec.create(author=author, type="result", inv=inv, fields={"summary": "Welch tests on the 20 outcomes.",
                    "values": {"p_steps_k": {"value": 0.0124}}}, links=[{"rel": "produced", "from": r["id"]}])
    return rec.create(author=author, type="claim", inv=inv,
                      fields={"statement": statement, "scope": "Every participant in trial.csv, each arm compared by a Welch test per outcome."},
                      links=[{"rel": "answers", "to": rec.resolve(q, inv)}, {"rel": "derived_from", "to": rs["id"]}])


def _settled_record(q3_author="stats", seats=SEATS, reviewer="critic"):
    rec = LocalRecord(None, seats)
    inv = rec.start("Does the supplement change steps_k?", MISSION, QUESTIONS, files=[],
                    reviewers=[s.name for s in seats if s.role == "reviewer"])
    q1 = _answer(rec, inv, "analyst", "Q1", "The only outcome that differs between the arms before correction is steps_k, lower on the supplement.")
    q2 = _answer(rec, inv, "analyst", "Q2", "No outcome remains significant after correction for the outcomes tested.")
    q3 = _answer(rec, inv, q3_author, "Q3", "The supplement reduces steps_k compared to placebo.")
    for c in (q1, q2, q3):
        rec.review(author=reviewer, target=c["id"], verdict="checked", **REVIEW)
    return rec, inv, q1, q2, q3


def _rows(rec, inv):
    """Every question complete, as the record's stages read once the workflow's gates are met (the hand-built record
    has no hypothesis or preregistration for Q3, so its own stages would not say so)."""
    return [{"question": b["id"], "code": b["code"], "complete": True, "workflow": "scientific@2",
             "gates": [{"gate": "reviewed", "who": "critic", "met": True, "optional": False}]}
            for b in rec.question_board(inv)]


def _scheduler(rec, inv, seats=SEATS):
    s = Scheduler(rec, inv, seats, model_for=lambda seat: None, meter=Meter(Budget(max_calls=20)))  # type: ignore[arg-type,return-value]
    issued: list[tuple[str, str, str, list]] = []
    s._issue = lambda seat, tgt, objective, done_when=None: issued.append((seat.name, tgt, objective, done_when or [])) or True  # type: ignore[method-assign]
    return s, issued


def test_the_conclusion_question_gets_one_reading_against_the_other_answers():
    rec, inv, q1, q2, q3 = _settled_record()
    rows = _rows(rec, inv)
    s, issued = _scheduler(rec, inv)
    s._assign_from_stages(rows)
    assert len(issued) == 1, issued
    seat, target, objective, done_when = issued[0]
    assert seat == "critic" and target == q3["id"] and done_when == [{"p": "reviewed"}]
    assert objective.startswith(CONSISTENCY_MARK + q3["code"])
    assert "Does the supplement change steps_k?" in objective
    assert "No outcome remains significant after correction" in objective and q2["code"] in objective
    assert q1["code"] in objective
    assert len(objective) <= OBJECTIVE_MAX
    assert "consistency_order" in [e["kind"] for e in s.res.events]
    s._assign_from_stages(rows)                                 # the next round doesn't order it again
    assert len(issued) == 1


def test_measured_questions_get_no_reading():
    rec, inv, _q1, _q2, q3 = _settled_record()
    s, issued = _scheduler(rec, inv)
    s._assign_from_stages(_rows(rec, inv))
    assert [t for _, t, _, _ in issued] == [q3["id"]]           # Q1 and Q2 ask for measurements


def test_a_resumed_run_finds_the_reading_already_ordered():
    rec, inv, _q1, _q2, q3 = _settled_record()
    rec.issue_work(author="harness", inv=inv, target=q3["id"], assignee="critic", role="reviewer",
                   objective=CONSISTENCY_MARK + q3["code"] + " with the record's other answers, ordered before the restart.",
                   done_when=[{"p": "reviewed"}])
    s, issued = _scheduler(rec, inv)
    s._assign_from_stages(_rows(rec, inv))
    assert issued == []


def test_the_reading_goes_to_a_reviewer_who_did_not_write_the_answer():
    rec, inv, _q1, _q2, q3 = _settled_record(q3_author="critic", seats=TWO_REVIEWERS, reviewer="auditor")
    s, issued = _scheduler(rec, inv, TWO_REVIEWERS)
    s._assign_from_stages(_rows(rec, inv))
    assert [(seat, t) for seat, t, _, _ in issued] == [("auditor", q3["id"])]


def test_a_record_with_one_question_has_nothing_to_read_against():
    rec = LocalRecord(None, SEATS)
    inv = rec.start("One question", MISSION, QUESTIONS[2:], files=[], reviewers=["critic"])
    q3 = _answer(rec, inv, "stats", "Q3", "The supplement reduces steps_k compared to placebo.")
    rec.review(author="critic", target=q3["id"], verdict="checked", **REVIEW)
    s, issued = _scheduler(rec, inv)
    s._assign_from_stages(_rows(rec, inv))
    assert issued == []


def test_the_reading_waits_until_a_sibling_answer_is_checked():
    rec = LocalRecord(None, SEATS)
    inv = rec.start("Does the supplement change steps_k?", MISSION, QUESTIONS, files=[], reviewers=["critic"])
    q2 = _answer(rec, inv, "analyst", "Q2", "No outcome remains significant after correction for the outcomes tested.")
    q3 = _answer(rec, inv, "stats", "Q3", "The supplement reduces steps_k compared to placebo.")
    rec.review(author="critic", target=q3["id"], verdict="checked", **REVIEW)
    rows = [{"question": rec.resolve("Q3", inv), "code": "Q3", "complete": True, "workflow": "scientific@2",
             "gates": [{"gate": "reviewed", "who": "critic", "met": True, "optional": False}]}]
    s, issued = _scheduler(rec, inv)
    s._assign_from_stages(rows)
    assert issued == []                                        # Q2's answer is still unchecked: nothing to read against
    rec.review(author="critic", target=q2["id"], verdict="checked", **REVIEW)
    s._assign_from_stages(rows)
    assert [t for _, t, _, _ in issued] == [q3["id"]]
