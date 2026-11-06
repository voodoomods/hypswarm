"""The order to redo a stale answer says to write the claim again, and the guard against copies refused it: a claim on
the fixed code that still held said the same thing, so the seat was told "already answers" until the order escalated.
E1 Q2 and E3 Q3 ended right but unchecked that way (BC-250, 2026-11-06)."""
from hypswarm import Seat, Task
from hypswarm.budget import Budget, Meter
from hypswarm.record import LocalRecord
from hypswarm.tools import worker_tools
from hypswarm.world import World, seed_baseline

CODE = b"def sample(rng):\n    return rng.choices(range(30), k=3)\n"
FIXED = b"def sample(rng):\n    return rng.sample(range(30), 3)\n"
AGAIN = FIXED + b"# again\n"
ANSWER = "The fixed sample draws each winner one time."
COUNT = "import raffle\nprint('repeats', 2)"


def _run(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    (work / "raffle.py").write_bytes(CODE)
    files = {"raffle.py": CODE}
    task = Task(title="raffle", mission="Fix the raffle.", profile="software", baseline=True, files=files,
                questions=[("Q1", "Over 1,000 calls of the fixed sample, how many repeat?", "measure")])
    rec = LocalRecord(":memory:", [Seat("tester", "worker"), Seat("other", "worker"), Seat("reviewer", "reviewer")])
    inv = rec.start(task.title, task.mission, task.questions, files=files, reviewers=["reviewer"], profile="software@2")
    seed_baseline(rec, inv, work, files)
    world = World(rec, inv, work, tree=True, kept={"raffle.py": CODE})
    (work / "raffle.py").write_bytes(FIXED)
    world.sync()

    def tools(seat="tester"):
        order = rec.issue_work(author="harness", inv=inv, target=rec.resolve("Q1", inv), assignee=seat,
                               objective="Count the repeats on the fixed sample.")["order"]
        return {t.name: t.fn for t in worker_tools(rec, Seat(seat, "worker"), inv, order, Meter(Budget(max_calls=50)))}

    return work, rec, inv, world, tools


def _stale_answer(tmp_path):
    work, rec, inv, world, tools = _run(tmp_path)
    t = tools()
    out = t["register_run"](name="r", result_summary="Repeats in 1000 calls.", values={"repeats": 2}, code=COUNT,
                            answers="Q1", claim=ANSWER, scope="1000 calls")
    assert "→ claim CL1" in out, out
    (work / "raffle.py").write_bytes(AGAIN)
    world.sync()
    assert (rec.get(rec.resolve("CL1", inv))["state"]).get("stale")
    return rec, inv, t


def _claim(rec, inv, code):
    return rec.get(rec.resolve(code, inv))


def test_a_stale_answer_can_be_written_again_through_a_run(tmp_path):
    rec, inv, t = _stale_answer(tmp_path)
    out = t["register_run"](name="again", result_summary="Repeats in 1000 calls, again.", values={"repeats": 2},
                            code=COUNT + "\nprint('checked again')", answers="Q1", claim=ANSWER, scope="1000 calls")
    assert "→ claim CL2" in out, out
    assert _claim(rec, inv, "CL1")["state"]["lifecycle"] == "superseded"
    assert not _claim(rec, inv, "CL2")["state"].get("stale")


def test_a_stale_answer_can_be_written_again_with_graph_add(tmp_path):
    rec, inv, t = _stale_answer(tmp_path)
    t["register_run"](name="again", result_summary="Repeats in 1000 calls, again.", values={"repeats": 2},
                      code=COUNT + "\nprint('checked again')", answers="Q1")
    out = t["graph_add"]("claim", {"statement": ANSWER, "scope": "1000 calls"},
                         [{"rel": "answers", "to": "Q1"}, {"rel": "derived_from", "to": "RS2"}])
    assert out.startswith("added CL2") and "replaces CL1" in out, out
    assert _claim(rec, inv, "CL1")["state"]["lifecycle"] == "superseded"


def test_a_stale_answer_leaves_the_question_when_it_is_replaced(tmp_path):
    rec, inv, t = _stale_answer(tmp_path)
    t["register_run"](name="again", result_summary="Repeats in 1000 calls, again.", values={"repeats": 2},
                      code=COUNT + "\nprint('checked again')", answers="Q1", claim=ANSWER, scope="1000 calls")
    row = next(b for b in rec.question_board(inv) if b["code"] == "Q1")
    assert row["answers"] == ["CL2"], row


def test_the_seat_may_still_name_the_link_itself(tmp_path):
    rec, inv, t = _stale_answer(tmp_path)
    t["register_run"](name="again", result_summary="Repeats in 1000 calls, again.", values={"repeats": 2},
                      code=COUNT + "\nprint('checked again')", answers="Q1")
    out = t["graph_add"]("claim", {"statement": ANSWER, "scope": "1000 calls"},
                         [{"rel": "answers", "to": "Q1"}, {"rel": "derived_from", "to": "RS2"},
                          {"rel": "supersedes", "to": "CL1"}])
    assert out.startswith("added CL2"), out
    assert _claim(rec, inv, "CL1")["state"]["lifecycle"] == "superseded"


def test_a_copy_of_an_answer_still_standing_is_refused(tmp_path):
    _, _, _, _, tools = _run(tmp_path)
    t = tools()
    t["register_run"](name="r", result_summary="Repeats in 1000 calls.", values={"repeats": 2}, code=COUNT,
                      answers="Q1", claim=ANSWER, scope="1000 calls")
    out = t["graph_add"]("claim", {"statement": ANSWER, "scope": "1000 calls"},
                         [{"rel": "answers", "to": "Q1"}, {"rel": "derived_from", "to": "RS1"}])
    assert out.startswith("refused: your CL1 already answers Q1"), out


def test_a_different_answer_doesnt_take_the_stale_ones_place(tmp_path):
    rec, inv, t = _stale_answer(tmp_path)
    t["register_run"](name="again", result_summary="Repeats in 1000 calls, again.", values={"repeats": 3},
                      code="import raffle\nprint('repeats', 3)", answers="Q1", claim="Repeated draws still happen on rare occasions.",
                      scope="1000 calls")
    assert _claim(rec, inv, "CL1")["state"]["lifecycle"] == "active"
