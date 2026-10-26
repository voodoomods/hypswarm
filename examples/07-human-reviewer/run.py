"""
07 · A person as the reviewer — over MCP, from your own coding agent or by hand.

The analyst (a model) answers; YOU review. Your seat is `external`: the scheduler issues it an order like any other
and waits for the record to say the order left 'open'. You work it from Claude Code / Cursor / any MCP client:

    hypgraph --db record.hypgraph --as nicolas mcp      # then: my_work → review(...) → return_work

or from the hypgraph CLI with --auto, which plays the person for you so the example runs unattended (it opens the
same record as a second process and writes the review as `nicolas`, exactly as the MCP server would).

    python run.py --auto              # a scripted analyst, and the example reviews as you
    python run.py                     # a scripted analyst, and the run waits up to 30 min for YOUR review
    python run.py --model deepseek-ai/DeepSeek-V4.1-Flash --fresh
"""
from __future__ import annotations

import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _common import budget, cli, main, models, pricing, register_python, reproducer, show, stage

from hypswarm import Seat, Task, run

HERE = Path(__file__).resolve().parent
ITEMS = ("item,a\n" + "\n".join(f"{i},{int(i % 7 != 0)}" for i in range(1, 501)) + "\n").encode()
KA, N = sum(int(i % 7 != 0) for i in range(1, 501)), 500

REVIEW_AS_YOU = textwrap.dedent("""
    import sys, time
    from hypgraph import Graph
    path, who = sys.argv[1], sys.argv[2]
    deadline = time.time() + 120
    while time.time() < deadline:                       # wait for an order assigned to us, like my_work would show
        g = Graph(path)
        inv = g.search("", "investigation", "", 1)[0]["id"]
        mine = [o for o in g.orders(inv) if o["assignee"] == who and o["status"] in ("open", "overdue")]
        if mine:
            o = mine[0]
            target = o["target_id"]
            g.review(author=who, target=target, verdict="checked",
                     method="Opened items.csv myself and recounted column a.",
                     notes="The count matches; the claim says exactly what the file says.")
            g.return_work(author=who, order=o["id"], note="Recounted by hand; the claim holds.")
            print(f"[{who}] reviewed {g.get(target)['code']} and returned {o['code']}", flush=True)
            break
        time.sleep(1.0)
""")


def play_the_person(record: str, who: str) -> threading.Thread:
    def go():
        p = subprocess.run([sys.executable, "-c", REVIEW_AS_YOU, record, who], check=False, capture_output=True, text=True)
        print(p.stdout.strip() or p.stderr.strip()[-600:])
    t = threading.Thread(target=go, daemon=True)
    t.start()
    return t


if __name__ == "__main__":
    args = cli("07 · a person as the reviewer", HERE, auto={"action": "store_true", "help": "play the person from a second process"},
               name={"default": "nicolas", "help": "your seat name"})
    work = stage(HERE, {"items.csv": ITEMS})
    register_python(work)
    # scientific@1: the frozen pre-workflow profile (the example is about the human seat); 01 runs the workflow (scientific@2)
    task = Task(title="Count A's accuracy, reviewed by a person", profile="scientific@1",
                mission="items.csv (item,a with 1 = right). What is A's accuracy? Use python on the file.",
                questions=[("Q1", "What is A's accuracy?")], files={"items.csv": ITEMS})
    answers = {"Q1": {"summary": "Counted column a in items.csv.", "values": {"acc_a": {"k": KA, "n": N}},
                      "code": "import csv\nrows = list(csv.DictReader(open('items.csv')))\nprint('acc_a', sum(int(r['a']) for r in rows), 'of', len(rows))",
                      "claim": f"A is right on {KA} of {N} items.", "scope": "The 500 items in items.csv.", "answer": round(KA / N, 3)}}
    seats = [Seat("analyst", "worker"), Seat(args.name, "reviewer", external=True), Seat("lead", "lead")]
    print(f"\nYour seat: {args.name} (reviewer). From another terminal:\n"
          f"  hypgraph --db {args.record} --as {args.name} mcp\n  → my_work, then review(<claim>, 'checked', how, notes), then return_work\n")
    if args.auto:
        time.sleep(0.5)
        play_the_person(args.record, args.name)
    res = main(run(task, seats, models(args, answers), record=args.record, budget=budget(args), pricing=pricing(args),
                   folder=work, toolkits=["files", "python"], reproducer=reproducer(work),
                   external_timeout_s=150 if args.auto else 1800, external_poll_s=0.5))
    show(res, quiet=args.quiet, trace=args.trace)
