"""
03 · Trading — a paper desk where "edge" needs out-of-sample returns after costs.

A thesis: after a 5-day drop of 3 % or more, the next 5 days mean-revert. The quant backtests it on a held-out
window with fees and slippage. The record refuses a backtest result that reports returns without the costs it
charged (BACKTEST_WITHOUT_COSTS), and a claim of an "edge" that rests on in-sample or pre-cost numbers
(EDGE_WITHOUT_OOS_COSTS). The scripted quant registers a costless result first, so you see the refusal, then the
honest one. There is no live-order path and no tool here could place one.

    python run.py
    python run.py --model deepseek-ai/DeepSeek-V4.1-Flash --fresh
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _common import budget, cli, main, models, pricing, register_python, reproducer, show, stage

from hypswarm import Seat, Task, run

HERE = Path(__file__).resolve().parent
FEES, SLIP = 0.0010, 0.0005


def make_prices(days: int = 1000, seed: int = 11) -> bytes:
    rng = random.Random(seed)
    rows, px = ["day,close"], 100.0
    for d in range(days):
        px *= 1 + rng.gauss(0.0002, 0.012)
        rows.append(f"{d},{px:.4f}")
    return ("\n".join(rows) + "\n").encode()


BACKTEST = """import csv
px = [float(r['close']) for r in csv.DictReader(open('prices.csv'))]
FEES, SLIP = 0.0010, 0.0005
def run(lo, hi, costs):
    eq, peak, mdd, i, trades = 1.0, 1.0, 0.0, lo + 5, 0
    while i + 5 < hi:
        if px[i] / px[i - 5] - 1 <= -0.03:
            r = px[i + 5] / px[i] - 1 - (2 * (FEES + SLIP) if costs else 0)
            eq *= 1 + r; trades += 1; i += 5
        else:
            i += 1
        peak = max(peak, eq); mdd = min(mdd, eq / peak - 1)
    years = (hi - lo) / 252
    return eq ** (1 / years) - 1, mdd, trades
oos_ret, mdd, n = run(600, len(px), True)
ins_ret, _, _ = run(0, 600, True)
print('oos_return', round(oos_ret, 4)); print('insample_return', round(ins_ret, 4)); print('max_dd', round(mdd, 4))
print('trades', n); print('fees', FEES); print('slippage', SLIP)
"""


def backtest_numbers(data: bytes) -> dict[str, float]:
    import io
    ns: dict[str, object] = {"DATA": data.decode(), "io": io}
    src = BACKTEST.replace("open('prices.csv')", "io.StringIO(DATA)")
    exec(compile(src, "backtest", "exec"), ns)  # noqa: S102 — the example's own backtest, run once to script the stub
    return {k: float(ns[k]) for k in ("oos_ret", "ins_ret", "mdd", "n")}  # type: ignore[arg-type]


if __name__ == "__main__":
    args = cli("03 · trading: out of sample, after costs", HERE)
    data = make_prices()
    v = backtest_numbers(data)
    work = stage(HERE, {"prices.csv": data})
    register_python(work)
    task = Task(title="Mean reversion after a 3 % five-day drop", profile="trading",
                mission="prices.csv holds 1,000 daily closes (day,close). Thesis: after a five-day drop of 3 % or more, the next "
                        "five days mean-revert. Days 0–599 are the fitting window; days 600–999 are HELD OUT. Backtest the "
                        "thesis on the held-out window with 10 bp fees and 5 bp slippage per side and say whether it has an "
                        "edge after costs. Paper only.",
                questions=[("Q1", "Does the thesis have an edge after costs on the held-out window (days 600–999)?")],
                files={"prices.csv": data})
    oos, ins, mdd, n = v["oos_ret"], v["ins_ret"], v["mdd"], int(v["n"])
    edge = oos > 0.0
    answers = {"Q1": {
        "first_try": ("register_run", {"name": "backtest, costless", "result_summary": "Q1: Backtested the thesis on the held-out window.",
                                       "values": {"oos_return": {"value": round(oos + 2 * n * (FEES + SLIP) / 1.6, 4)}},
                                       "claim": "The thesis has an edge on the held-out window.", "answers": "Q1", "scope": "days 600–999"}),
        # the trading workflow: the thesis as a hypothesis, the backtest preregistered as an experiment (windows,
        # costs, configurations), the result with trials declared, and a decision on the claim — paper or declined
        "hypothesis": "After a five-day drop of 3 % or more, the next five days mean-revert.",
        "prediction": "a positive mean return over the five days after the signal on the held-out window, after costs",
        "protocol": "Fitting window days 0–599; held out days 600–999; 10 bp fees and 5 bp slippage per side; one configuration (the thesis as stated).",
        "expected": "a positive held-out return after costs if the thesis holds",
        "summary": "Backtested the thesis on the held-out window with 10 bp fees and 5 bp slippage per side.",
        "values": {"oos_return": {"value": round(oos, 4)}, "insample_return": {"value": round(ins, 4)}, "max_dd": {"value": round(mdd, 4)},
                   "trades": {"value": n}, "fees": {"value": FEES}, "slippage": {"value": SLIP}, "trials": {"value": 1}},
        "code": BACKTEST,
        "claim": (f"On the held-out window the thesis returns {oos:.1%} a year after 10 bp fees and 5 bp slippage, over {n} trades, "
                  f"with a {mdd:.1%} maximum drawdown" + (" — a positive out-of-sample return after costs." if edge else " — no edge after costs.")),
        "scope": "prices.csv days 600–999, held out; 10 bp fees and 5 bp slippage per side; one configuration tried; no leverage; paper.",
        "answer": "yes" if edge else "no",
        **({"position": {"choice": "Paper position: 1 % of book on each signal, stop at -3 % from entry.", "kind": "position",
                         "size": "1 % of book", "stop": "-3 % from entry", "review_date": "2027-03-31", "paper": True,
                         "reasons": "The held-out return after costs is positive; sized small and reviewed in a quarter."}}
           if edge else {"reasons": "No edge after costs on the held-out window; the thesis is declined."})}}
    seats = [Seat("quant", "worker", takes=("edge", "backtest", "thesis")), Seat("risk", "reviewer"), Seat("lead", "lead")]
    res = main(run(task, seats, models(args, answers), record=args.record, budget=budget(args), pricing=pricing(args),
                   folder=work, toolkits=["files", "python"], reproducer=reproducer(work)))
    show(res, quiet=args.quiet, trace=args.trace)
