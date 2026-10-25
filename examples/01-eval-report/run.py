"""
01 · Scientific — an eval report that holds up.

Two models were scored on the same 1,000 items. Does A beat B? Two seats count and compare, the critic settles each
question, the lead writes under the facts. Watch the second claim: "significantly" is accepted only because the
record ran the test on the bound counts; written the other way it is refused with the arithmetic.

    python run.py                 # scripted models, free
    python run.py --model deepseek-ai/DeepSeek-V4.1-Flash --fresh     # a real provider, a few cents
"""
from __future__ import annotations

import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _common import budget, cli, main, models, pricing, register_python, reproducer, show, stage

from hypswarm import Seat, Task, run

HERE = Path(__file__).resolve().parent


def make_items(n: int = 1000, seed: int = 7) -> tuple[bytes, int, int]:
    rng = random.Random(seed)
    rows, ka, kb = ["item,a,b"], 0, 0
    for i in range(1, n + 1):
        a, b = int(rng.random() < 0.81), int(rng.random() < 0.80)
        ka, kb = ka + a, kb + b
        rows.append(f"{i},{a},{b}")
    return ("\n".join(rows) + "\n").encode(), ka, kb


def two_proportion_p(ka: int, kb: int, n: int) -> float:
    p = (ka + kb) / (2 * n)
    se = math.sqrt(p * (1 - p) * (2 / n))
    z = (ka / n - kb / n) / se if se else 0.0
    return 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))


if __name__ == "__main__":
    args = cli("01 · scientific: does A beat B", HERE)
    data, ka, kb = make_items()
    n = 1000
    p = two_proportion_p(ka, kb, n)
    sig = p < 0.05
    work = stage(HERE, {"items.csv": data})
    register_python(work)

    task = Task(title="Does A beat B", profile="scientific",
                mission="Two models, A and B, were scored on the same 1,000 items (items.csv: item,a,b with 1 = right). "
                        "Find out whether A beats B. Numbers come from the file, through python.",
                questions=[("Q1", "What is A's accuracy?"), ("Q2", "Is A significantly more accurate than B (two-sided, 0.05)?")],
                files={"items.csv": data})

    code_q1 = "import csv\nrows = list(csv.DictReader(open('items.csv')))\nk = sum(int(r['a']) for r in rows); n = len(rows)\nprint('acc_a', k, 'of', n)"
    code_q2 = ("import csv, math\nrows = list(csv.DictReader(open('items.csv')))\nn = len(rows)\nka = sum(int(r['a']) for r in rows); kb = sum(int(r['b']) for r in rows)\n"
               "p = (ka + kb) / (2 * n); se = math.sqrt(p * (1 - p) * 2 / n); z = (ka - kb) / n / se\n"
               "pv = 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))\nprint('a', ka, 'of', n); print('b', kb, 'of', n); print('p', round(pv, 4))")
    answers = {
        "Q1": {"summary": "Counted A's correct items in items.csv.", "values": {"acc_a": {"k": ka, "n": n}}, "code": code_q1,
               "claim": f"A is right on {ka} of {n} items.", "scope": "The 1,000 paired items in items.csv.", "answer": round(ka / n, 3)},
        "Q2": {"summary": "Compared A and B on the same items with a two-sided two-proportion z-test.",
               "values": {"a": {"k": ka, "n": n}, "b": {"k": kb, "n": n}, "p": {"value": round(p, 4)}}, "code": code_q2,
               "claim": (f"A is significantly more accurate than B ({ka} of {n} vs {kb} of {n}, p = {p:.3f})." if sig else
                         f"A is not significantly more accurate than B ({ka} of {n} vs {kb} of {n}, p = {p:.2f})."),
               "scope": "The 1,000 paired items in items.csv; two-sided test at 0.05.", "answer": "yes" if sig else "no"},
    }
    seats = [Seat("analyst", "worker", takes=("accuracy", "count")), Seat("stats", "worker", takes=("significantly", "test")),
             Seat("critic", "reviewer"), Seat("lead", "lead")]
    res = main(run(task, seats, models(args, answers), record=args.record, budget=budget(args), pricing=pricing(args),
                   folder=work, toolkits=["files", "python"], reproducer=reproducer(work)))
    show(res, quiet=args.quiet, trace=args.trace)
