"""Calls the tools can take as meant (gpt-oss-20b on a BC-250, 2026-11-05: 236 of 733 calls in 8 runs came back refused).

Most of those were field shapes, not bad findings: register_run's names passed to graph_add, the number itself as a
measurement's result, a file name where a code goes, and a retry after a refused claim that repeated its own result.
Every test here also pins what stays refused: the record's checks run on whatever these tools pass on.
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


def _setup():
    seats = [Seat("analyst", "worker"), Seat("critic", "reviewer")]
    r = LocalRecord(None, seats)
    inv = r.start("Does A beat B", "Score A and B on the same items.", [("Q1", "What is A's accuracy?")])
    order = r.issue_work(author="harness", inv=inv, target=r.resolve("Q1", inv), assignee="analyst",
                         objective="Find A's accuracy on items.csv.")["order"]
    tools = {t.name: t.fn for t in worker_tools(r, seats[0], inv, order, Meter(Budget(max_calls=40)))}
    return r, inv, tools


def _result(t) -> None:
    out = t["register_run"](name="count", result_summary="Counted A's correct items.", values=VALUES, code=CODE)
    assert out.startswith("run "), out


def _file(r, inv) -> str:
    return r.create(author="harness", type="artifact", inv=inv, fields={
        "sha256": "a" * 64, "path": "data/items.csv", "size": 10, "format": "csv"})["code"]


def _claim(r, inv, code="CL1"):
    return r.get(r.resolve(code, inv))


def test_register_runs_field_names_work_on_graph_add():
    r, inv, t = _setup()
    _result(t)
    out = t["graph_add"]("claim", {"statement": SENTENCE, "scope": SCOPE, "claim_kind": "finding", "answers": "Q1"},
                         [{"rel": "derived_from", "to": "RS1"}])
    assert out.startswith("added CL1"), out
    c = _claim(r, inv)
    assert c["body"]["kind"] == "finding"
    assert "answers" not in c["body"]
    assert any(e["rel"] == "answers" and e["dst"] == r.resolve("Q1", inv) for e in c["out"])


def test_an_answers_list_and_a_kind_of_claim_are_taken_too():
    r, inv, t = _setup()
    _result(t)
    out = t["graph_add"]("claim", {"statement": SENTENCE, "scope": SCOPE, "kind": "claim", "answers": ["Q1"]},
                         [{"rel": "answers", "to": "Q1"}, {"rel": "derived_from", "to": "RS1"}])
    assert out.startswith("added CL1"), out
    assert (_claim(r, inv)["body"].get("kind") or "finding") == "finding"


def test_a_number_in_a_measurements_result_is_left_to_the_record_to_bind():
    r, inv, t = _setup()
    _result(t)
    out = t["graph_add"]("claim", {"statement": SENTENCE, "scope": SCOPE,
                                   "measurements": [{"name": "acc", "result": 0.814}, {"name": "x", "key": "acc_a"},
                                                    {"name": "y", "key": "nope", "result": "RS1"}]},
                         [{"rel": "derived_from", "to": "RS1"}, {"rel": "answers", "to": "Q1"}])
    assert out.startswith("added CL1"), out
    bound = _claim(r, inv)["body"]["measurements"]
    assert [m["key"] for m in bound] == ["acc_a"]                    # the record's own binding, read off the statement
    assert bound[0]["result"] == r.resolve("RS1", inv)


def test_a_measurement_the_record_can_read_is_kept_and_still_checked():
    r, inv, t = _setup()
    _result(t)
    good = {"name": "acc_a", "result": "RS1", "key": "acc_a", "k": 814, "n": 1000}
    out = t["graph_add"]("claim", {"statement": SENTENCE, "scope": SCOPE, "measurements": [good]},
                         [{"rel": "derived_from", "to": "RS1"}])
    assert out.startswith("added CL1"), out
    assert _claim(r, inv)["body"]["measurements"][0]["key"] == "acc_a"
    wrong = t["graph_add"]("claim", {"statement": "A is right on 900 of 1000 items.", "scope": SCOPE,
                                     "measurements": [dict(good, k=900)]},
                           [{"rel": "derived_from", "to": "RS1"}])
    assert wrong.startswith("refused"), wrong


def test_a_number_no_result_holds_stays_refused_when_its_measurement_is_dropped():
    _, _, t = _setup()
    _result(t)
    out = t["graph_add"]("claim", {"statement": "A is right on 900 of 1000 items.", "scope": SCOPE,
                                   "measurements": [{"name": "acc", "result": 900}]},
                         [{"rel": "derived_from", "to": "RS1"}])
    assert out.startswith("refused") and "900" in out, out


def test_a_claim_with_no_evidence_stays_refused_with_its_fields_tidied():
    _, _, t = _setup()
    out = t["graph_add"]("claim", {"statement": "A is not more accurate than B on the items.", "scope": SCOPE,
                                   "claim_kind": "finding", "measurements": [{"name": "p", "result": 0.08}]}, [])
    assert out.startswith("refused") and "evidence" in out, out


def test_a_claim_that_uses_a_result_derives_from_it():
    r, inv, t = _setup()
    _result(t)
    out = t["graph_add"]("claim", {"statement": SENTENCE, "scope": SCOPE}, [{"rel": "uses", "dst": "RS1"}])
    assert out.startswith("added CL1"), out
    assert any(e["rel"] == "derived_from" and e["dst"] == r.resolve("RS1", inv) for e in _claim(r, inv)["out"])


def test_a_file_path_stands_for_its_artifact():
    r, inv, t = _setup()
    a = _file(r, inv)
    out = t["register_run"](name="count", result_summary="Counted A's correct items.", values=VALUES, code=CODE,
                            uses=["items.csv"])
    assert out.startswith("run ") and "left out" not in out, out
    run = r.get(r.resolve("RUN1", inv))
    assert any(e["rel"] == "uses" and e["dst"] == r.resolve(a, inv) for e in run["out"])


def test_a_read_that_isnt_in_the_record_costs_the_line_not_the_run():
    r, inv, t = _setup()
    out = t["register_run"](name="count", result_summary="Counted A's correct items.", values=VALUES, code=CODE,
                            uses=["other.csv"])
    assert out.startswith("run ") and "left out of uses: other.csv" in out, out
    assert r.resolve("RS1", inv)


def test_an_experiment_is_found_by_its_aim_and_an_invented_name_gets_the_codes():
    r, inv, t = _setup()
    aim = "Compute the accuracy of model A on items.csv."
    add = t["graph_add"]("experiment", {"aim": aim, "protocol": "Read the file and count the correct rows of A.",
                                        "success_criteria": "An accuracy between zero and one is printed."},
                         [{"rel": "motivated_by", "to": "Q1"}])
    assert add.startswith("added X1"), add
    out = t["register_run"](name="count", result_summary="Counted A's correct items.", values=VALUES, code=CODE,
                            experiment=aim)
    assert out.startswith("run "), out
    assert any(e["rel"] == "executes" and e["dst"] == r.resolve("X1", inv) for e in r.get(r.resolve("RUN1", inv))["out"])
    other = t["register_run"](name="count", result_summary="Counted again.", values={"z": {"value": 2.5}},
                              code="print('z', 2.5)", experiment="exp_made_up")
    assert other.startswith("run ") and "no experiment 'exp_made_up'" in other, other
    bad = t["graph_link"]("exp_made_up", "tests", "Q1")
    assert bad.startswith("refused: no node 'exp_made_up'") and "Q1" in bad, bad


def test_a_file_already_in_the_record_needs_no_registering_and_new_bytes_still_register():
    r, inv, t = _setup()
    a = _file(r, inv)
    out = t["graph_add"]("artifact", {"name": "items.csv", "path": "items.csv"})
    assert out.startswith(a) and "already in the record" in out, out
    new = t["graph_add"]("artifact", {"sha256": "b" * 64, "path": "items.csv", "size": 11, "format": "csv"})
    assert new.startswith("added"), new


def test_a_retry_after_a_refused_claim_puts_the_claim_on_the_same_result():
    r, inv, t = _setup()
    first = t["register_run"](name="count", result_summary="Counted A's correct items.", values=VALUES, code=CODE,
                              claim="C1", answers="Q1", scope=SCOPE)
    assert "RS1" in first and "claim refused" in first, first
    again = t["register_run"](name="count", result_summary="Counted A's correct items.", values=VALUES, code=CODE,
                              claim=SENTENCE, answers="Q1", scope=SCOPE)
    assert "RS1" in again and "→ claim CL1" in again and "claim goes on it" in again, again
    assert not any(a.get("code") == "RS2" for a in r.search("", "result", inv, 20))


def test_a_restatement_with_no_claim_is_still_refused():
    _, _, t = _setup()
    _result(t)
    again = t["register_run"](name="count again", result_summary="Counted A's correct items.", values=VALUES, code=CODE)
    assert again.startswith("refused") and "RESULT_RESTATES" in again


def test_a_label_for_a_claim_is_told_so_and_the_run_stands():
    r, inv, t = _setup()
    out = t["register_run"](name="count", result_summary="Counted A's correct items.", values=VALUES, code=CODE,
                            claim="CL3", answers="Q1", scope=SCOPE)
    assert "RS1" in out and "the sentence itself, not a label" in out, out
    assert r.resolve("RS1", inv)


def test_graph_link_can_say_what_a_test_expects():
    r, inv, t = _setup()
    h = t["graph_add"]("hypothesis", {"statement": "Model A is right on most of the items in the file.",
                                      "predictions": ["More than half of the rows have A correct."]},
                       [{"rel": "answers", "to": "Q1"}])
    assert h.startswith("added H1"), h
    x = t["graph_add"]("experiment", {"aim": "Count how many items model A gets right in the file.",
                                      "protocol": "Read the file and count the correct rows of A.",
                                      "success_criteria": "A count of correct rows out of all rows is printed."})
    assert x.startswith("added X1"), x
    bare = t["graph_link"]("X1", "tests", "H1")
    assert bare.startswith("refused") and "expected" in bare, bare
    out = t["graph_link"]("X1", "tests", "H1", expected="More than half of the rows have A correct.")
    assert out.startswith("linked"), out
    assert any(e["rel"] == "tests" for e in r.get(r.resolve("X1", inv))["out"])


def test_the_tools_description_doesnt_carry_a_task_s_answer():
    _, _, t = _setup()
    assert "0.814" not in (t["graph_add"].__doc__ or "")


def _hypothesis(t, *links) -> str:
    return t["graph_add"]("hypothesis", {"statement": "Model A is right on most of the items in the file.",
                                         "predictions": ["More than half of the rows have A correct."]}, list(links))


def _experiment(t, h="H1") -> str:
    return t["graph_add"]("experiment", {"aim": "Count how many items model A gets right in the file.",
                                         "protocol": "Read the file and count the correct rows of A.",
                                         "success_criteria": "A count of correct rows out of all rows is printed."},
                          [{"rel": "tests", "to": h, "data": {"expected": "More than half of the rows."}}])


def test_a_hypothesis_answers_the_orders_question_unless_it_says_otherwise():
    r, inv, t = _setup()
    assert _hypothesis(t).startswith("added H1")
    q = r.resolve("Q1", inv)
    assert any(e["rel"] == "answers" and e["dst"] == q for e in r.get(r.resolve("H1", inv))["out"])


def test_a_run_executes_the_seats_one_open_experiment():
    r, inv, t = _setup()
    _hypothesis(t)
    assert _experiment(t).startswith("added X1")
    out = t["register_run"](name="count", result_summary="Counted A's correct items.", values=VALUES, code=CODE)
    assert out.startswith("run "), out
    assert any(e["rel"] == "executes" and e["dst"] == r.resolve("X1", inv) for e in r.get(r.resolve("RUN1", inv))["out"])
    again = t["register_run"](name="other", result_summary="Measured something else.", values={"z": {"value": 2.5}},
                              code="print('z', 2.5)")
    assert again.startswith("run ")
    assert not any(e["rel"] == "executes" for e in r.get(r.resolve("RUN2", inv))["out"])  # X1 has its run


def test_two_open_experiments_are_not_guessed_between():
    r, inv, t = _setup()
    _hypothesis(t)
    _experiment(t)
    t["graph_add"]("experiment", {"aim": "Count how many items model B gets right in the file.",
                                  "protocol": "Read the file and count the correct rows of B.",
                                  "success_criteria": "A count of correct rows out of all rows is printed."},
                   [{"rel": "tests", "to": "H1", "data": {"expected": "Fewer than half of the rows."}}])
    t["register_run"](name="count", result_summary="Counted A's correct items.", values=VALUES, code=CODE)
    assert not any(e["rel"] == "executes" for e in r.get(r.resolve("RUN1", inv))["out"])


def test_an_experiment_on_another_questions_hypothesis_says_so():
    r, inv, t = _setup()
    q2 = r.create(author="harness", type="question", inv=inv, fields={"text": "Is A better than B on these items?"})
    r.create(author="analyst", type="hypothesis", inv=inv, fields={
        "statement": "Model A beats model B on these items.", "predictions": ["A has the higher accuracy."]},
        links=[{"rel": "answers", "to": q2["id"]}])
    out = _experiment(t)
    assert out.startswith("added X1") and "doesn't count for it" in out, out


def test_a_uses_of_something_not_a_file_is_left_out():
    _, _, t = _setup()
    _result(t)
    out = t["register_run"](name="other", result_summary="Measured something else.", values={"z": {"value": 2.5}},
                            code="print('z', 2.5)", uses=["RS1"])
    assert out.startswith("run ") and "left out of uses: RS1" in out, out


def test_a_reviewers_claim_isnt_written_and_its_run_is():
    seats = [Seat("analyst", "worker"), Seat("critic", "reviewer")]
    r = LocalRecord(None, seats)
    inv = r.start("Does A beat B", "Score A and B on the same items.", [("Q1", "What is A's accuracy?")])
    order = r.issue_work(author="harness", inv=inv, target=r.resolve("Q1", inv), assignee="critic",
                         objective="Check A's accuracy.")["order"]
    t = {x.name: x.fn for x in worker_tools(r, seats[1], inv, order, Meter(Budget(max_calls=40)))}
    out = t["register_run"](name="recount", result_summary="Recounted A's correct items.", values=VALUES, code=CODE,
                            claim=SENTENCE, answers="Q1", scope=SCOPE)
    assert out.startswith("run ") and "RS1" in out and "reviewer's claim" in out, out
    assert not r.search("", "claim", inv, 10)


def test_fields_in_the_wrong_place_and_a_missing_scope_from_the_result():
    r, inv, t = _setup()
    _result(t)
    assert _hypothesis_with_links_in_fields(t).startswith("added H1")
    out = t["graph_add"]("claim", {"statement": SENTENCE, "name": "CL-a", "scope": "all"},
                         [{"rel": "derived_from", "to": "RS1"}])
    assert out.startswith("added CL1"), out
    assert _claim(r, inv)["body"]["scope"] == "Counted A's correct items."


def _hypothesis_with_links_in_fields(t) -> str:
    return t["graph_add"]("hypothesis", {"statement": "Model A is right on most of the items in the file.",
                                         "predictions": ["More than half of the rows have A correct."],
                                         "links": [{"rel": "answers", "to": "Q1"}]})
