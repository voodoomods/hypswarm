"""Orders from stages (hypgraph ≥ 0.5): under an @2 profile the scheduler asks the record which stage each question
is in and issues that stage's order — the gates up to the next review as the done-when, to the seat the stage names;
a review stage goes to a reviewer on the node the previous gate produced. The question is complete when the record
says so. Under a frozen @1 profile nothing changes."""
import asyncio
import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest
from hypgraph import Graph

from hypswarm import Budget, Seat, Task, run
from hypswarm.http_record import HttpRecord

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples"))
from _common import scripted  # the examples' stage-walking scripted models


def _answers_scientific():
    return {"Q1": {"summary": "Counted A's correct items in items.csv.", "values": {"acc_a": {"k": 812, "n": 1000}},
                   "code": "print('acc_a', 812, 'of', 1000)", "claim": "A is right on 812 of 1000 items.",
                   "scope": "The 1,000 items in items.csv.", "answer": 0.812}}


def _events(res, kind):
    return [e for e in res.scheduler.events if e["kind"] == kind]


def test_stage_orders_walk_a_scientific_question_to_complete(tmp_path):
    task = Task(title="Does A beat B", mission="Count A's accuracy from items.csv.", questions=[("Q1", "What is A's accuracy?")],
                files={"items.csv": b"item,a\n1,1\n"}, profile="scientific")
    seats = [Seat("analyst", "worker", takes=("accuracy", "counts")), Seat("critic", "reviewer"), Seat("lead", "lead")]
    path = tmp_path / "s.hypgraph"
    res = asyncio.run(run(task, seats, scripted(_answers_scientific()), record=path, budget=Budget(max_calls=40)))
    assert res.stopped == "settled" and res.report_accepted
    issued = _events(res, "stage_order")
    assert issued[0]["stage"] == "conjectured" and issued[0]["seat"] == "analyst"
    assert issued[0]["gates"] == ["hypothesis_stated", "preregistered", "run_registered", "result_exists", "claim_made"]
    assert any(e["stage"] == "reviewed" and e["gates"] == ["reviewed"] and e["seat"] == "critic" for e in issued)
    g = Graph(str(path))
    try:
        assert g.get(res.inv)["body"]["profile"] == "scientific@2"
        first = g.orders(res.inv)[0]
        assert "is at stage 'conjectured' (2/8)" in g.order_text(first["id"]) and "[preregistered]" in g.order_text(first["id"])
        rows = g.stages(res.inv)
        assert rows[0]["complete"] and rows[0]["stage"] == "reviewed"
        gates = {x["gate"]: x for x in rows[0]["gates"]}
        assert gates["preregistered"]["met"] and gates["hypothesis_stated"]["evidence"] == ["H1"]
        assert "### Workflow" in g.report(res.inv)["markdown"]
    finally:
        g.close()


def test_frozen_v1_profile_keeps_the_board_path(tmp_path):
    task = Task(title="Does A beat B", mission="Count A's accuracy from items.csv.", questions=[("Q1", "What is A's accuracy?")],
                files={"items.csv": b"item,a\n1,1\n"}, profile="scientific@1")
    seats = [Seat("analyst", "worker"), Seat("critic", "reviewer"), Seat("lead", "lead")]
    path = tmp_path / "v1.hypgraph"
    res = asyncio.run(run(task, seats, scripted(_answers_scientific()), record=path, budget=Budget(max_calls=40)))
    assert res.stopped == "settled" and not _events(res, "stage_order")
    g = Graph(str(path))
    try:
        assert [p["p"] for p in g.get(res.orders[0]["id"])["body"]["done_when"]] == ["claim_made"]
        assert g.stages(res.inv)[0]["workflow"] is False
    finally:
        g.close()


def _sandbox(folder: Path):
    def repro(code: str) -> str:
        p = subprocess.run([sys.executable, "-E", "-s", "-c", code], check=False, cwd=folder, capture_output=True, text=True,
                           timeout=60, env={"PATH": os.environ.get("PATH", ""), "SYSTEMROOT": os.environ.get("SYSTEMROOT", "")})
        return p.stdout + ("\n[stderr]\n" + p.stderr if p.stderr.strip() else "")
    return repro


def test_software_stage_orders_register_the_diff_and_the_instrument_tests_the_head(tmp_path):
    src = b"def f(x):\n    return x + 1\n"
    head = hashlib.sha256(src).hexdigest()
    (tmp_path / "mod.py").write_bytes(src)
    code = "import mod\nprint('passed', int(mod.f(1) == 2), 'of', 1)\nprint('exit_code', 0)"
    answers = {"Q1": {"summary": "Ran the check on mod.py.", "values": {"passed": {"k": 1, "n": 1}, "exit_code": {"value": 0}},
                      "code": code, "outcome": "positive", "claim": "mod.f passes 1 of 1 checks.", "scope": "mod.py at head " + head[:7],
                      "answer": "yes",
                      "artifact": {"sha256": head, "path": "mod.py", "kind": "diff",
                                   "meta": {"base_sha": "0000000", "head_sha": head[:12], "files": ["mod.py"]}}}}
    task = Task(title="f adds one", mission="Verify mod.f adds one.", questions=[("Q1", "Does mod.f(1) return 2?")],
                files={"mod.py": src}, profile="software")
    seats = [Seat("tester", "worker"), Seat("reviewer", "reviewer"), Seat("lead", "lead")]
    path = tmp_path / "sw.hypgraph"
    res = asyncio.run(run(task, seats, scripted(answers), record=path, budget=Budget(max_calls=60), reproducer=_sandbox(tmp_path)))
    assert res.stopped == "settled", res.scheduler.events[-6:]
    issued = _events(res, "stage_order")
    assert issued[0]["gates"] == ["diff_registered", "tests_pass_current", "claim_made"]
    g = Graph(str(path))
    try:
        rows = g.stages(res.inv)
        gates = {x["gate"]: x for x in rows[0]["gates"]}
        assert rows[0]["complete"] and gates["diff_registered"]["evidence"] == ["A1"] and gates["tests_pass_current"]["met"]
        lab = [r for r in g.search("", "run", res.inv, 50) if g.get(r["id"])["body"].get("kind") == "lab"]
        assert lab and any(e["rel"] == "uses" for e in g.get(lab[0]["id"])["out"])     # the instrument's run uses the diff
        comp = {c["name"]: c["met"] for c in g.completion(res.inv)["criteria"]}
        assert comp["requirements_verified_current"]
    finally:
        g.close()


def test_an_unanswerable_question_settles_as_inconclusive_and_its_order_is_cancelled(tmp_path):
    answers = {"Q1": {"summary": "Read 2 of 2 pages; 0 of 2 answer it.", "values": {"pages_read": {"k": 2, "n": 2}, "answering": {"k": 0, "n": 2}},
                      "outcome": "negative", "claim_kind": "inconclusive", "claim": "No page answers it: 0 of 2 pages read mention it.",
                      "scope": "The 2 of 2 pages in the folder, read in full.", "answer": None}}
    task = Task(title="A fact", mission="Find when the dam was decommissioned, from the pages.", questions=[("Q1", "When was the dam decommissioned?")],
                files={"a.txt": b"nothing", "b.txt": b"nothing"}, profile="knowledge")
    seats = [Seat("researcher", "worker"), Seat("fact_checker", "reviewer"), Seat("lead", "lead")]
    path = tmp_path / "k.hypgraph"
    res = asyncio.run(run(task, seats, scripted(answers), record=path, budget=Budget(max_calls=40)))
    assert res.stopped == "settled"
    assert any(e["kind"] == "cancelled" and e.get("why") == "question complete" for e in res.scheduler.events)
    g = Graph(str(path))
    try:
        row = g.stages(res.inv)[0]
        assert row["complete"] and row["settled_by"] == "CL1" and "inconclusive" in row["settled_how"]
    finally:
        g.close()


def test_http_record_speaks_stages():
    assert all(hasattr(HttpRecord, m) for m in ("stages", "stage", "completion", "link"))


@pytest.mark.parametrize("name", ["scientific", "software", "trading", "knowledge", "optimization"])
def test_every_profile_name_is_its_workflow_version(name):
    from hypswarm import profiles
    p = profiles.get(name)
    assert p.id == f"{name}@2" and p.workflow is not None and p.notes


def test_a_failing_suite_is_a_confirmed_failure_that_settles_the_requirement(tmp_path):
    src = b"def f(x):\n    return x + 2\n"                         # the change is wrong: 1 of 2 checks pass
    head = hashlib.sha256(src).hexdigest()
    (tmp_path / "mod.py").write_bytes(src)
    code = "import mod\nprint('passed', int(mod.f(1) == 2) + int(mod.f(0) == 2), 'of', 2)\nprint('exit_code', 1)"
    answers = {"Q1": {"summary": "Ran the checks on mod.py.", "values": {"passed": {"k": 1, "n": 2}, "exit_code": {"value": 1}},
                      "code": code, "outcome": "negative",
                      "claim": "The change does not meet the requirement: 1 of 2 checks on mod.f pass.", "scope": "mod.py at head " + head[:7], "answer": "no",
                      "artifact": {"sha256": head, "path": "mod.py", "kind": "diff",
                                   "meta": {"base_sha": "0000000", "head_sha": head[:12], "files": ["mod.py"]}}}}
    task = Task(title="f adds one", mission="Verify mod.f adds one.", questions=[("Q1", "Does mod.f add one?")],
                files={"mod.py": src}, profile="software")
    seats = [Seat("tester", "worker"), Seat("reviewer", "reviewer"), Seat("lead", "lead")]
    path = tmp_path / "sw.hypgraph"
    res = asyncio.run(run(task, seats, scripted(answers), record=path, budget=Budget(max_calls=60), reproducer=_sandbox(tmp_path)))
    assert res.stopped == "settled", res.scheduler.events[-6:]
    g = Graph(str(path))
    try:
        labs = [r for r in g.search("", "result", res.inv, 50) if r["by"] == "instrument"]
        assert labs and g.get(labs[0]["id"])["body"]["outcome"] == "negative"     # confirmed numbers, confirmed failure
        row = g.stages(res.inv)[0]
        gates = {x["gate"]: x for x in row["gates"]}
        assert not gates["tests_pass_current"]["met"] and row["complete"] and "verified failure" in row["settled_how"]
        assert not next(c for c in g.completion(res.inv)["criteria"] if c["name"] == "requirements_verified_current")["met"]
    finally:
        g.close()
