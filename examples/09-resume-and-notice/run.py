"""
09 · Stop it, resume it; withdraw a file mid-run.

Two things a record makes mechanical.

RESUME   In phase 1 the south seat is external — a person who never shows up. The north seat answers, the host
         stops the run, and the south order is still open in the record. Phase 2 resumes the same investigation
         with a model in the south seat: the open order is adopted as it stands, nothing is re-asked, the north
         work still counts, and a new run node says it resumed.
NOTICE   In phase 2, as soon as the first order returns, the host declares site_south.csv corrupt (exported in
         µg/L, labelled mg/L) and registers the fixed file. The record withdraws the artifact with the reason;
         every order issued from then on carries the notice; a worker's read_file refuses the stale bytes; and
         anything that rested on the file falls (here nothing did yet — the south seat had not written).

    python run.py
    python run.py --model deepseek-ai/DeepSeek-V4.1-Flash --fresh
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _common import budget, cli, main, models, pricing, register_python, reproducer, show, stage

from hypswarm import Seat, Task, run, toolkits
from hypswarm.record import LocalRecord
from hypswarm.toolkits import ToolContext

HERE = Path(__file__).resolve().parent
NORTH = ("day,mg_l\n" + "\n".join(f"{d},{1.2 + 0.01 * (d % 5):.2f}" for d in range(30)) + "\n").encode()
SOUTH_BAD = ("day,mg_l\n" + "\n".join(f"{d},{(2.4 + 0.02 * (d % 5)) * 1000:.0f}" for d in range(30)) + "\n").encode()   # µg/L labelled mg/L
SOUTH_FIXED = ("day,mg_l\n" + "\n".join(f"{d},{2.4 + 0.02 * (d % 5):.2f}" for d in range(30)) + "\n").encode()
MEAN_N = round(sum(1.2 + 0.01 * (d % 5) for d in range(30)) / 30, 3)
MEAN_S = round(sum(2.4 + 0.02 * (d % 5) for d in range(30)) / 30, 3)
CODE = "import csv\nv = [float(r['mg_l']) for r in csv.DictReader(open('{f}'))]\nprint('mean_{s}', round(sum(v) / len(v), 3))"

TASK = Task(title="Mean concentration at two sites", profile="scientific",
            mission="site_north.csv and site_south.csv hold 30 daily concentrations (day,mg_l). Report each site's mean in mg/L, from python. "
                    "Read any NOTICES in your order before touching a file.",
            questions=[("Q1", "What is the north site's mean concentration (mg/L)?"), ("Q2", "What is the south site's mean concentration (mg/L)?")],
            files={"site_north.csv": NORTH, "site_south.csv": SOUTH_BAD})


def answers(south_file: str, delay: int = 0) -> dict:
    return {"Q1": {"summary": "Averaged site_north.csv.", "values": {"mean_n": {"value": MEAN_N, "unit": "mg/L"}}, "code": CODE.format(f="site_north.csv", s="n"),
                   "claim": f"The north site's mean concentration is {MEAN_N} mg/L.", "scope": "site_north.csv, 30 daily values.", "answer": MEAN_N},
            "Q2": {"summary": f"Averaged {south_file}.", "values": {"mean_s": {"value": MEAN_S, "unit": "mg/L"}}, "code": CODE.format(f=south_file, s="s"),
                   "claim": f"The south site's mean concentration is {MEAN_S} mg/L.", "scope": f"{south_file}, 30 daily values.", "answer": MEAN_S,
                   "delay_calls": delay}}


if __name__ == "__main__":
    args = cli("09 · resume and notice", HERE)
    Path(args.record).unlink(missing_ok=True)                    # always fresh: the example needs both phases
    work = stage(HERE, {"site_north.csv": NORTH, "site_south.csv": SOUTH_BAD})
    register_python(work)

    print("\n=== phase 1: north answers; south is a person who never shows up; stop at the first return ===")
    seats1 = [Seat("north", "worker", takes=("north",)), Seat("south", "worker", takes=("south",), external=True),
              Seat("critic", "reviewer"), Seat("lead", "lead")]
    r1 = main(run(TASK, seats1, models(args, answers("site_south.csv")), record=args.record, budget=budget(args), pricing=pricing(args),
                  folder=work, toolkits=["files", "python"], reproducer=reproducer(work), external_timeout_s=600,
                  on_return=lambda sched, n: sched.stop() if n == 1 else None))
    print(f"stopped: {r1.stopped!r}; orders in the record: " + ", ".join(f"{o['code']}={o['status']} ({o['assignee']})" for o in r1.orders))

    print("\n=== phase 2: resume with a model in the south seat; at the first return, declare site_south.csv corrupt ===")
    (work / "site_south_fixed.csv").write_bytes(SOUTH_FIXED)
    seats2 = [Seat("north", "worker", takes=("north",)), Seat("south", "worker", takes=("south",)),
              Seat("critic", "reviewer"), Seat("lead", "lead")]

    def notice_once(sched, n):
        if n == 1 and not sched.notices:
            sched.notify("site_south.csv was exported in µg/L but labelled mg/L; use site_south_fixed.csv (mg/L).",
                         stale=["site_south.csv"], add_files={"site_south_fixed.csv": SOUTH_FIXED})
    r2 = main(run(TASK, seats2, models(args, answers("site_south_fixed.csv", delay=2)), record=args.record, budget=budget(args),
                  pricing=pricing(args), folder=work, toolkits=["files", "python"], reproducer=reproducer(work), resume=r1.inv,
                  on_return=notice_once))
    show(r2, quiet=args.quiet, trace=args.trace)

    print(f"\nadopted on resume: {r2.scheduler.adopted} (south's open order, as it stood); notices: {len(r2.scheduler.notices)}")
    rec = LocalRecord(args.record, seats2)
    inv = r2.inv
    stale = [a for a in rec.search("site_south.csv", "artifact", inv) if a["title"].strip() == "site_south.csv"]
    for a in stale:
        print(f"artifact site_south.csv: {rec.get(a['id'])['state']['sentence']}")
    last = rec.orders(inv)[-1]
    text = rec.order_text(last["id"])
    if "NOTICES" in text:
        i = text.index("NOTICES")
        print(f"the last order issued ({last['code']}) carries it:\n  " + text[i:i + 160].replace("\n", "\n  "))
    files = toolkits.build(["files"], ToolContext(rec, inv, work))
    read_file = next(t for t in files if t.name == "read_file")
    print("read_file('site_south.csv') →", asyncio.run(read_file.call({"name": "site_south.csv"}))[:160])
    print("read_file('site_south_fixed.csv') →", asyncio.run(read_file.call({"name": "site_south_fixed.csv"}))[:60].replace("\n", " "), "…")
    rec.close()
