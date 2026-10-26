"""The world watcher and the instruments built on it (P3): a file whose bytes changed supersedes its artifact and
makes what used it stale; the software tree is a head a commit supersedes; a page that no longer says a source's
passage makes the source stale; a run's implied ``uses``; and, end to end, a change mid-run — the instrument re-runs
both answers on the current file, the unchanged one comes back with no model call, and only the moved one is redone."""
import asyncio
import hashlib
import os
import subprocess
import sys
from pathlib import Path

from hypgraph import Graph

from hypswarm import Budget, Seat, Task, run
from hypswarm.record import HARNESS, LocalRecord
from hypswarm.tools import implied_uses
from hypswarm.world import World, passage_in

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples"))
from _common import scripted  # the examples' stage-walking scripted models


def _rec(tmp_path, profile="scientific@2", files=None):
    seats = [Seat("analyst", "worker"), Seat("critic", "reviewer"), Seat("lead", "lead")]
    rec = LocalRecord(tmp_path / "w.hypgraph", seats)
    inv = rec.start("A world that changes", "Watch the files and the pages.", [("Q1", "How many rows have a set?")],
                    files=files or {}, reviewers=["critic"], profile=profile)
    return rec, inv


def test_passage_in_tolerates_case_space_and_ellipses():
    page = "<p>The treaties were   signed on October 24, 1648, at Münster.</p>"
    assert passage_in("…signed on October 24, 1648…", page)
    assert passage_in("SIGNED ON october 24, 1648", page)
    assert not passage_in("signed on October 25, 1648", page)
    assert not passage_in("…signed… 1650…", page)


def test_a_changed_file_supersedes_its_artifact_and_stales_what_used_it(tmp_path):
    (tmp_path / "data.csv").write_text("a\n1\n0\n", encoding="utf-8")
    rec, inv = _rec(tmp_path, files={"data.csv": (tmp_path / "data.csv").read_bytes()})
    a1 = rec.search("", "artifact", inv, 5)[0]["id"]
    run_ = rec.create(author="analyst", type="run", inv=inv, fields={"kind": "agent", "name": "count", "state": "succeeded"},
                      links=[{"rel": "uses", "to": a1}])["id"]
    rs = rec.create(author="analyst", type="result", inv=inv, fields={"summary": "Counted the rows with a set.",
                    "values": {"n_a": {"k": 1, "n": 2}}}, links=[{"rel": "produced", "from": run_}])["id"]
    w = World(rec, inv, tmp_path)
    assert w.sync() == [] and not rec.get(rs)["state"].get("stale")          # nothing moved yet
    (tmp_path / "data.csv").write_text("a\n1\n1\n", encoding="utf-8")
    notes = w.sync()
    assert len(notes) == 1 and "data.csv changed on disk" in notes[0]
    assert rec.get(a1)["state"]["lifecycle"] == "superseded"
    assert "superseded" in rec.get(rs)["state"]["stale"][0]
    assert w.sync() == []                                                      # idempotent until the next change
    rec.close()


def test_the_software_tree_is_a_head_that_a_commit_supersedes(tmp_path):
    (tmp_path / "mod.py").write_text("def f(x):\n    return x + 1\n", encoding="utf-8")
    rec, inv = _rec(tmp_path, profile="software@2", files={"mod.py": (tmp_path / "mod.py").read_bytes()})
    q = rec.resolve("Q1", inv)
    w = World(rec, inv, tmp_path, tree=True)
    w.sync()
    assert rec.stage(q)["stage"] == "verified"                                 # the tree is the registered diff
    tree = [a for a in rec.search("", "artifact", inv, 10) if rec.get(a["id"])["body"].get("path") == "."]
    assert len(tree) == 1 and rec.get(tree[0]["id"])["body"]["kind"] == "diff"
    (tmp_path / "mod.py").write_text("def f(x):\n    return x + 2\n", encoding="utf-8")      # a teammate's commit
    notes = w.sync()
    assert any("new head" in n and "mod.py" in n for n in notes)
    heads = [a for a in rec.search("", "artifact", inv, 10) if rec.get(a["id"])["body"].get("path") == "."]
    assert len(heads) == 2 and rec.get(heads[0]["id"])["state"]["lifecycle"] == "superseded"
    assert rec.get(heads[1]["id"])["body"]["meta"]["files"] == ["mod.py"]
    rec.close()


def test_a_page_that_no_longer_says_it_makes_the_source_stale(tmp_path):
    rec, inv = _rec(tmp_path, profile="knowledge@2")
    page = {"text": "Harlow Reservoir: capacity is 4,200 megalitres."}
    src = rec.create(author="analyst", type="source", inv=inv, fields={"citation": "Harlow page.", "url": "http://local/harlow",
                     "passage": "capacity is 4,200 megalitres", "retrieved": "2026-10-26", "kind": "secondary"})["id"]
    w = World(rec, inv, refetch=lambda url: page["text"])
    assert w.sync() == [] and not rec.get(src)["state"].get("stale")          # fetched, still says it
    page["text"] = "Harlow Reservoir: capacity is 4,200 megalitres. Dam height 30 m."
    assert w.sync() == [] and not rec.get(src)["state"].get("stale")          # an edit elsewhere on the page
    page["text"] = "Harlow Reservoir: capacity is 4,600 megalitres (revised)."
    notes = w.sync()
    assert notes and "no longer contains its passage" in notes[0]
    assert "no longer contains its passage" in rec.get(src)["state"]["stale"][0]
    rec.close()


def test_implied_uses_names_the_files_the_code_reads(tmp_path):
    rec, inv = _rec(tmp_path, files={"data.csv": b"a\n1\n", "other.csv": b"x\n"})
    q = rec.resolve("Q1", inv)
    o = rec.issue_work(author=HARNESS, inv=inv, target=q, assignee="analyst", objective="Count the rows with a set.")
    ids = implied_uses(rec, inv, o["order"], "import csv\nrows = list(csv.DictReader(open('data.csv')))")
    paths = [rec.get(i)["body"]["path"] for i in ids]
    assert paths == ["data.csv"]                                                 # not other.csv; not a substring hit
    assert implied_uses(rec, inv, o["order"], "print('mydata.csv.bak')") == []
    rec.close()


# ── end to end: a corrected file mid-run ──────────────────────────────────────

ROWS = [(1, 0), (0, 1), (1, 1), (1, 0), (0, 0), (1, 1), (0, 1), (1, 0), (0, 0), (1, 1)]   # a: 6 of 10, b: 5 of 10
FIXED = [(a, 1 if i in (4, 8) else b) for i, (a, b) in enumerate(ROWS)]                    # b corrected: 7 of 10


def _csv(rows):
    return ("a,b\n" + "".join(f"{a},{b}\n" for a, b in rows)).encode()


def _code(col):
    return (f"import csv\nrows = list(csv.DictReader(open('data.csv')))\n"
            f"k = sum(int(r['{col}']) for r in rows)\nprint('n_{col}', k, 'of', len(rows))")


def _sandbox(folder: Path):
    def repro(code: str) -> str:
        p = subprocess.run([sys.executable, "-E", "-s", "-c", code], check=False, cwd=folder, capture_output=True, text=True,
                           timeout=60, env={"PATH": os.environ.get("PATH", ""), "SYSTEMROOT": os.environ.get("SYSTEMROOT", "")})
        return p.stdout + ("\n[stderr]\n" + p.stderr if p.stderr.strip() else "")
    return repro


def test_a_correction_mid_run_redoes_only_the_answer_that_moved(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    (work / "data.csv").write_bytes(_csv(ROWS))
    answers = {
        "Q1": {"summary": "Counted the rows with a set.", "values": {"n_a": {"k": 6, "n": 10}}, "code": _code("a"),
               "claim": "a is set on 6 of 10 rows.", "scope": "data.csv, 10 rows.", "answer": 6},
        "Q2": {"summary": "Counted the rows with b set.", "values": {"n_b": {"k": 5, "n": 10}}, "code": _code("b"),
               "claim": "b is set on 5 of 10 rows.", "scope": "data.csv, 10 rows.", "answer": 5,
               "after": {"values": {"n_b": {"k": 7, "n": 10}}, "claim": "b is set on 7 of 10 rows.", "answer": 7}},
    }
    fired = []

    def correct_after_q2(kind, payload):                     # the vendor's correction lands right after Q2 is computed
        if kind == "register_run" and "n_b" in (payload.get("values") or {}) and not fired:
            fired.append(1)
            (work / "data.csv").write_bytes(_csv(FIXED))

    task = Task(title="Counts", mission="Count rows in data.csv.", questions=[("Q1", "How many rows have a set?"),
                ("Q2", "How many rows have b set?")], files={"data.csv": _csv(ROWS)}, profile="scientific")
    seats = [Seat("analyst", "worker"), Seat("stats", "worker"), Seat("critic", "reviewer"), Seat("lead", "lead")]
    path = tmp_path / "e.hypgraph"
    res = asyncio.run(run(task, seats, scripted(answers), record=path, budget=Budget(max_calls=80), folder=work,
                          reproducer=_sandbox(work), watch=True, on_write=correct_after_q2))
    assert fired and res.stopped == "settled", res.scheduler.events[-8:]
    ev = res.scheduler.events
    assert any(e["kind"] == "world_changed" for e in ev)
    refreshed = [e for e in ev if e["kind"] == "refresh_order"]
    assert [e["question"] for e in refreshed] == ["Q2"]                        # only the answer that moved is redone
    reverified = {e["result"]: e for e in ev if e["kind"] == "reverified"}
    assert any(e["supported"] for e in reverified.values())                    # Q1 came back with no model call
    assert any(e["contradicted"] == ["n_b"] for e in reverified.values())
    assert '"Q2": 7' in res.report and '"Q1": 6' in res.report
    g = Graph(str(path))
    try:
        rows = g.stages(res.inv)
        assert all(r["complete"] for r in rows)
        assert "STALE" in g.report(res.inv)["markdown"]                       # the old Q2 claim stays, marked
        assert hashlib.sha256((work / "data.csv").read_bytes()).hexdigest() in {
            g.get(a["id"])["body"]["sha256"] for a in g.search("", "artifact", res.inv, 20)}
    finally:
        g.close()
