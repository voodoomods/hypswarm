"""Re-verification per value: when one value of a stale result moved, a claim whose own values all reproduced on the
current files comes back (a lab result of just those values supports it); a claim resting on the moved value, on a
number it can't trace to a value, or on another result that is still stale stays stale for a worker. Found in the
change suite: an analyst counted A and B in one run, the vendor fixed B's labels, and the claim about A's count went
stale with it — 6 of the 11 redos of untouched questions were change-driven."""
import asyncio
import os
import subprocess
import sys
from pathlib import Path

from hypswarm import Seat
from hypswarm.record import LocalRecord
from hypswarm.reproduce import claim_rests_on, reproduce_result
from hypswarm.world import World

CODE = ("import csv\nrows = list(csv.DictReader(open('data.csv')))\n"
        "print('a_correct', sum(int(r['a']) for r in rows))\nprint('b_correct', sum(int(r['b']) for r in rows))")


def _sandbox(folder: Path):
    def repro(code: str) -> str:
        p = subprocess.run([sys.executable, "-E", "-s", "-c", code], check=False, cwd=folder, capture_output=True,
                           text=True, timeout=60,
                           env={"PATH": os.environ.get("PATH", ""), "SYSTEMROOT": os.environ.get("SYSTEMROOT", "")})
        return p.stdout
    return repro


def _csv(rows):
    return ("a,b\n" + "".join(f"{a},{b}\n" for a, b in rows)).encode()


def _setup(tmp_path):
    (tmp_path / "data.csv").write_bytes(_csv([(1, 0), (1, 1), (0, 0), (1, 0)]))      # a = 3, b = 1
    seats = [Seat("analyst", "worker"), Seat("critic", "reviewer"), Seat("lead", "lead")]
    rec = LocalRecord(tmp_path / "w.hypgraph", seats)
    inv = rec.start("Does A beat B?", "Count each model's correct items.",
                    [("Q1", "How many items is A right on?"), ("Q2", "How many items is B right on?")],
                    files={"data.csv": (tmp_path / "data.csv").read_bytes()}, reviewers=["critic"],
                    profile="scientific@2")
    a1 = rec.search("", "artifact", inv, 5)[0]["id"]
    run_ = rec.create(author="analyst", type="run", inv=inv, links=[{"rel": "uses", "to": a1}],
                      fields={"kind": "agent", "name": "count both", "state": "succeeded",
                              "config": {"source": CODE, "language": "python"}})["id"]
    rs = rec.create(author="analyst", type="result", inv=inv, fields={"summary": "Counted both models' correct items.",
                    "values": {"a_correct": {"value": 3}, "b_correct": {"value": 1}}},
                    links=[{"rel": "produced", "from": run_}])
    claims = {}
    for q, key, n in (("Q1", "a_correct", 3), ("Q2", "b_correct", 1)):
        claims[q] = rec.create(author="analyst", type="claim", inv=inv, fields={
            "statement": f"The model is right on {n} items of data.csv." if n > 1 else "The model is right on one item.",
            "scope": "data.csv as registered.",
            "measurements": [{"name": key, "key": key, "result": rs["id"], "value": n}]},
            links=[{"rel": "answers", "to": rec.resolve(q, inv)}, {"rel": "derived_from", "to": rs["id"]}])["id"]
    return rec, inv, rs, claims


def test_the_claim_whose_value_reproduced_comes_back_and_the_other_stays_stale(tmp_path):
    rec, inv, rs, claims = _setup(tmp_path)
    (tmp_path / "data.csv").write_bytes(_csv([(1, 0), (1, 1), (0, 1), (1, 1)]))      # the vendor fixes B: b = 3
    World(rec, inv, tmp_path).sync()
    assert rec.get(claims["Q1"])["state"].get("stale") and rec.get(claims["Q2"])["state"].get("stale")
    out = asyncio.run(reproduce_result(rec, inv, rs["id"], _sandbox(tmp_path), support_claims=True))
    assert out["confirmed"] == ["a_correct"] and out["contradicted"] == ["b_correct"]
    assert out["supported"] == [rec.get(claims["Q1"])["code"]]
    assert not rec.get(claims["Q1"])["state"].get("stale")                            # A's count is back
    assert rec.get(claims["Q2"])["state"].get("stale")                                # B's moved: a worker redoes it
    rec.close()


def test_what_a_claim_rests_on():
    class R:                                          # the two record reads claim_rests_on makes
        def __init__(self, nodes):
            self.nodes = nodes

        def get(self, nid):
            return self.nodes[nid]

        def resolve(self, ref, inv=""):
            return ref

    res = {"id": "rs1", "code": "RS1", "inv": "inv"}
    values = {"a_correct": {"value": 827}, "b_correct": {"value": 789}, "n": {"k": 827, "n": 1000}}
    nodes = {
        "bound": {"body": {"measurements": [{"key": "a_correct", "result": "rs1", "value": 827}]}},
        "said": {"body": {"statement": "A is right on 827 of the 1,000 items."}},
        "derived": {"body": {"statement": "A beats B by 38 items."}},                  # 38 is no single value
        "other": {"body": {"measurements": [{"key": "a_correct", "result": "rs1", "value": 827},
                                            {"key": "p", "result": "rs2", "value": 0.03}]}},
        "rs2": {"state": {"lifecycle": "active", "stale": ["the data file is superseded"]}},
    }
    r = R(nodes)
    assert claim_rests_on(r, "bound", res, values) == {"a_correct"}
    assert claim_rests_on(r, "said", res, values) == {"a_correct", "n"}
    assert claim_rests_on(r, "derived", res, values) is None
    assert claim_rests_on(r, "other", res, values) is None                             # rs2 is still stale
