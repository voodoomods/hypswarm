"""A worker's claim, written under a question's order, names the question it answers.

In 815 knowledge runs on a BC-250 (gpt-oss-20b, 2026-11-11), 1,303 of 4,331 claims carried no answers link. The tool
said "added CL5" and nothing about it; the claim counted for nothing, the workflow's gate read "no claim answering Q1
cites a live source", and the next order wrote the same claim again: a tenth to a fifth of a run's calls, depending on
the challenge. The tool now refuses such a claim and gives the call to send, naming the order's question. It doesn't
attach the question itself, as it does for a hypothesis: one unlinked claim in eight was about another question.
"""
from __future__ import annotations

from hypswarm import Budget, Seat
from hypswarm.budget import Meter
from hypswarm.record import LocalRecord
from hypswarm.tools import worker_tools

CODE = "k, n = 814, 1000\nprint('acc_a', k, 'of', n, '=', k / n)\n"
VALUES = {"acc_a": {"k": 814, "n": 1000}}
SCOPE = "The 1000 items in items.csv, every row."
SENTENCE = "A is right on 814 of 1000 items."


def _setup(seat: int = 0, target: str = "Q1"):
    seats = [Seat("analyst", "worker"), Seat("critic", "reviewer")]
    r = LocalRecord(None, seats)
    inv = r.start("Does A beat B", "Score A and B on the same items.",
                  [("Q1", "What is A's accuracy?"), ("Q2", "What is B's accuracy?")])
    order = r.issue_work(author="harness", inv=inv, target=r.resolve(target, inv), assignee=seats[seat].name,
                         objective="Find A's accuracy on items.csv.")["order"]
    tools = {t.name: t.fn for t in worker_tools(r, seats[seat], inv, order, Meter(Budget(max_calls=40)))}
    return r, inv, tools


def _result(t) -> None:
    out = t["register_run"](name="count", result_summary="Counted A's correct items.", values=VALUES, code=CODE)
    assert out.startswith("run "), out


def _answers(r, inv, code="CL1") -> list[str]:
    c = r.get(r.resolve(code, inv))
    return [r.get(e["dst"])["code"] for e in c["out"] if e["rel"] == "answers"]


def test_a_claim_that_names_no_question_is_refused_and_told_its_orders_question():
    r, inv, t = _setup()
    _result(t)
    out = t["graph_add"]("claim", {"statement": SENTENCE, "scope": SCOPE}, [{"rel": "derived_from", "to": "RS1"}])
    assert out.startswith("refused: this claim names no question"), out
    assert '"links": [{"rel": "answers", "to": "Q1"}]' in out and "another question" in out, out
    assert "nothing was added" in out and "graph_link cannot do this" in out, out
    assert not r.search("", "claim", inv, 10)


def test_the_same_claim_with_the_link_is_added():
    r, inv, t = _setup()
    _result(t)
    out = t["graph_add"]("claim", {"statement": SENTENCE, "scope": SCOPE},
                         [{"rel": "answers", "to": "Q1"}, {"rel": "derived_from", "to": "RS1"}])
    assert out.startswith("added CL1"), out
    assert _answers(r, inv) == ["Q1"]


def test_the_question_given_as_a_field_counts():
    r, inv, t = _setup()
    _result(t)
    out = t["graph_add"]("claim", {"statement": SENTENCE, "scope": SCOPE, "answers": "Q1"},
                         [{"rel": "derived_from", "to": "RS1"}])
    assert out.startswith("added CL1"), out
    assert _answers(r, inv) == ["Q1"]


def test_the_seat_may_name_another_question_than_its_orders():
    r, inv, t = _setup()
    _result(t)
    out = t["graph_add"]("claim", {"statement": SENTENCE, "scope": SCOPE},
                         [{"rel": "answers", "to": "Q2"}, {"rel": "derived_from", "to": "RS1"}])
    assert out.startswith("added CL1"), out
    assert _answers(r, inv) == ["Q2"]


def test_a_claim_that_supports_a_hypothesis_needs_no_question():
    _, _, t = _setup()
    _result(t)
    assert t["graph_add"]("hypothesis", {"statement": "Model A is right on most of the items in the file.",
                                         "predictions": ["More than half of the rows have A correct."]}, []
                          ).startswith("added H1")
    out = t["graph_add"]("claim", {"statement": SENTENCE, "scope": SCOPE},
                         [{"rel": "derived_from", "to": "RS1"},
                          {"rel": "supports", "to": "H1", "why": "814 of 1000 is more than half of the rows."}])
    assert out.startswith("added CL1"), out


def test_an_order_that_is_not_on_a_question_is_left_alone():
    r, inv, t = _setup()
    _result(t)
    assert t["graph_add"]("claim", {"statement": SENTENCE, "scope": SCOPE},
                          [{"rel": "answers", "to": "Q1"}, {"rel": "derived_from", "to": "RS1"}]).startswith("added CL1")
    seats = [Seat("analyst", "worker"), Seat("critic", "reviewer")]
    order = r.issue_work(author="harness", inv=inv, target=r.resolve("CL1", inv), assignee="analyst",
                         objective="Say what CL1 leaves out.")["order"]
    t2 = {x.name: x.fn for x in worker_tools(r, seats[0], inv, order, Meter(Budget(max_calls=40)))}
    out = t2["graph_add"]("claim", {"statement": "A is right on 814 of the 1000 items, every row counted.", "scope": SCOPE},
                          [{"rel": "derived_from", "to": "RS1"}])
    assert not out.startswith("refused: this claim names no question"), out


def test_a_reviewer_is_told_what_it_was_told_before():
    _, _, t = _setup(seat=1)
    out = t["graph_add"]("claim", {"statement": SENTENCE, "scope": SCOPE}, [])
    assert out.startswith("refused: you are a reviewer"), out
