"""
05 · Optimization — "optimal" needs a bound.

Six customers, three depots with capacity, a cost per assignment: minimise cost. The solver registers objective,
feasibility and the gap. A result with an objective and no feasibility is refused before it is a result
(OBJECTIVE_WITHOUT_FEASIBILITY); "optimal" without a bound that meets the objective is refused
(OPTIMAL_WITHOUT_BOUND). The instance is small enough to enumerate (3^6 = 729 assignments), so the bound is exact
and the claim can say optimal — and the instrument re-runs the enumeration to confirm it.

    python run.py
    python run.py --model deepseek-ai/DeepSeek-V4.1-Flash --fresh
"""
from __future__ import annotations

import itertools
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _common import budget, cli, main, models, pricing, register_python, reproducer, show, stage

from hypswarm import Seat, Task, run

HERE = Path(__file__).resolve().parent
COST = [[4, 6, 9], [5, 4, 7], [6, 3, 4], [8, 5, 3], [4, 8, 5], [7, 6, 2]]      # customer × depot
CAP = [2, 2, 3]                                                                   # per depot (customers)
DATA = "customer,d0,d1,d2\n" + "\n".join(f"c{i}," + ",".join(map(str, r)) for i, r in enumerate(COST)) + "\ncapacity,2,2,3\n"

SOLVE = """import csv, itertools
rows = list(csv.reader(open('instance.csv')))
cost = [[int(x) for x in r[1:]] for r in rows[1:-1]]; cap = [int(x) for x in rows[-1][1:]]
best, arg, n_feasible = None, None, 0
for a in itertools.product(range(3), repeat=len(cost)):
    if any(a.count(d) > cap[d] for d in range(3)):
        continue
    n_feasible += 1
    c = sum(cost[i][d] for i, d in enumerate(a))
    if best is None or c < best:
        best, arg = c, a
print('objective', best); print('feasible', 1); print('bound', best); print('gap', 0.0)
print('enumerated_feasible', n_feasible); print('assignment', ''.join(map(str, arg)))
"""


def solve() -> tuple[int, str, int]:
    best, arg, nf = None, None, 0
    for a in itertools.product(range(3), repeat=6):
        if any(a.count(d) > CAP[d] for d in range(3)):
            continue
        nf += 1
        c = sum(COST[i][d] for i, d in enumerate(a))
        if best is None or c < best:
            best, arg = c, a
    return int(best), "".join(map(str, arg)), nf


if __name__ == "__main__":
    args = cli("05 · optimization: optimal needs a bound", HERE)
    obj, assignment, nf = solve()
    work = stage(HERE, {"instance.csv": DATA.encode()})
    register_python(work)
    task = Task(title="Assign six customers to three depots at minimum cost", profile="optimization",
                mission="instance.csv: a cost per customer × depot and a capacity per depot (last row). Assign every customer to one "
                        "depot without exceeding capacity, at minimum total cost. Report objective, feasibility and a bound or gap; "
                        "say 'optimal' only with a bound that meets the objective.",
                questions=[("Q1", "What is the minimum total cost, and is the solution found optimal?")], files={"instance.csv": DATA.encode()})
    answers = {"Q1": {
        "first_try": ("register_run", {"name": "greedy", "result_summary": "Q1: A greedy assignment.", "values": {"objective": {"value": obj + 3}},
                                       "claim": f"The minimum cost is {obj + 3}.", "answers": "Q1", "scope": "instance.csv"}),
        "summary": "Enumerated every capacity-feasible assignment (3^6 = 729 candidates) and kept the cheapest.",
        "values": {"objective": {"value": obj}, "feasible": {"value": True}, "bound": {"value": obj}, "gap": {"value": 0.0},
                   "enumerated_feasible": {"value": nf}}, "code": SOLVE,
        "claim": f"The minimum total cost is {obj}, and the solution is optimal: the bound from full enumeration equals the objective.",
        "scope": "instance.csv as given; capacities 2, 2, 3; full enumeration.", "answer": obj}}
    seats = [Seat("modeller", "worker", takes=("model",)), Seat("solver", "worker", takes=("minimum", "cost", "optimal")),
             Seat("verifier", "reviewer"), Seat("lead", "lead")]
    res = main(run(task, seats, models(args, answers), record=args.record, budget=budget(args), pricing=pricing(args),
                   folder=work, toolkits=["files", "python"], reproducer=reproducer(work)))
    show(res, quiet=args.quiet, trace=args.trace)
