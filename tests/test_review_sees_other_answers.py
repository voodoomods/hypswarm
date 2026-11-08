"""A review order carries the checked answers on the record's other questions. On the box (rb1, 2026-11-07) the
critic checked "the supplement reduces steps_k" while "no outcome remains significant after correction" stood checked
on Q2 of the same record, and "A is more accurate once difficulty is taken into account" while "B is better on easy
items and on hard items" stood checked beside it: it recomputed the numbers, they matched, and the order it was given
named no other claim. Now it is shown them and asked to read the claim beside them."""
from hypswarm import Budget, Seat
from hypswarm.budget import Meter
from hypswarm.record import LocalRecord
from hypswarm.scheduler import OBJECTIVE_MAX, Scheduler

SEATS = [Seat("analyst", "worker"), Seat("stats", "worker"), Seat("critic", "reviewer")]
QUESTIONS = [("Q1", "Which outcomes differ between the arms at p < 0.05 without correction?", "measure"),
             ("Q2", "After correcting for the 20 outcomes tested, which differences remain significant?", "measure"),
             ("Q3", "Does the supplement change steps_k?")]


def _answer(rec, inv, author, q, statement):
    r = rec.create(author=author, type="run", inv=inv, fields={"kind": "agent", "name": "stats", "state": "succeeded"})
    rs = rec.create(author=author, type="result", inv=inv, fields={"summary": "Welch tests on the 20 outcomes.",
                    "values": {"p_steps_k": {"value": 0.0124}}}, links=[{"rel": "produced", "from": r["id"]}])
    return rec.create(author=author, type="claim", inv=inv, fields={"statement": statement, "scope": "Every participant in trial.csv, each arm compared by a Welch test per outcome."},
                      links=[{"rel": "answers", "to": rec.resolve(q, inv)}, {"rel": "derived_from", "to": rs["id"]}])


def _record():
    rec = LocalRecord(None, SEATS)
    inv = rec.start("Does the supplement change steps_k?", "PRESS.md announces a trial result; trial.csv has every participant's arm and 20 measured outcomes, so analyse it.", QUESTIONS, files=[],
                    reviewers=["critic"])
    return rec, inv


def _review_order(rec, inv, target):
    s = Scheduler(rec, inv, SEATS, model_for=lambda seat: None, meter=Meter(Budget(max_calls=10)))  # type: ignore[arg-type,return-value]
    issued: list[tuple[str, str]] = []
    s._issue = lambda seat, tgt, objective, done_when=None: issued.append((tgt, objective)) or True  # type: ignore[method-assign]
    row = next(b for b in rec.question_board(inv) if b["code"] == "Q3")
    q = {"question": row["id"], "code": "Q3", "index": 7, "of": 8, "profile": "scientific@2"}
    first = {"gate": "reviewed", "stage": "reviewed", "who": "critic", "met": False, "evidence": []}
    s._issue_review_on(q, first, target["id"], target["code"], row["text"], set())
    assert issued and issued[0][0] == target["id"]
    return issued[0][1]


def test_the_review_lists_the_checked_answers_on_the_other_questions():
    rec, inv = _record()
    q1 = _answer(rec, inv, "analyst", "Q1", "The only outcome that differs between the arms before correction is steps_k, lower on the supplement.")
    q2 = _answer(rec, inv, "analyst", "Q2", "No outcome remains significant after correction for the outcomes tested.")
    for c in (q1, q2):
        rec.review(author="critic", target=c["id"], verdict="checked", method="Recomputed every number from trial.csv.", notes="Every number holds and the method answers the question.")
    q3 = _answer(rec, inv, "stats", "Q3", "The supplement reduces steps_k compared to placebo.")
    objective = _review_order(rec, inv, q3)
    assert "Checked answers already stand on the record's other questions" in objective
    assert f"Q2 — {q2['code']}: \"No outcome remains significant after correction" in objective
    assert f"Q1 — {q1['code']}:" in objective
    assert "contradicts a checked answer is wrong, or the checked one is" in objective
    assert q3["code"] + ":" not in objective.split("Checked answers already stand")[1]   # the claim under review isn't a sibling


def test_unchecked_and_own_question_answers_are_not_listed():
    rec, inv = _record()
    unchecked = _answer(rec, inv, "analyst", "Q2", "No outcome remains significant after correction.")
    q3 = _answer(rec, inv, "stats", "Q3", "The supplement reduces steps_k compared to placebo.")
    objective = _review_order(rec, inv, q3)
    assert "Checked answers already stand" not in objective
    assert unchecked["code"] not in objective


def test_a_record_with_one_question_adds_nothing():
    rec = LocalRecord(None, SEATS)
    inv = rec.start("One question", "PRESS.md announces a trial result; trial.csv has every participant's arm and 20 measured outcomes, so analyse it.", QUESTIONS[2:], files=[], reviewers=["critic"])
    q3 = _answer(rec, inv, "stats", "Q3", "The supplement reduces steps_k compared to placebo.")
    objective = _review_order(rec, inv, q3)
    assert "Checked answers already stand" not in objective


def test_the_order_stays_within_the_record_cap_however_long_the_siblings_are():
    """T1 (re1, 2026-11-07): five long trading claims pushed every review order past the record's 2,000-character cap;
    the record refused all twelve, three answers stayed unchecked and the run ended stuck."""
    rec, inv = _record()
    long = ("The long/flat strategy on the signal was traded on the day the signal appears, with the position changed "
            "whenever the signal changed, and the resulting series of daily returns was recorded for the out-of-sample "
            "period along with the buy and hold series for the same days, costs applied at each position change. ")
    for q in ("Q1", "Q2"):
        for _ in range(3):
            c = _answer(rec, inv, "analyst", q, (long * 2).strip())
            rec.review(author="critic", target=c["id"], verdict="checked",
                       method="Recomputed every number from trial.csv.",
                       notes="Every number holds and the method answers the question.")
    q3 = _answer(rec, inv, "stats", "Q3", "The supplement reduces steps_k compared to placebo.")
    objective = _review_order(rec, inv, q3)
    assert len(objective) <= OBJECTIVE_MAX
    assert "Checked answers already stand on the record's other questions" in objective
    assert "Q1 \u2014 CL1:" in objective                       # at least the first sibling is still named
    assert objective.endswith("name the claim in your notes.")


def test_no_sibling_text_when_the_objective_has_no_room_left():
    rec, inv = _record()
    c = _answer(rec, inv, "analyst", "Q2", "No outcome remains significant after correction for the outcomes tested.")
    rec.review(author="critic", target=c["id"], verdict="checked", method="Recomputed every number from trial.csv.",
               notes="Every number holds and the method answers the question.")
    s = Scheduler(rec, inv, SEATS, model_for=lambda seat: None, meter=Meter(Budget(max_calls=10)))  # type: ignore[arg-type,return-value]
    q3 = rec.resolve("Q3", inv)
    assert s._elsewhere(q3, "CL9", room=60) == ""
    full = s._elsewhere(q3, "CL9", room=OBJECTIVE_MAX)
    assert "No outcome remains significant" in full and len(full) < OBJECTIVE_MAX
