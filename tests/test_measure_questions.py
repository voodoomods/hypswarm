"""A task question may say it asks for a measurement — (code, text, "measure") — and the record's workflow then skips
the gates that question doesn't need (hypgraph measure_skips): no diff to verify the code as it is, no preregistered
hypothesis to count rows (studies: E2, E4, S1, T1)."""
import pytest
from hypgraph.profiles import Workflow

from hypswarm import Seat, Task
from hypswarm.record import LocalRecord

needs_measure = pytest.mark.skipif(not hasattr(Workflow, "measure_skips"),
                                   reason="needs a hypgraph with measure questions (asks=measure)")


@needs_measure
def test_a_measure_question_reaches_the_record_and_skips_its_gates():
    r = LocalRecord(None, [Seat("tester", "worker"), Seat("critic", "reviewer")])
    inv = r.start("Time the dedupe.", "Measure how long dedupe takes.", [("Q1", "How long does dedupe_slow take?", "measure"),
                                                                          ("Q2", "Make dedupe faster.")],
                  profile="software@2")
    qs = {q["code"]: q for q in r.search(type="question", inv=inv)}
    assert r.get(qs["Q1"]["id"])["body"].get("asks") == "measure"
    assert "asks" not in r.get(qs["Q2"]["id"])["body"]
    g1, g2 = (r.g.stage(qs[c]["id"]) for c in ("Q1", "Q2"))
    assert g1["stage"] == "claimed" and g2["stage"] == "implemented"   # Q1 needs no diff and no suite on a new head


def test_the_preamble_says_which_questions_are_measurements():
    t = Task(title="T", mission="M", questions=[("Q1", "How long?", "measure"), ("Q2", "Why?")])
    pre = t.preamble()
    assert "Q1: How long? (a measurement" in pre and "Q2: Why?\n" in pre + "\n"


def test_the_lead_cannot_add_an_instruction_as_a_question():
    """T1: the lead added "Assign it to risk as a REVIEW of CL2 …" as a question; the run then owed it a workflow."""
    from hypswarm import Budget
    from hypswarm.budget import Meter
    from hypswarm.tools import lead_tools

    r = LocalRecord(None, [Seat("quant", "worker"), Seat("risk", "reviewer")])
    inv = r.start("Is the signal tradeable?", "Test the vendor's signal.", [("Q1", "Is there look-ahead in it?")])
    lead = Seat("lead", "lead")
    add = next(t for t in lead_tools(r, lead, inv, Meter(Budget(max_calls=10)), report_box={}, roster=[])
               if t.name == "add")
    out = add.fn(type="question", fields={"text": "CL2 is unchecked. Assign it to risk as a review of CL2."})
    assert out.startswith("refused") and "rework" in out
    assert add.fn(type="question", fields={"text": "Does the signal survive a one-day delay?"}).startswith("added")


def test_a_timing_without_its_spread_is_refused_with_the_fix():
    """E2: every timing registered bare was contradicted on re-run; the ones with a spread were confirmed."""
    from hypswarm import Budget
    from hypswarm.budget import Meter
    from hypswarm.tools import _timings_without_spread, worker_tools

    assert _timings_without_spread({"median_slow_s": {"value": 0.33}, "elapsed_ms": 12.5, "t": {"value": 3, "unit": "ms"},
                                    "ok": {"value": 0.4, "unit": "s", "spread": [0.39, 0.41]},
                                    "fast": {"value": 4e-4, "unit": "s", "rel_tol": 0.2},
                                    "n_items": {"value": 10000}, "passed": {"k": 6, "n": 6}}) == \
        ["median_slow_s", "elapsed_ms", "t"]
    r = LocalRecord(None, [Seat("tester", "worker"), Seat("critic", "reviewer")])
    inv = r.start("Time it.", "Time dedupe.", [("Q1", "How long does dedupe_slow take?")])
    order = r.issue_work(author="harness", inv=inv, target=r.resolve("Q1", inv), assignee="tester",
                         objective="Time it.")["order"]
    reg = next(t for t in worker_tools(r, Seat("tester", "worker"), inv, order, Meter(Budget(max_calls=10)))
               if t.name == "register_run")
    code = "print('median_slow_s', 0.33)"
    out = reg.fn(name="time", result_summary="Timed dedupe_slow.", values={"median_slow_s": {"value": 0.33, "unit": "s"}},
                 code=code)
    assert out.startswith("refused") and "spread" in out
    ok = reg.fn(name="time", result_summary="Timed dedupe_slow over 7 repeats.", code=code,
                values={"median_slow_s": {"value": 0.33, "unit": "s", "spread": [0.32, 0.35]}})
    assert ok.startswith("run ")
