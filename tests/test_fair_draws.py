"""A reviewer can't call a fair draw wrong. Two or three re-runs were taken for the range of the code, and on E3 reviewers
objected to 21 of 29 reviewed counts, every one of them inside what the code gives; two runs spent their budget on it
(BC-250, 2026-11-06)."""
import asyncio
import random

import pytest

from hypswarm.reproduce import draw_band, reproduce_result

from .test_counts_and_sources import _claim_on_a_draw, _record, _review_tool, _tools


def _reviews(rec, inv, node):
    return [e for e in rec.get(rec.resolve(node, inv))["in"] if e["rel"] == "reviews"]


def _one_draw(rng):
    return sum(len({rng.randrange(30) for _ in range(3)}) < 3 for _ in range(1000))


def test_three_reruns_dont_show_the_range_of_a_count():
    rng = random.Random(1)
    inside = printed = 0
    for _ in range(300):
        reruns = [_one_draw(rng) for _ in range(3)]
        draw = _one_draw(rng)
        low, high = draw_band(min(reruns), max(reruns))
        inside += low <= draw <= high
        printed += min(reruns) <= draw <= max(reruns)
    assert inside >= 295 and printed < 200, (inside, printed)


def test_a_count_far_from_its_reruns_is_no_draw():
    low, high = draw_band(96, 107)
    assert high < 140 and low > 60


def test_a_count_with_a_wide_range_keeps_it():
    assert draw_band(72, 110) == (53, 129)


def test_numbers_that_arent_counts_keep_the_printed_width():
    assert draw_band(1.25, 1.5) == (1.0, 1.75)
    assert draw_band(-3, -1) == (-5, 1)


CAUSE = "The sampler draws with replacement, so a winner can repeat."
COUNT_IN_SCOPE = "1,000 calls of the sampler, of which 104 repeated."
COUNT_ON_THE_RESULT = "1,000 calls of the sampler on the default generator."


def _on_a_draw(rec, inv, values, sampled, scope):
    tools = _tools(rec, inv)
    tools["register_run"](name="draw", result_summary="Repeats in a sample of the sampler.", values=values,
                          code="n = 0\nprint(n)")
    run = next(e["src"] for e in rec.get(rec.resolve("RS1", inv))["in"] if e["rel"] == "produced")
    rec.create(author="instrument", type="run", inv=inv, fields={
        "kind": "lab", "name": "re-execution", "state": "succeeded", "note": "re-ran it",
        "config": {"reproduces": run, "sampled": sampled}},
        links=[{"rel": "replicates", "to": run, "data": {"differs": "same_code"}}])
    out = tools["graph_add"]("claim", {"statement": CAUSE, "scope": scope, "kind": "finding"},
                             [{"rel": "answers", "to": "Q2"}, {"rel": "supports", "from": "RS1", "why": "RS1 counted the repeats in the sample."}])
    assert "CL1" in out, out


@pytest.mark.parametrize("scope", [COUNT_IN_SCOPE, COUNT_ON_THE_RESULT])
def test_an_objection_to_a_draw_is_refused_wherever_the_count_is_written(tmp_path, scope):
    # ro1: a right cause, its count in the scope, objected to because the reviewer's own run gave 96
    _, rec, inv = _record(tmp_path)
    _on_a_draw(rec, inv, {"repeats": 104}, {"repeats": [96, 112]}, scope)
    out = _review_tool(rec, inv, "CL1")("CL1", "objection", "I ran the sampler once myself.", "I got 96, not the 104 claimed.")
    assert out.startswith("refused") and "repeats: 96 to 112" in out, out
    assert not _reviews(rec, inv, "CL1")


def test_an_objection_to_the_cause_itself_is_recorded(tmp_path):
    _, rec, inv = _record(tmp_path)
    _on_a_draw(rec, inv, {"repeats": 104}, {"repeats": [96, 112]}, COUNT_IN_SCOPE)
    out = _review_tool(rec, inv, "CL1")("CL1", "objection", "I read the source of the sampler.", "It draws without replacement.")
    assert not out.startswith("refused"), out
    assert len(_reviews(rec, inv, "CL1")) == 1


def test_a_count_far_outside_the_range_is_still_open_to_objection(tmp_path):
    _, rec, inv = _record(tmp_path)
    _on_a_draw(rec, inv, {"repeats": 300}, {"repeats": [96, 112]}, COUNT_ON_THE_RESULT)
    out = _review_tool(rec, inv, "CL1")("CL1", "objection", "I ran the sampler once myself.", "I got 96, not the 300 claimed.")
    assert not out.startswith("refused"), out


def test_only_the_value_that_varies_is_under_review(tmp_path):
    # the size of the sample happens to sit inside the band, and says nothing about the count that varies
    _, rec, inv = _record(tmp_path)
    _on_a_draw(rec, inv, {"repeats": 300, "batches": 100}, {"repeats": [96, 112]}, COUNT_ON_THE_RESULT)
    out = _review_tool(rec, inv, "CL1")("CL1", "objection", "I ran the sampler once myself.", "I got 96, not the 300 claimed.")
    assert not out.startswith("refused"), out


def _claimed(rec, inv, value, reruns):
    _tools(rec, inv)["register_run"](name="draw", result_summary="repeats in a sample", values={"repeats": value},
                                     code="n = 0\nprint(n)", answers="Q2", claim=f"One draw of the sampler gave {value} repeats.")
    out = iter(reruns)
    return asyncio.run(reproduce_result(rec, inv, rec.resolve("RS1", inv), lambda code: next(out)))


def test_a_count_two_reruns_miss_is_still_a_draw(tmp_path):
    # rd1: 104 registered, the re-run printed 97; "unprinted", so the reviewer heard nothing of a range
    _, rec, inv = _record(tmp_path)
    out = _claimed(rec, inv, 104, ["97\n", "99\n", "96\n"])
    assert out["ok"] and out["confirmed"] == ["repeats"] and not out["unprinted"]
    run = rec.get(rec.resolve(out["run"], inv))
    assert "a fair draw falls within" in run["body"]["note"]


def test_a_count_far_outside_stays_unconfirmed(tmp_path):
    _, rec, inv = _record(tmp_path)
    out = _claimed(rec, inv, 300, ["97\n", "99\n", "96\n"])
    assert out["unprinted"] == ["repeats"] and not out["ok"]


def test_the_same_objection_sent_twice_is_refused_twice(tmp_path):
    work, rec, inv = _record(tmp_path)
    _claim_on_a_draw(work, rec, inv)
    review = _review_tool(rec, inv, "CL1")
    for _ in range(2):
        out = review("CL1", "objection", "I ran the sampler myself.", "I got 106, not 100, so the claim is wrong.")
        assert out.startswith("refused") and "a fair draw" in out, out
    assert not _reviews(rec, inv, "CL1")


def test_the_refusal_gives_the_range_not_only_the_reruns(tmp_path):
    work, rec, inv = _record(tmp_path)
    _claim_on_a_draw(work, rec, inv)
    out = _review_tool(rec, inv, "CL1")("CL1", "fail", "I ran the sampler ten times.", "The spread was 96 to 112.")
    assert out.startswith("refused") and "from 73 to 135" in out, out


def test_checked_is_recorded(tmp_path):
    work, rec, inv = _record(tmp_path)
    _claim_on_a_draw(work, rec, inv)
    out = _review_tool(rec, inv, "CL1")("CL1", "checked", "I ran the sampler once myself.", "I got 106; the range covers both.")
    assert not out.startswith("refused"), out
    assert _reviews(rec, inv, "CL1")


def test_an_objection_about_something_else_is_recorded(tmp_path):
    work, rec, inv = _record(tmp_path)
    _claim_on_a_draw(work, rec, inv)
    out = _review_tool(rec, inv, "CL1")("CL1", "objection", "I read the code.", "It counts the fixed file, not the original.")
    assert not out.startswith("refused"), out
    assert _reviews(rec, inv, "CL1")


def test_an_objection_to_a_number_outside_the_range_is_recorded(tmp_path):
    _, rec, inv = _record(tmp_path)
    _claimed(rec, inv, 300, ["97\n", "99\n", "96\n"])
    run = next(e["src"] for e in rec.get(rec.resolve("RS1", inv))["in"] if e["rel"] == "produced")
    rec.create(author="instrument", type="run", inv=inv, fields={
        "kind": "lab", "name": "re-execution", "state": "succeeded", "note": "re-ran it",
        "config": {"reproduces": run, "sampled": {"repeats": [96, 99]}}},
        links=[{"rel": "replicates", "to": run, "data": {"differs": "same_code"}}])
    out = _review_tool(rec, inv, "CL1")("CL1", "objection", "I ran the sampler once myself.", "It prints about 98, never 300.")
    assert not out.startswith("refused"), out
