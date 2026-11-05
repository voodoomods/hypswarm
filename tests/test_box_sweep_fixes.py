"""What the 16-challenge sweep on the BC-250 found (2026-11-05). Both code-fix challenges settled nothing: seats did what
the prompt said and registered the test command as code, which ran as Python source and was a SyntaxError on every
re-run, or registered no values, so the instrument had nothing to confirm. 60 worker orders ran out of turns, 826 of
about 1,900 calls, most of them ending on refused writes."""
import asyncio
from pathlib import Path

import pytest

from hypswarm import Budget, Seat, run
from hypswarm.budget import Meter
from hypswarm.profiles import _NOTES
from hypswarm.providers.stub import StubModel, calls_made
from hypswarm.record import LocalRecord
from hypswarm.reproduce import reproduce_result, runner_summary
from hypswarm.sandbox import as_python, python_subprocess
from hypswarm.scheduler import JUDGE
from hypswarm.tools import NOT_A_NODE, worker_tools
from hypswarm.worker import CLOSING_WORK, WRITING

from .test_alpha import TASK, make_models


@pytest.mark.parametrize("code", ["python test_x.py", "python -m pytest test_x.py", "python3 -m pytest -q test_x.py",
                                  "pytest -q test_x.py", "$ pytest test_x.py"])
def test_a_command_becomes_python_that_runs_it(code):
    out = as_python(code)
    assert out != code and "subprocess.run" in out
    compile(out, "<code>", "exec")


@pytest.mark.parametrize("code", ["print(1)", "python = 3", "import os\nprint(os.name)", "pytest", "ls -l",
                                  "python -c 'unterminated"])
def test_anything_else_is_left_alone(code):
    assert as_python(code) == code


def test_the_sandbox_runs_a_test_command(tmp_path: Path):
    (tmp_path / "test_x.py").write_text("print('2 of 3 passed')\n", encoding="utf-8")
    out = python_subprocess(tmp_path)("python test_x.py")
    assert "2 of 3 passed" in out and "exit code 0" in out


@pytest.mark.parametrize("out,want", [
    ("......  [100%]\n6 passed, 1 warning in 0.15s", {"passed": 6, "failed": 0}),
    ("FAILED test_x.py::t\n3 failed, 3 passed, 1 warning in 0.15s", {"passed": 3, "failed": 3}),
    ("PASS a\nFAIL b\n3 of 4 passed", {"passed": 3, "failed": 1}),
    ("Ran 5 tests in 0.001s\n\nOK", {"passed": 5, "failed": 0}),
    ("Ran 5 tests in 0.001s\n\nFAILED (failures=2)", {"passed": 3, "failed": 2}),
    ("2 errors in 0.1s", {"passed": 0, "failed": 2}),
])
def test_a_runners_summary_is_read(out, want):
    assert runner_summary(out) == want


def test_no_summary_and_stderr_dont_count():
    assert runner_summary("hello 3") is None
    assert runner_summary("nothing\n[stderr]\n6 passed") is None


def _setup():
    seats = [Seat("analyst", "worker"), Seat("critic", "reviewer")]
    r = LocalRecord(None, seats)
    inv = r.start("Does A beat B", "Score A and B on the same items.", [("Q1", "What is A's accuracy?")])
    order = r.issue_work(author="harness", inv=inv, target=r.resolve("Q1", inv), assignee="analyst",
                         objective="Find A's accuracy on items.csv.")["order"]
    return r, inv, {t.name: t.fn for t in worker_tools(r, seats[0], inv, order, Meter(Budget(max_calls=40)))}


def _with_run(stdout: str, *, values=None):
    r, inv, tools = _setup()
    out = tools["register_run"]("tests", "The test suite ran on the current code.", values=values or {}, code="pytest -q")
    res = r.resolve(out.split("result ")[1].split()[0], inv)
    filed = asyncio.run(reproduce_result(r, inv, res, lambda _: stdout))
    assert filed
    return r.get(r.resolve(filed["result"], inv))["body"]


def test_passing_tests_are_positive_with_no_value_registered():
    body = _with_run("6 passed in 0.1s")
    assert body["outcome"] == "positive" and body["values"] == {"passed": 6, "failed": 0}


def test_failing_tests_are_negative_with_no_value_registered():
    body = _with_run("3 failed, 3 passed in 0.1s")
    assert body["outcome"] == "negative" and body["values"]["failed"] == 3


def test_no_tests_run_is_not_a_pass():
    body = _with_run("0 passed in 0.1s")
    assert body["outcome"] == "negative"


def test_a_run_with_neither_stays_inconclusive():
    body = _with_run("hello")
    assert body["outcome"] == "inconclusive"


def test_registered_values_still_decide():
    body = _with_run("passes 6\n6 passed in 0.1s", values={"passes": {"value": 6}})
    assert body["outcome"] == "positive" and list(body["values"]) == ["passes"]


def test_the_software_note_doesnt_ask_for_a_diff_the_record_refuses():
    note = _NOTES["software@2"]
    assert note.index("watches") < note.index("graph_add")
    assert "never graph_add a diff" in note


def test_a_review_objects_to_a_claim_that_doesnt_say_the_answer():
    assert "must itself state the answer" in JUDGE


OFFERED: list[list[str]] = []
TOLD: list[bool] = []


def reader(messages, tools):
    """Runs python forever, and writes only when it is offered nothing else."""
    names = [t.name for t in tools]
    OFFERED.append(names)
    if "python" in names:
        return ("python", {"code": "print(1)"})
    TOLD.append(any(CLOSING_WORK in str(getattr(m, "content", "")) for m in messages))
    if "return_work" not in calls_made(messages):
        return ("return_work", {"note": "Ran out of turns before a claim."})
    return None


def test_a_workers_last_turns_only_write():
    OFFERED.clear()
    TOLD.clear()
    models = make_models()
    models["analyst"] = StubModel(reader, "reader")
    seats = [Seat("analyst", "worker", takes=("accuracy", "question"), max_turns=6),
             Seat("stats", "worker", takes=("significant",)), Seat("critic", "reviewer"), Seat("lead", "lead")]
    from hypswarm.messages import Tool

    def python(code: str) -> str:
        """Run python."""
        return "1"
    asyncio.run(run(TASK, seats, models, record=None, budget=Budget(max_calls=40),
                    data_tools=[Tool.from_function(python)]))
    assert OFFERED[:3] and all("python" in o for o in OFFERED[:3])          # work is allowed for the first turns
    closing = [o for o in OFFERED if "python" not in o]
    assert closing and all(set(o) <= set(WRITING) for o in closing)
    assert TOLD and all(TOLD)                                               # and the seat was told why


def test_show_says_a_file_isnt_a_node():
    _r, _inv, tools = _setup()
    out = tools["show"]("serve.py")
    assert "no node" in out and NOT_A_NODE in out


def test_a_run_named_as_support_means_its_result():
    r, inv, tools = _setup()
    out = tools["register_run"]("count", "Counted A's correct items in items.csv.", values={"acc_a": {"k": 814, "n": 1000}},
                                code="print('acc_a', 814, 'of', 1000)")
    run_code = out.split()[1]
    claim = tools["graph_add"]("claim", {"statement": "A is right on 814 of 1000 items.",
                                         "scope": "The 1000 items in items.csv, every row."},
                               links=[{"rel": "supports", "from": run_code, "why": "the count of correct items on the file"},
                                      {"rel": "answers", "to": "Q1"}])
    assert "refused" not in claim
    assert any(n["type"] == "claim" for n in r.search("", "claim", inv, 5))


def test_a_withdrawn_source_is_not_evidence():
    note = _NOTES["knowledge@2"]
    assert "retraction" in note and "withdrawn source is not evidence" in note
