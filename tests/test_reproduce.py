"""The instrument re-executes registered code so reviewers judge instead of recomputing; a result and its claim
are written in one call. No model recomputes a number the record can re-run."""
import asyncio
import contextlib
import io

from hypgraph import Graph

from hypswarm import Budget, Seat, Task, run
from hypswarm.providers.stub import StubModel, calls_made, tool_outputs
from hypswarm.reproduce import check_output

from .test_alpha import TASK, _target, lead_script, reviewer_script

CODE_Q1 = "k, n = 812, 1000\nprint('A correct:', k, 'of', n, '=', k / n)\n"
CODE_Q2 = "a, b = 812, 800\nprint('A', a, 'B', b, 'of 1000 each; diff', a - b)\n"


def one_call_worker(messages, tools):
    """Registers the run, its result AND the claim in one register_run call, then returns when told."""
    done = calls_made(messages)
    outs = tool_outputs(messages)
    if any("return_work now" in o for o in outs) and "return_work" not in done:
        return ("return_work", {"note": "one call did it"})
    if "register_run" not in done:
        q = _target(messages)
        if q == "Q1":
            return ("register_run", {"name": "count A", "result_summary": "Counted A's correct items in items.csv.",
                                     "values": {"acc_a": {"k": 812, "n": 1000}}, "code": CODE_Q1,
                                     "claim": "A is right on 812 of 1000 items.", "answers": "Q1",
                                     "scope": "The 1000 paired items in items.csv."})
        return ("register_run", {"name": "compare", "result_summary": "Compared A and B on the 1000 items.",
                                 "values": {"a": {"k": 812, "n": 1000}, "b": {"k": 800, "n": 1000}}, "code": CODE_Q2,
                                 "claim": "A is not significantly more accurate than B (812 of 1000 vs 800 of 1000).",
                                 "answers": "Q2", "scope": "The 1000 paired items in items.csv."})
    return None


def exec_reproducer(source: str) -> str:
    """A test sandbox: run the code in-process, capture stdout. A real host runs it where its workers run python."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        exec(source, {"__name__": "__repro__"})  # noqa: S102 — test only
    return buf.getvalue()


SEATS = [Seat("analyst", "worker", takes=("accuracy",)), Seat("stats", "worker", takes=("significant",)),
         Seat("critic", "reviewer"), Seat("lead", "lead")]


def test_one_call_result_and_claim_then_instrument_reproduces(tmp_path):
    models = {"worker": StubModel(one_call_worker, "w"), "reviewer": StubModel(reviewer_script, "r"),
              "lead": StubModel(lead_script, "l")}
    path = tmp_path / "r.hypgraph"
    res = asyncio.run(run(TASK, SEATS, models, record=path, budget=Budget(max_calls=60), reproducer=exec_reproducer))
    assert res.stopped == "settled" and res.report_accepted
    # each worker made the result and the claim in one tool call: register_run only, then return_work
    for w in res.scheduler.workers:
        if w.seat in ("analyst", "stats"):
            assert [t["tool"] for t in w.tool_log] == ["register_run", "return_work"], w.tool_log
            assert "→ claim CL" in w.tool_log[0]["out"]
    # the instrument re-ran both results, with no model call
    rep = [e for e in res.scheduler.events if e["kind"] == "reproduced"]
    assert len(rep) == 2 and all(e["ok"] for e in rep) and res.scheduler.reproductions == 2
    g = Graph(str(path))
    try:
        labs = [g.get(n["id"]) for n in g.subgraph(res.inv, types=["run"])["nodes"] if n["by"] == "instrument"]
        assert len(labs) == 2 and all(r["body"]["kind"] == "lab" for r in labs)
        assert all(any(e["rel"] == "replicates" for e in r["out"]) for r in labs)
        # the authors' results now carry 'reproduced in project' evidence, and the review order said so
        cl1 = g.get(g.resolve("CL1", res.inv))
        assert cl1["state"]["evidence"] in ("project_rerun", "new_data", "separate_implementation")
    finally:
        g.close()
    review_orders = [o for o in res.orders if o["assignee"] == "critic"]
    assert review_orders and all("re-run" in o["objective"] and "CONTRADICTED" in o["objective"] for o in review_orders)
    assert res.usage["calls"] <= 12                        # the same as the alpha task without any of this


def test_a_wrong_number_is_contradicted(tmp_path):
    def liar(messages, tools):
        done = calls_made(messages); outs = tool_outputs(messages)
        if any("return_work now" in o for o in outs) and "return_work" not in done:
            return ("return_work", {"note": "done"})
        if "register_run" not in done:
            q = _target(messages)
            return ("register_run", {"name": "count", "result_summary": f"Counted for {q}.",
                                     "values": {"acc": {"k": 900, "n": 1000}},                  # the code prints acc 812
                                     "code": "k, n = 812, 1000\nprint('acc', k, 'of', n)\n",
                                     "claim": "A is right on 900 of 1000 items.", "answers": q,
                                     "scope": "The 1000 paired items in items.csv."})
        return None
    models = {"worker": StubModel(liar, "w"), "reviewer": StubModel(reviewer_script, "r"), "lead": StubModel(lead_script, "l")}
    res = asyncio.run(run(Task(title="One question", mission="Count how often A is right.", questions=[("Q1", "What is A's accuracy?")]),
                          [Seat("analyst", "worker"), Seat("critic", "reviewer"), Seat("lead", "lead")], models,
                          record=None, budget=Budget(max_calls=40), reproducer=exec_reproducer))
    rep = [e for e in res.scheduler.events if e["kind"] == "reproduced"]
    assert len(rep) == 1 and not rep[0]["ok"] and rep[0]["contradicted"] == ["acc"]


def test_check_output_three_verdicts():
    assert check_output({"acc": {"k": 812, "n": 1000}}, "812 of 1000")["confirmed"] == ["acc"]
    assert check_output({"rate": {"value": 0.812}}, "rate = 81.2%")["ok"]
    # computed but never printed: not evidence against, and not 'ok' on its own
    c = check_output({"n_items": {"value": 1352}, "acc": {"value": 0.8328}}, "0.8328\n")
    assert c["confirmed"] == ["acc"] and c["unprinted"] == ["n_items"] and c["contradicted"] == [] and c["ok"]
    # a different number next to the value's own name: contradicted
    c = check_output({"n_items": {"value": 1352}}, "n_items: 1350\n")
    assert c["contradicted"] == ["n_items"] and not c["ok"]
    assert check_output({"rate": {"value": 0.8125}}, "rate = 0.81")["contradicted"] == ["rate"]
    assert not check_output({}, "anything")["ok"]
