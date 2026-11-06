"""A cause is a fact about the code that had the fault. E3's Q2 ("What in raffle.py causes the repeated winners?") says
no "original", so seats measured it on the working file, the fix made that stale, and the refresh order said to
recompute from the files as they are now. The fixed code has no fault to explain, so the right answer was replaced by a
description of the fix (BC-250, 2026-11-05)."""
import pytest

from hypswarm import Seat, Task
from hypswarm.budget import Budget, Meter
from hypswarm.record import LocalRecord
from hypswarm.scheduler import refresh_objective
from hypswarm.tools import worker_tools
from hypswarm.world import World, about_the_original, seed_baseline

CODE = b"def sample(rng):\n    return rng.choices(range(30), k=3)\n"
FIXED = b"def sample(rng):\n    return rng.sample(range(30), 3)\n"
CAUSE = "What in raffle.py causes the repeated winners?"
ON_THE_FILE = "import raffle\nprint('repeats', 83)"
ON_THE_ORIGINAL = "import sys\nsys.path.insert(0, '_base')\nimport raffle\nprint('repeats', 83)"


def _run(tmp_path, baseline=True):
    work = tmp_path / "work"
    work.mkdir()
    (work / "raffle.py").write_bytes(CODE)
    files = {"raffle.py": CODE}
    task = Task(title="raffle", mission="Fix the raffle.", profile="software", baseline=baseline, files=files,
                questions=[("Q1", CAUSE, "measure"),
                           ("Q2", "Over 1,000 calls of the fixed sample, how many repeat?")])
    rec = LocalRecord(":memory:", [Seat("tester", "worker"), Seat("reviewer", "reviewer")])
    inv = rec.start(task.title, task.mission, task.questions, files=files, reviewers=["reviewer"], profile="software@2")
    if baseline:
        seed_baseline(rec, inv, work, files)
    order = rec.issue_work(author="harness", inv=inv, target=rec.resolve("Q1", inv), assignee="tester",
                           objective="Find what causes the repeats.")["order"]
    tools = {t.name: t.fn for t in worker_tools(rec, Seat("tester", "worker"), inv, order, Meter(Budget(max_calls=50)))}
    return work, rec, inv, tools


@pytest.mark.parametrize("question, about", [
    (CAUSE, True),
    ("Which tests in test_semver.py fail on the original semver.py, and what causes each failure?", True),
    ("Why does test_x fail?", True),
    ("What is the root cause of the crash?", True),
    ("What caused the outage?", True),
    ("Which tests fail on the unfixed file?", True),
    ("Over 1,000 calls of the fixed sample, how many repeat?", False),
    ("Why does the fixed parser reject it?", False),
    ("Do all tests pass on the changed semver.py?", False),
    ("What does this do because of the config?", False),
])
def test_what_counts_as_a_question_about_the_original(question, about):
    assert about_the_original(question) is about


def test_a_cause_measured_on_the_working_file_is_refused(tmp_path):
    _, _, _, tools = _run(tmp_path)
    out = tools["register_run"](name="r", result_summary="Repeats in 1000 calls.", values={"repeats": 83},
                                code=ON_THE_FILE, answers="Q1")
    assert out.startswith("refused: Q1 asks about the original") and "_base/raffle.py" in out, out


def test_a_cause_measured_on_the_kept_copy_stands(tmp_path):
    _, _, _, tools = _run(tmp_path)
    out = tools["register_run"](name="r", result_summary="Repeats in 1000 calls.", values={"repeats": 83},
                                code=ON_THE_ORIGINAL, answers="Q1")
    assert not out.startswith("refused"), out


def test_a_claim_on_a_cause_cant_rest_on_the_working_file(tmp_path):
    _, _, _, tools = _run(tmp_path)
    tools["register_run"](name="r", result_summary="Repeats in 1000 calls.", values={"repeats": 83}, code=ON_THE_FILE,
                          answers="Q2")
    out = tools["graph_add"]("claim", {"statement": "raffle.py uses rng.choices, which draws with replacement.",
                                       "scope": "1000 calls"},
                             [{"rel": "answers", "to": "Q1"}, {"rel": "derived_from", "to": "RS1"}])
    assert out.startswith("refused: RS1 came from the current files"), out


def test_a_cause_measured_on_the_kept_copy_outlives_the_fix(tmp_path):
    work, rec, inv, tools = _run(tmp_path)
    tools["register_run"](name="r", result_summary="Repeats in 1000 calls.", values={"repeats": 83},
                          code=ON_THE_ORIGINAL, answers="Q1",
                          claim="raffle.py draws with rng.choices, which samples with replacement.")
    world = World(rec, inv, work, tree=True, kept={"raffle.py": CODE})
    world.sync()
    (work / "raffle.py").write_bytes(FIXED)
    world.sync()
    (work / "raffle.py").write_bytes(FIXED + b"# again\n")
    world.sync()
    assert not (rec.get(rec.resolve("CL1", inv)).get("state") or {}).get("stale")
    run = rec.get(rec.resolve("RUN1", inv))
    assert [rec.get(e["dst"])["code"] for e in run["out"] if e["rel"] == "uses"] == ["A1"]


@pytest.mark.parametrize("code", ["from _base.raffle import sample\nprint('repeats', 83)",
                                  "import sys\nsys.path.insert(0, '_base')\nimport raffle\nprint('repeats', 83)",
                                  "print('repeats', 83, open('_base/raffle.py').read()[:0])"])
def test_a_run_on_the_kept_copy_used_it_however_it_names_it(tmp_path, code):
    _, rec, inv, tools = _run(tmp_path)
    tools["register_run"](name="r", result_summary="Repeats in 1000 calls.", values={"repeats": 83}, code=code,
                          answers="Q1")
    run = rec.get(rec.resolve("RUN1", inv))
    assert [rec.get(e["dst"])["code"] for e in run["out"] if e["rel"] == "uses"] == ["A1"]


def test_without_a_kept_copy_nothing_is_refused(tmp_path):
    _, _, _, tools = _run(tmp_path, baseline=False)
    out = tools["register_run"](name="r", result_summary="Repeats in 1000 calls.", values={"repeats": 83},
                                code=ON_THE_FILE, answers="Q1")
    assert not out.startswith("refused"), out


def test_a_refresh_of_a_cause_goes_to_the_kept_copy():
    text = refresh_objective("Q2", "CL2", "diff A3 is superseded", CAUSE, kept=True)
    assert "_base" in text and "as they are now" not in text and "CL2" in text and "A3" in text


def test_a_refresh_of_the_current_code_stays_on_the_current_files():
    text = refresh_objective("Q3", "CL4", "diff A3 is superseded", "How many repeat on the fixed sample?", kept=True)
    assert "as they are now" in text and "_base" not in text


def test_with_no_kept_copy_a_refresh_stays_on_the_current_files():
    assert "_base" not in refresh_objective("Q2", "CL2", "file A1 changed", CAUSE, kept=False)


def test_the_preamble_says_a_cause_comes_from_the_kept_copy():
    t = Task(title="t", mission="m", questions=[("Q1", "q")], files={"a.py": b"x"}, baseline=True)
    assert "what caused a fault" in t.preamble()
