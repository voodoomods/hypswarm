"""A review of a claim about the original has to look at the original. On E3 a reviewer read the fixed raffle.py, objected
that the code uses rng.sample, and a right cause stayed contested until the run stuck (BC-250, 2026-11-06)."""
import asyncio

import pytest

from hypswarm import Seat, Task, file_tools
from hypswarm.budget import Budget, Meter
from hypswarm.providers.stub import StubModel, tool_outputs
from hypswarm.record import LocalRecord
from hypswarm.scheduler import Scheduler, on_the_original
from hypswarm.tools import worker_tools
from hypswarm.worker import run_order
from hypswarm.world import World, seed_baseline

CODE = b"def sample(rng):\n    return rng.choices(range(30), k=3)\n"
FIXED = b"def sample(rng):\n    return rng.sample(range(30), 3)\n"
CAUSE = "What in raffle.py causes the repeated winners?"
ON_THE_FILE = "import raffle\nprint('repeats', 83)"
ON_THE_COPY = "import sys\nsys.path.insert(0, '_base')\nimport raffle\nprint('repeats', 83)"
SEATS = [Seat("tester", "worker"), Seat("reviewer", "reviewer")]
METHOD = "I read the source of sample in raffle.py."
NOTES = "It calls rng.sample, so the claim is false."


def _run(tmp_path, baseline=True, question=CAUSE):
    work = tmp_path / "work"
    work.mkdir()
    (work / "raffle.py").write_bytes(CODE)
    files = {"raffle.py": CODE}
    task = Task(title="raffle", mission="Fix the raffle.", profile="software", baseline=baseline, files=files,
                questions=[("Q1", question, "measure")])
    rec = LocalRecord(":memory:", SEATS)
    inv = rec.start(task.title, task.mission, task.questions, files=files, reviewers=["reviewer"], profile="software@2")
    if baseline:
        seed_baseline(rec, inv, work, files)
    world = World(rec, inv, work, tree=True, kept={"raffle.py": CODE} if baseline else None)
    order = rec.issue_work(author="harness", inv=inv, target=rec.resolve("Q1", inv), assignee="tester",
                           objective="Find the cause.")["order"]
    tools = {t.name: t.fn for t in worker_tools(rec, SEATS[0], inv, order, Meter(Budget(max_calls=50)))}
    code = ON_THE_COPY if baseline else ON_THE_FILE
    out = tools["register_run"](name="r", result_summary="Repeats in 1000 calls.", values={"repeats": 83}, code=code,
                                answers="Q1", claim="raffle.py draws with rng.choices, which samples with replacement.",
                                scope="The source of raffle.py and 1000 calls.")
    assert "CL1" in out, out
    (work / "raffle.py").write_bytes(FIXED)
    world.sync()
    return work, rec, inv, world


def _reviewer(rec, inv, watched=True, read=(), ran=()):
    order = rec.issue_work(author="harness", inv=inv, target=rec.resolve("CL1", inv), assignee="reviewer",
                           objective="Check CL1.")["order"]
    tools = {t.name: t.fn for t in worker_tools(rec, SEATS[1], inv, order, Meter(Budget(max_calls=50)))}
    state = tools["review"].__dict__["_state"]
    state["ran"].extend(ran)
    if watched:
        state["read"] = list(read)
    return tools


def _reviews(rec, inv):
    return [e for e in rec.get(rec.resolve("CL1", inv))["in"] if e["rel"] == "reviews"]


def test_an_objection_from_the_fixed_file_is_refused(tmp_path):
    _, rec, inv, _ = _run(tmp_path)
    out = _reviewer(rec, inv, read=["raffle.py"])["review"]("CL1", "objection", METHOD, NOTES)
    assert out.startswith("refused: Q1 asks about the original") and "_base/raffle.py" in out, out
    assert not _reviews(rec, inv)


@pytest.mark.parametrize("read, ran", [(["_base/raffle.py"], []), (["raffle.py", "./_base/raffle.py"], []),
                                       ([], [(ON_THE_COPY, "repeats 83\n")])])
def test_after_looking_at_the_original_an_objection_is_recorded(tmp_path, read, ran):
    _, rec, inv, _ = _run(tmp_path)
    out = _reviewer(rec, inv, read=read, ran=ran)["review"]("CL1", "objection", METHOD, NOTES)
    assert not out.startswith("refused"), out
    assert len(_reviews(rec, inv)) == 1


def test_a_run_on_the_fixed_file_doesnt_count_as_looking(tmp_path):
    _, rec, inv, _ = _run(tmp_path)
    out = _reviewer(rec, inv, ran=[(ON_THE_FILE, "repeats 0\n")])["review"]("CL1", "objection", METHOD, NOTES)
    assert out.startswith("refused"), out


def test_saying_the_copy_was_read_doesnt_count(tmp_path):
    _, rec, inv, _ = _run(tmp_path)
    out = _reviewer(rec, inv)["review"]("CL1", "objection", "I read _base/raffle.py in full.", NOTES)
    assert out.startswith("refused"), out


def test_a_check_needs_no_look_at_the_original(tmp_path):
    _, rec, inv, _ = _run(tmp_path)
    out = _reviewer(rec, inv)["review"]("CL1", "checked", "I read the claim against its run.", "The run shows what it says.")
    assert not out.startswith("refused"), out


def test_a_claim_about_the_fixed_code_is_judged_on_the_files(tmp_path):
    _, rec, inv, _ = _run(tmp_path, question="Over 1,000 calls of the fixed sample, how many repeat?")
    out = _reviewer(rec, inv, read=["raffle.py"])["review"]("CL1", "objection", METHOD, NOTES)
    assert not out.startswith("refused"), out


def test_without_a_kept_copy_nothing_is_refused(tmp_path):
    _, rec, inv, _ = _run(tmp_path, baseline=False)
    out = _reviewer(rec, inv, read=["raffle.py"])["review"]("CL1", "objection", METHOD, NOTES)
    assert not out.startswith("refused"), out


def test_a_seat_outside_the_worker_loop_isnt_held_to_what_it_cant_show(tmp_path):
    _, rec, inv, _ = _run(tmp_path)
    out = _reviewer(rec, inv, watched=False)["review"]("CL1", "objection", METHOD, NOTES)
    assert not out.startswith("refused"), out


def test_a_reviewers_run_on_the_working_file_is_refused(tmp_path):
    _, rec, inv, _ = _run(tmp_path)
    out = _reviewer(rec, inv)["register_run"](name="r2", result_summary="Repeats in 1000 calls.", values={"repeats": 0},
                                              code=ON_THE_FILE)
    assert out.startswith("refused: Q1 asks about the original"), out


def test_a_reviewers_run_on_the_kept_copy_stands(tmp_path):
    _, rec, inv, _ = _run(tmp_path)
    out = _reviewer(rec, inv)["register_run"](name="r2", result_summary="Repeats in 1000 calls.", values={"repeats": 83},
                                              code=ON_THE_COPY)
    assert not out.startswith("refused"), out


@pytest.mark.parametrize("name, refused", [("raffle.py", True), ("_base/raffle.py", False)])
def test_the_worker_loop_knows_what_a_seat_read(tmp_path, name, refused):
    work, rec, inv, _ = _run(tmp_path)
    order = rec.issue_work(author="harness", inv=inv, target=rec.resolve("CL1", inv), assignee="reviewer",
                           objective="Check CL1.")["order"]

    def script(messages, tools):
        done = len(tool_outputs(messages))
        if done == 0:
            return "read_file", {"name": name}
        if done == 1:
            return "review", {"node": "CL1", "verdict": "objection", "method": METHOD, "notes": NOTES}
        return "return_work", {"note": "reviewed"}

    res = asyncio.run(run_order(SEATS[1], StubModel(script), rec, inv, order, meter=Meter(Budget(max_calls=9)),
                                data_tools=file_tools(rec, inv, work)))
    read, said = (next(x["out"] for x in res.tool_log if x["tool"] == tool) for tool in ("read_file", "review"))
    assert ("choices" if "_base" in name else "rng.sample") in read, read
    assert said.startswith("refused") is refused, said
    assert len(_reviews(rec, inv)) == (0 if refused else 1)


def test_the_note_is_only_for_a_claim_about_the_original():
    assert "_base" in on_the_original("Q2", CAUSE, kept=True)
    assert on_the_original("Q3", "How many repeat on the fixed sample?", kept=True) == ""
    assert on_the_original("Q2", CAUSE, kept=False) == ""


def _scheduler(rec, inv, world):
    s = Scheduler(rec, inv, SEATS, model_for=lambda seat: None, meter=Meter(Budget(max_calls=10)))  # type: ignore[arg-type,return-value]
    s.world = world
    sent = []
    s._issue = lambda seat, target, objective, *a, **k: sent.append(objective) or True  # type: ignore[method-assign]
    return s, sent


def test_a_staged_review_order_says_so(tmp_path):
    _, rec, inv, world = _run(tmp_path)
    s, sent = _scheduler(rec, inv, world)
    first = {"gate": "reviewed", "who": "reviewer", "stage": "reviewed"}
    q = {"question": rec.resolve("Q1", inv), "code": "Q1", "index": 2, "of": 3, "profile": "software"}
    s._issue_review_on(q, first, rec.resolve("CL1", inv), "CL1", CAUSE, set())
    assert sent and "copy under _base/" in sent[0], sent


def test_a_plain_review_order_says_so(tmp_path):
    _, rec, inv, world = _run(tmp_path)
    s, sent = _scheduler(rec, inv, world)
    s._stage_rows = lambda: None  # type: ignore[method-assign]
    s._assign()
    assert any("copy under _base/" in x for x in sent), sent
