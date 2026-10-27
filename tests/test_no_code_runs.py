"""A computational run that can't execute code says so, and the CLI can give it python. Through the CLI with only the
files toolkit, an optimization run's seats wrote "exact DP over capacity" as prose and a wrong optimum settled
(studies O1). `hypswarm run --python` gives the seats a python tool in --folder and re-runs their registered code."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import pytest

from hypswarm import Budget, Task, run
from hypswarm.cli import main
from hypswarm.messages import Tool
from hypswarm.providers.stub import StubModel
from hypswarm.run import NO_CODE
from hypswarm.sandbox import python_subprocess

TASK = Task(title="Load the van", mission="Pick the items worth the most under the weight limit.",
            questions=[("Q1", "What is the highest total value that fits?")], profile="optimization")


SEEN: list[str] = []


def _quiet(messages, tools):          # a model that says nothing (the run ends at once) and keeps its system prompt
    SEEN.append(messages[0].content)
    return "nothing to do"


def _run(task: Task = TASK, **kw) -> str:
    SEEN.clear()
    asyncio.run(run(task, None, StubModel(_quiet), record=None, budget=Budget(max_calls=4), **kw))
    return "\n".join(SEEN)


def test_a_computational_run_with_nothing_that_executes_code_is_told(caplog: pytest.LogCaptureFixture):
    with caplog.at_level(logging.WARNING, logger="hypswarm"):
        seen = _run()
    assert NO_CODE in seen
    assert any("nothing that executes code" in m for m in caplog.messages)


def test_with_python_and_the_instrument_nothing_is_said(tmp_path: Path, caplog: pytest.LogCaptureFixture):
    py = python_subprocess(tmp_path)
    with caplog.at_level(logging.WARNING, logger="hypswarm"):
        seen = _run(data_tools=[Tool.from_function(py, name="python")], reproducer=py, folder=tmp_path)
    assert seen and NO_CODE not in seen and not any("executes code" in m or "instrument" in m for m in caplog.messages)


def test_knowledge_needs_no_code():
    seen = _run(Task(title="Facts", mission="Answer from the sources in the folder.",
                     questions=[("Q1", "When did the bridge open?")], profile="knowledge"))
    assert seen and NO_CODE not in seen


def test_the_sandbox_runs_in_the_folder_with_a_time_limit(tmp_path: Path):
    (tmp_path / "items.csv").write_text("item,weight\ni01,3\n", encoding="utf-8")
    py = python_subprocess(tmp_path, seconds=1)
    assert py("print(open('items.csv').read().splitlines()[1])").strip() == "i01,3"
    assert py("import time; time.sleep(5)").startswith("error: no output within 1 s")


def test_cli_python_needs_a_folder(tmp_path: Path):
    t = tmp_path / "task.toml"
    t.write_text('title = "T"\nmission = "Pick the items worth the most."\n[[questions]]\ncode = "Q1"\ntext = "Which?"\n',
                 encoding="utf-8")
    with pytest.raises(SystemExit, match="give --folder"):
        main(["run", "--task", str(t), "--profile", "optimization", "--model", "m", "--python"])


def test_code_nothing_could_run_is_refused():
    """O1 through the CLI (evening): with only the files toolkit and no instrument, seats registered code and its
    "output" 14 times; code text counts as the code behind a result, and nothing had run it."""
    from hypswarm import Seat
    from hypswarm.budget import Meter
    from hypswarm.record import LocalRecord
    from hypswarm.tools import worker_tools
    r = LocalRecord(None, [Seat("solver", "worker"), Seat("verifier", "reviewer")])
    inv = r.start("Load the van", "Pick the items worth the most under the weight limit.", [("Q1", "What fits best?")])
    order = r.issue_work(author="harness", inv=inv, target=r.resolve("Q1", inv), assignee="solver",
                         objective="Find the highest total value that fits in the van.")["order"]

    def reg(runs_code: bool):
        return next(t for t in worker_tools(r, Seat("solver", "worker"), inv, order, Meter(Budget(max_calls=10)),
                                            runs_code=runs_code) if t.name == "register_run")
    out = reg(False).fn(name="dp", result_summary="Exact DP over capacity: optimum 757.", code="print('objective', 757)",
                        values={"objective": {"value": 757}})
    assert out.startswith("refused") and "wasn't run" in out
    read = reg(False).fn(name="plan", result_summary="Read PLAN.md: the plan lists 11 items.",
                         values={"n_items_listed": {"value": 11}})
    assert read.startswith("run ")
    assert reg(True).fn(name="dp", result_summary="Exact DP over capacity: optimum 656.", code="print('objective', 656)",
                        values={"objective": {"value": 656}}).startswith("run ")


def test_the_scheduler_knows_when_nothing_runs_code(tmp_path: Path):
    from hypswarm import Seat
    from hypswarm.budget import Meter
    from hypswarm.files import file_tools
    from hypswarm.record import LocalRecord
    from hypswarm.scheduler import Scheduler
    seats = [Seat("solver", "worker"), Seat("verifier", "reviewer")]
    r = LocalRecord(None, seats)
    inv = r.start("Load the van", "Pick the items worth the most under the weight limit.", [("Q1", "What fits best?")])
    files = file_tools(r, inv, tmp_path)
    mk = lambda **kw: Scheduler(r, inv, seats, model_for=lambda s: None, meter=Meter(Budget(max_calls=4)), **kw)  # type: ignore[arg-type]
    py = python_subprocess(tmp_path)
    assert not mk(data_tools=files).runs_code
    assert mk(data_tools=files, reproducer=py).runs_code
    assert mk(data_tools=[*files, Tool.from_function(py, name="python")]).runs_code
