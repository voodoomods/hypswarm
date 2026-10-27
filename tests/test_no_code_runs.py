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
