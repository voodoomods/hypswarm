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
