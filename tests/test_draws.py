"""A sampled count has to reach the reviewer as one. On E3, 9 reviewers' objections were to fresh draws of unseeded code,
and none of those claims carried the instrument's finding that the count varies: 7 rested on a result registered with no
code, 2 on code that printed the number with no name (BC-250, 2026-11-05)."""
import asyncio

from hypswarm import Seat
from hypswarm.budget import Budget, Meter
from hypswarm.messages import Tool
from hypswarm.providers.stub import StubModel, tool_outputs
from hypswarm.reproduce import printed_by, reproduce_result
from hypswarm.worker import run_order
from hypswarm.world import seed_baseline

from .test_counts_and_sources import BROKEN, TEST, _python, _record, _review_tool, _tools


def _with_calls(tools, *ran):
    next(reversed(tools.values())).__dict__["_state"]["ran"].extend(ran)
    return tools


COUNT = "n = 0\nfor _ in range(1000):\n    n += 1\nprint('repeats', 104)"


def test_the_code_comes_from_the_call_that_printed_the_values():
    assert printed_by({"repeats": 104}, [("print(1)", "1\n"), (COUNT, "repeats 104\n")]) == COUNT


def test_the_latest_call_that_printed_them_wins():
    assert printed_by({"repeats": 104}, [("first", "104\n"), ("second", "104\n"), ("third", "99\n")]) == "second"


def test_a_call_that_printed_another_number_isnt_the_code():
    assert printed_by({"repeats": 104}, [(COUNT, "repeats 99\n")]) == ""


def test_a_failed_call_isnt_the_code():
    assert printed_by({"repeats": 104}, [("boom", "Traceback (most recent call last):\n  line 104\nValueError\n")]) == ""


def test_a_value_left_unprinted_has_to_be_in_the_code():
    values = {"repeats": 104, "total": 1000}
    assert printed_by(values, [(COUNT, "repeats 104\n")]) == COUNT
    assert printed_by(values, [("print('repeats', 104)", "repeats 104\n")]) == ""


def test_values_with_no_number_take_no_code():
    assert printed_by({"note": "fine"}, [("print('fine')", "fine\n")]) == ""


def test_a_bare_result_gets_the_code_the_seat_ran(tmp_path):
    work, rec, inv = _record(tmp_path)
    tools = _with_calls(_tools(rec, inv, run_code=_python(work)), (COUNT, "repeats 104\n"))
    out = tools["register_run"](name="count", result_summary="Repeats in 1000 calls.", values={"repeats": 104})
    assert "your python call that printed these values" in out, out
    res = rec.get(rec.resolve("RS1", inv))
    run = rec.get(next(e["src"] for e in res["in"] if e["rel"] == "produced"))
    assert run["body"]["config"]["source"] == COUNT


def test_code_the_seat_gave_stands(tmp_path):
    work, rec, inv = _record(tmp_path)
    tools = _with_calls(_tools(rec, inv, run_code=_python(work)), (COUNT, "repeats 104\n"))
    out = tools["register_run"](name="count", result_summary="Repeats in 1000 calls.", values={"repeats": 104},
                                code="print('repeats', 104)")
    assert "your python call" not in out, out


def test_a_result_nothing_printed_stays_bare(tmp_path):
    work, rec, inv = _record(tmp_path)
    tools = _with_calls(_tools(rec, inv, run_code=_python(work)), (COUNT, "repeats 99\n"))
    out = tools["register_run"](name="count", result_summary="Repeats in 1000 calls.", values={"repeats": 104})
    assert "python call" not in out, out


def test_nothing_is_adopted_where_nothing_runs_code(tmp_path):
    _, rec, inv = _record(tmp_path)
    tools = _with_calls(_tools(rec, inv, runs_code=False), (COUNT, "repeats 104\n"))
    out = tools["register_run"](name="count", result_summary="Repeats in 1000 calls.", values={"repeats": 104})
    assert "python call" not in out, out


def test_adopted_code_on_the_current_files_cant_answer_about_the_original(tmp_path):
    work, rec, inv = _record(tmp_path)
    seed_baseline(rec, inv, work, {"calc.py": BROKEN, "test_calc.py": TEST})
    code = "import calc\nprint('sum', calc.add(1, 1))"
    tools = _with_calls(_tools(rec, inv, question="Q1", run_code=_python(work)), (code, "sum 2\n"))
    out = tools["register_run"](name="count", result_summary="A sum.", values={"sum": 2}, answers="Q1")
    assert out.startswith("refused:") and "_base" in out, out


def _rerun(tmp_path, printed, value=100, source="n = 0\nprint(n)"):
    _, rec, inv = _record(tmp_path)
    _tools(rec, inv)["register_run"](name="draw", result_summary="repeats in a sample", values={"repeats": value},
                                     code=source)
    out = iter(printed)
    return rec, asyncio.run(reproduce_result(rec, inv, rec.resolve("RS1", inv), lambda code: next(out))), inv


def test_a_bare_number_that_moves_is_a_draw(tmp_path):
    rec, out, inv = _rerun(tmp_path, ["92\n", "108\n", "101\n"])
    assert out["ok"] and out["confirmed"] == ["repeats"] and not out["unprinted"]
    run = rec.get(rec.resolve(out["run"], inv))
    assert run["body"]["config"]["sampled"] == {"repeats": [92.0, 108.0]}


def test_a_number_under_another_name_that_moves_is_a_draw(tmp_path):
    _, out, _ = _rerun(tmp_path, ["repeated_winners 92\n", "repeated_winners 108\n", "repeated_winners 101\n"])
    assert out["ok"] and out["confirmed"] == ["repeats"]


def test_a_steady_bare_number_says_nothing(tmp_path):
    _, out, _ = _rerun(tmp_path, ["92\n", "92\n", "92\n"])
    assert out["unprinted"] == ["repeats"] and not out["contradicted"] and not out["ok"]


def test_a_bare_number_is_never_grounds_for_a_contradiction(tmp_path):
    _, out, _ = _rerun(tmp_path, ["92\n", "108\n", "101\n"], value=4000)
    assert out["unprinted"] == ["repeats"] and not out["contradicted"]


def test_a_number_that_moves_beside_one_that_doesnt_is_a_draw(tmp_path):
    rec, out, inv = _rerun(tmp_path, ["92 of 1000\n", "108 of 1000\n", "101 of 1000\n"])
    assert out["ok"] and out["confirmed"] == ["repeats"]
    assert rec.get(rec.resolve(out["run"], inv))["body"]["config"]["sampled"] == {"repeats": [92.0, 108.0]}


FIVE = ["1000 115\n1000 97\n1000 104\n1000 100\n1000 96\n", "1000 101\n1000 118\n1000 93\n1000 105\n1000 102\n",
        "1000 99\n1000 88\n1000 105\n1000 87\n1000 115\n"]


def test_five_draws_a_run_with_the_value_among_them_are_draws(tmp_path):
    """It used to read as confirmed: the 100 was the fourth number printed, and no run but that one printed it."""
    rec, out, inv = _rerun(tmp_path, FIVE)
    assert out["ok"] and out["confirmed"] == ["repeats"]
    config = rec.get(rec.resolve(out["run"], inv))["body"]["config"]
    assert config["sampled"] == {"repeats": [87.0, 118.0]}


def test_five_draws_a_run_without_the_value_are_draws(tmp_path):
    rec, out, inv = _rerun(tmp_path, FIVE[1:] + FIVE[:1], value=103)
    assert out["ok"] and out["confirmed"] == ["repeats"]
    assert rec.get(rec.resolve(out["run"], inv))["body"]["config"]["sampled"] == {"repeats": [87.0, 118.0]}


def test_a_timing_in_the_output_cant_confirm_a_count(tmp_path):
    rec, out, inv = _rerun(tmp_path, ["5 in 0.11 s, 0.42 s\n", "5 in 0.13 s, 0.52 s\n", "5 in 0.09 s, 0.47 s\n"], value=0.12)
    assert out["unprinted"] == ["repeats"] and not out["ok"]
    assert rec.get(rec.resolve(out["run"], inv))["body"]["config"]["sampled"] == {"repeats": [0.09, 0.13]}


def test_a_steady_output_gets_one_further_run(tmp_path):
    runs = []

    def same(code):
        runs.append(code)
        return "17 23\n"
    _, rec, inv = _record(tmp_path)
    _tools(rec, inv)["register_run"](name="n", result_summary="two counts in a file", values={"a": 17, "b": 23}, code="x")
    out = asyncio.run(reproduce_result(rec, inv, rec.resolve("RS1", inv), same))
    assert out["confirmed"] == ["a", "b"] and len(runs) == 2


def test_a_value_named_in_the_output_isnt_run_again(tmp_path):
    runs = []

    def named(code):
        runs.append(code)
        return "a 17\nb 23\n"
    _, rec, inv = _record(tmp_path)
    _tools(rec, inv)["register_run"](name="n", result_summary="two counts in a file", values={"a": 17, "b": 23}, code="x")
    asyncio.run(reproduce_result(rec, inv, rec.resolve("RS1", inv), named))
    assert len(runs) == 1


def test_outputs_of_different_shapes_say_nothing(tmp_path):
    _, out, _ = _rerun(tmp_path, ["92\n", "92\n108\n", "101\n"])
    assert out["unprinted"] == ["repeats"] and not out["contradicted"]


def test_a_test_runs_output_isnt_read_for_draws(tmp_path):
    rec, out, inv = _rerun(tmp_path, ["6 passed in 0.11s\n", "6 passed in 0.13s\n", "6 passed in 0.09s\n"], value=0.1)
    assert not out.get("sampled") and "sampled" not in rec.get(rec.resolve(out["run"], inv))["body"]["config"]


def test_a_value_in_the_code_isnt_what_the_number_speaks_of(tmp_path):
    _, rec, inv = _record(tmp_path)
    _tools(rec, inv)["register_run"](name="draw", result_summary="repeats in a sample", code="print(range(1000), 'x')",
                                     values={"repeats": 100, "total": 1000})
    out = iter(["92\n", "108\n", "101\n"])
    res = asyncio.run(reproduce_result(rec, inv, rec.resolve("RS1", inv), lambda code: next(out)))
    assert res["confirmed"].count("repeats") == 1 and "total" in res["unprinted"]


def test_a_seats_call_reaches_the_reviewer_as_a_draw(tmp_path):
    """The whole path: the seat runs python and registers the number with no code, the instrument re-runs what it ran,
    and an objection to a different count comes back to the reviewer."""
    _, rec, inv = _record(tmp_path)
    order = rec.issue_work(author="harness", inv=inv, target=rec.resolve("Q2", inv), assignee="tester",
                           objective="Count the repeats.")["order"]
    code = "print('repeats', 100)"

    def python(code: str) -> str:
        """Run python."""
        return "repeats 100\n"

    def script(messages, tools):
        done = len(tool_outputs(messages))
        if done == 0:
            return "python", {"code": code}
        if done == 1:
            return "register_run", {"name": "count", "result_summary": "Repeats in 1000 calls.", "values": {"repeats": 100},
                                    "answers": "Q2", "claim": "The sampler gave 100 repeats in one draw of 1000 calls."}
        return "return_work", {"note": "counted"}

    meter = Meter(Budget(max_calls=20))
    asyncio.run(run_order(Seat("tester", "worker"), StubModel(script), rec, inv, order, meter=meter,
                          data_tools=[Tool.from_function(python)]))
    assert rec.get(rec.resolve("CL1", inv))
    printed = iter(["repeats 92\n", "repeats 108\n", "repeats 101\n"])
    out = asyncio.run(reproduce_result(rec, inv, rec.resolve("RS1", inv), lambda c: next(printed)))
    assert out["ok"]
    said = _review_tool(rec, inv, "CL1")("CL1", "objection", "I ran the sampler once myself.", "I got 88, not 100.")
    assert said.startswith("refused") and "repeats: 92 to 108" in said, said
