"""Reliability and cost of the scheduler itself, on scripted models — no network, no spend.

Runs the alpha task N times on an in-memory record and reports, per run: did it settle, model calls, scheduler
rounds, orders issued, reworks, wall seconds. Model calls here are the scheduler's *orchestration* cost: how many
model turns it takes to settle a task when every seat does exactly its job. Run it on two commits to see what a
change costs.

    .venv/Scripts/python bench/stub_bench.py [N]
    PYTHONPATH=<other checkout>/src .venv/Scripts/python bench/stub_bench.py [N]     # the same on another commit
"""
from __future__ import annotations

import asyncio
import json
import statistics as st
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))                      # tests/ as a package
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "HypGraph" / "src"))
if "PYTHONPATH" not in __import__("os").environ:                                   # this checkout, unless told otherwise
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from tests.test_alpha import TASK, make_models  # noqa: E402

import hypswarm  # noqa: E402
from hypswarm import Budget, Seat, run  # noqa: E402

SEATS = [Seat("analyst", "worker", takes=("accuracy", "counts")), Seat("stats", "worker", takes=("significant", "test")),
         Seat("critic", "reviewer"), Seat("lead", "lead")]


def one() -> dict:
    t = time.perf_counter()
    res = asyncio.run(run(TASK, SEATS, make_models(), record=None, budget=Budget(max_calls=150)))
    return {"settled": res.stopped == "settled" and res.report_accepted, "calls": res.usage["calls"],
            "rounds": res.scheduler.rounds, "orders": res.scheduler.orders_issued, "reworks": res.scheduler.reworks,
            "s": time.perf_counter() - t}


def main(n: int) -> int:
    rows = [one() for _ in range(n)]
    out = {"hypswarm": hypswarm.__version__, "source": str(Path(hypswarm.__file__).resolve().parent), "runs": n,
           "settled": sum(r["settled"] for r in rows),
           "calls": {"mean": st.mean(r["calls"] for r in rows), "min": min(r["calls"] for r in rows),
                     "max": max(r["calls"] for r in rows)},
           "rounds": st.mean(r["rounds"] for r in rows), "orders": st.mean(r["orders"] for r in rows),
           "reworks": sum(r["reworks"] for r in rows),
           "seconds": {"median": round(st.median(r["s"] for r in rows), 3), "p90": round(sorted(r["s"] for r in rows)[int(n * 0.9) - 1], 3)}}
    print(json.dumps(out, indent=1))
    return 0 if out["settled"] == n else 1


if __name__ == "__main__":
    sys.exit(main(int(sys.argv[1]) if len(sys.argv) > 1 else 20))
