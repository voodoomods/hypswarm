"""Task(baseline=True): the files as they were at the start stay readable and live, while the working file's new
bytes become their own artifact when a seat edits it (studies E1 Q1, stuck in 2 of 2 runs because the original's
artifact had been superseded and the tester's copy of it was refused as unregistered)."""
from pathlib import Path

from hypswarm import Seat, Task
from hypswarm.files import file_tools, verify
from hypswarm.record import LocalRecord
from hypswarm.world import BASELINE_DIR, World, seed_baseline

CODE = b"def compare(a, b):\n    return (a > b) - (a < b)\n"
TEST = b"from semver import compare\n\ndef test_minor():\n    assert compare('1.10', '1.9') > 0\n"
FIXED = CODE.replace(b"(a > b) - (a < b)", b"compare_versions(a, b)")


def _run(tmp_path: Path):
    work = tmp_path / "work"
    work.mkdir()
    (work / "semver.py").write_bytes(CODE)
    (work / "test_semver.py").write_bytes(TEST)
    files = {"semver.py": CODE, "test_semver.py": TEST}
    task = Task(title="semver", mission="Fix the tests.", profile="software", baseline=True, files=files,
                questions=[("Q1", "Which tests fail on the original semver.py?", "measure"),
                           ("Q2", "Do all tests pass on the changed semver.py?")])
    rec = LocalRecord(":memory:", [Seat("tester", "worker"), Seat("reviewer", "reviewer")])
    inv = rec.start(task.title, task.mission, task.questions, files=files, reviewers=["reviewer"],
                    profile="software@2")
    return work, task, rec, inv


def _artifacts(rec, inv):
    return {rec.get(a["id"])["code"]: rec.get(a["id"]) for a in rec.search("", "artifact", inv, 50)}


def test_the_preamble_says_where_the_originals_are():
    t = Task(title="t", mission="m", questions=[("Q1", "q")], files={"a.py": b"x"}, baseline=True)
    assert "_base/" in t.preamble() and "never change" in t.preamble()
    assert "_base/" not in Task(title="t", mission="m", questions=[("Q1", "q")], files={"a.py": b"x"}).preamble()


def test_the_original_stays_live_and_readable_after_a_seat_edits_the_file(tmp_path):
    work, task, rec, inv = _run(tmp_path)
    assert seed_baseline(rec, inv, work, task.files) == ["A1", "A2"]      # the task's own artifacts, marked
    assert (work / BASELINE_DIR / "semver.py").read_bytes() == CODE
    arts = _artifacts(rec, inv)
    assert arts["A1"]["body"]["meta"]["baseline"] == "_base/semver.py" and arts["A1"]["body"]["path"] == "semver.py"
    (work / "semver.py").write_bytes(FIXED)
    world = World(rec, inv, work, tree=True)
    notes = world.sync()
    assert any("original stays at _base/semver.py" in n for n in notes)
    arts = _artifacts(rec, inv)
    assert (arts["A1"].get("state") or {}).get("lifecycle", "active") == "active"      # not superseded
    new = [a for a in arts.values() if a["body"].get("path") == "semver.py" and a["code"] != "A1"]
    assert len(new) == 1 and new[0]["body"]["sha256"] != arts["A1"]["body"]["sha256"]
    assert verify(rec, inv, CODE)["status"] == "live" and verify(rec, inv, FIXED)["status"] == "live"
    tools = {t.name: t for t in file_tools(rec, inv, work)}
    assert tools["read_file"].fn("_base/semver.py") == CODE.decode()
    assert tools["read_file"].fn("semver.py") == FIXED.decode()
    # a second sync is quiet, and a second edit supersedes the working file's own artifact, never the original
    assert world.sync() == []
    (work / "semver.py").write_bytes(FIXED + b"# again\n")
    world.sync()
    arts = _artifacts(rec, inv)
    assert (arts["A1"].get("state") or {}).get("lifecycle", "active") == "active"
    assert (arts[new[0]["code"]].get("state") or {}).get("lifecycle") == "superseded"


def _register(rec, inv):
    from hypswarm.budget import Budget, Meter
    from hypswarm.tools import worker_tools
    order = rec.issue_work(author="harness", inv=inv, target=rec.resolve("Q1", inv), assignee="tester",
                           objective="Find which tests fail.")["order"]
    return {t.name: t.fn for t in worker_tools(rec, Seat("tester", "worker"), inv, order,
                                               Meter(Budget(max_calls=50)))}["register_run"]


def test_a_run_for_the_original_has_to_run_the_original(tmp_path):
    work, task, rec, inv = _run(tmp_path)
    seed_baseline(rec, inv, work, task.files)
    reg = _register(rec, inv)
    current = "import semver\nprint('failed', 3)"
    out = reg(name="r", result_summary="Three tests failed on the file.", values={"failed": 3}, code=current, answers="Q1")
    assert out.startswith("refused: Q1 asks about the original") and "_base/semver.py" in out
    # the order's own question counts when the seat names none
    assert reg(name="r", result_summary="Three tests failed on the file.", values={"failed": 3}, code=current).startswith("refused: Q1")
    kept = "import sys\nsys.path.insert(0, '_base')\nimport semver\nprint('failed', 3)"
    assert not reg(name="r", result_summary="Three tests failed on the file.", values={"failed": 3}, code=kept, answers="Q1").startswith("refused")


def test_a_question_about_the_current_code_runs_the_current_code(tmp_path):
    work, task, rec, inv = _run(tmp_path)
    seed_baseline(rec, inv, work, task.files)
    out = _register(rec, inv)(name="r", result_summary="Three tests passed on the file.", values={"passed": 3},
                              code="import semver\nprint('passed', 3)", answers="Q2")
    assert not out.startswith("refused")


def test_original_in_a_question_about_something_else_refuses_nothing(tmp_path):
    work, task, rec, inv = _run(tmp_path)
    seed_baseline(rec, inv, work, task.files)
    out = _register(rec, inv)(name="r", result_summary="A count of three in the file.", values={"n": 3}, code="print('n', 3)", answers="Q1")
    assert not out.startswith("refused")


def test_no_kept_files_no_refusal(tmp_path):
    _work, _task, rec, inv = _run(tmp_path)
    out = _register(rec, inv)(name="r", result_summary="Three tests failed on the file.", values={"failed": 3},
                              code="import semver\nprint('failed', 3)", answers="Q1")
    assert not out.startswith("refused")


def test_a_bare_pytest_finds_one_copy_of_each_test(tmp_path):
    import subprocess
    import sys
    _, _, rec, inv = _run(tmp_path)
    w = tmp_path / "w"
    w.mkdir()
    (w / "test_one.py").write_text("def test_one():\n    assert True\n", encoding="utf-8")
    seed_baseline(rec, inv, w, {"test_one.py": b"def test_one():\n    assert False\n"})

    def pytest(*args):
        return subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *args], cwd=w,
                              capture_output=True, text=True, check=False).stdout
    assert "1 passed" in pytest()
    assert "1 failed" in pytest("_base/test_one.py")


def test_a_kept_original_that_was_changed_is_put_back(tmp_path):
    work, task, rec, inv = _run(tmp_path)
    seed_baseline(rec, inv, work, task.files)
    world = World(rec, inv, work, tree=True, kept=task.files)
    assert world.sync() == []
    (work / BASELINE_DIR / "semver.py").write_bytes(b"def compare(a, b):\nreturn 0\n")
    notes = world.sync()
    assert (work / BASELINE_DIR / "semver.py").read_bytes() == CODE
    assert any("_base/semver.py had been changed" in n and "measure it again" in n for n in notes)
    assert world.sync() == []


def test_a_kept_original_that_was_deleted_is_put_back(tmp_path):
    work, task, rec, inv = _run(tmp_path)
    seed_baseline(rec, inv, work, task.files)
    world = World(rec, inv, work, kept=task.files)
    (work / BASELINE_DIR / "test_semver.py").unlink()
    assert any("_base/test_semver.py" in n for n in world.sync())
    assert (work / BASELINE_DIR / "test_semver.py").read_bytes() == TEST


def test_a_run_hands_the_watcher_its_originals(tmp_path):
    import asyncio

    from hypswarm import Budget, run
    from hypswarm.providers.stub import StubModel

    work = tmp_path / "work"
    work.mkdir()
    (work / "semver.py").write_bytes(CODE)
    task = Task(title="semver", mission="Fix the failing tests in the folder.", profile="software", files={"semver.py": CODE},
                questions=[("Q1", "Which tests fail on the original semver.py?", "measure")])

    damaged = []

    def script(messages, tools):
        if not damaged:
            damaged.append(True)
            (work / BASELINE_DIR / "semver.py").write_bytes(b"broken\n")

    seats = [Seat("lead", "lead"), Seat("tester", "worker"), Seat("reviewer", "reviewer")]
    asyncio.run(run(task, seats, StubModel(script), budget=Budget(max_calls=3), folder=str(work),
                    record=str(tmp_path / "r.hypgraph")))
    assert damaged and (work / BASELINE_DIR / "semver.py").read_bytes() == CODE


def _software_run(tmp_path, folder, **kw):
    import asyncio

    from hypswarm import Budget, run
    from hypswarm.providers.stub import StubModel
    task = Task(title="semver", mission="Fix the failing tests in the folder.", profile="software", files={"semver.py": CODE},
                questions=[("Q1", "Which tests fail on the original semver.py?", "measure")], **kw)
    seats = [Seat("lead", "lead"), Seat("tester", "worker"), Seat("reviewer", "reviewer")]
    asyncio.run(run(task, seats, StubModel(lambda m, t: None), budget=Budget(max_calls=1), folder=folder, record=str(tmp_path / "r.hypgraph")))


def test_a_software_run_in_a_folder_keeps_the_original_unasked(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    (work / "semver.py").write_bytes(CODE)
    _software_run(tmp_path, str(work))
    assert (work / "_base" / "semver.py").read_bytes() == CODE


def test_a_task_can_say_no(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    (work / "semver.py").write_bytes(CODE)
    _software_run(tmp_path, str(work), baseline=False)
    assert not (work / "_base").exists()
