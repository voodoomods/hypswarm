"""A run's call budget comes from what its questions owe. Three full-workflow questions on a flat 160 calls ran out
every time (studies T2, T3, S3, 2026-10-27), and more turns per order only spent the same 160 in fewer pieces: the
budget was the constraint. `calls_for` gives each question a base plus a share per gate its workflow asks of it."""
from __future__ import annotations

import asyncio

from hypgraph import profiles as P

from hypswarm import Task, run
from hypswarm.budget import BASE_PER_QUESTION, PER_GATE, Budget, calls_for
from hypswarm.providers.stub import StubModel

SCI = P.get("scientific@2").workflow            # 7 gates a full question owes; a measure question skips 2
TRD = P.get("trading@2").workflow


def test_a_full_question_owes_every_gate_and_a_measure_question_skips_its_share():
    full = sum(1 for st in SCI.stages if not st.optional)
    assert calls_for([("Q1", "Is A better?")], SCI) == 8 + BASE_PER_QUESTION + PER_GATE * full
    skipped = sum(1 for st in SCI.stages if not st.optional and st.gate in SCI.measure_skips)
    assert calls_for([("Q1", "How many?", "measure")], SCI) == 8 + BASE_PER_QUESTION + PER_GATE * (full - skipped)


def test_three_questions_cost_more_than_a_flat_160():
    s3 = [("Q1", "Which differ?", "measure"), ("Q2", "Which survive correction?", "measure"), ("Q3", "Does it change steps?")]
    t2 = [("Q1", "What does it return?"), ("Q2", "How many beat buy and hold?", "measure"), ("Q3", "Position or decline?")]
    assert calls_for(s3, SCI) > 160 and calls_for(t2, TRD) > 160
    assert calls_for(s3, SCI) == 8 + 3 * BASE_PER_QUESTION + PER_GATE * (5 + 5 + 7)   # 7 gates; measure skips 2


def test_no_workflow_gives_the_floor():
    assert calls_for([("Q1", "x")], None) == 60
    assert calls_for([("Q1", "x")], P.get("scientific@1").workflow) == 60


def test_run_takes_the_rule_when_no_budget_is_given(tmp_path):
    from hypgraph import Graph
    task = Task(title="Does A beat B", mission="Count A's accuracy from items.csv.", questions=[("Q1", "What is A's accuracy?", "measure")],
                profile="scientific")
    path = tmp_path / "b.hypgraph"
    r = asyncio.run(run(task, None, StubModel(lambda m, t: "nothing to do"), record=path))
    g = Graph(str(path))
    try:
        harness = next(n for n in g.search("", "run", r.inv, 5) if g.get(n["id"])["body"].get("name") == "hypswarm run")
        assert g.get(harness["id"])["body"]["config"]["budget"]["max_calls"] == calls_for(task.questions, SCI)
    finally:
        g.close()
    r2 = asyncio.run(run(task, None, StubModel(lambda m, t: "nothing to do"), record=None, budget=Budget(max_calls=12)))
    assert r2.usage["calls"] <= 12
