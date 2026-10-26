"""
The change suite (P3): five families in which the world changes in the middle of the work, and nobody says so.

Each instance is a task whose evidence is computed from files or pages, plus one change that lands right after the
first computation on the old state — a vendor's corrected file (C1, C3), a teammate's commit (C2), an edited page
(C4), a revised instance (C5). The change is applied by the tool both conditions share (the python or fetch call
that read the old state fires it), so P and R meet it at the same point and are told the same thing: nothing. Both
missions carry the same rule (FRESH_RULE): re-check before answering. The only difference is enforcement — in R the
record notices the bytes changed, re-runs what depended on them and reopens only the answers that moved.

Seeds 0-3 change an answer; seed 4 is HARMLESS — the bytes change, the answers don't (rows reordered, a docstring, a
re-export, an edit elsewhere on the page, a cost on a pair nobody uses). The checker scores the final artifact
against the answers as they are AFTER the change: current, or stale (it reports the pre-change answer), plus the
question the change didn't touch.
"""
from __future__ import annotations

import itertools
import json
import random
import re
from dataclasses import dataclass, field
from typing import Any

from checkers import _answers
from families import _backtest, two_prop_p

CHANGE_FAMILIES = ("C1", "C2", "C3", "C4", "C5")
PROFILE = {"C1": "scientific", "C2": "software", "C3": "trading", "C4": "knowledge", "C5": "optimization"}
HARMLESS_SEED = 4
FRESH_RULE = ("The files and pages may change while you work — a vendor's corrected file, a teammate's commit, an edited "
              "page — and nobody will tell you. Before you give your final answer, make sure every number in it comes "
              "from the files and pages as they are at that moment.")


@dataclass
class Change:
    files: dict[str, bytes] = field(default_factory=dict)       # path -> the bytes after the change
    pages: dict[str, str] = field(default_factory=dict)         # page path -> the html after the change
    python: str = ""                                            # a python call whose code matches this fires it
    fetch: str = ""                                             # a fetch of a URL ending with this fires it
    evidence: str = ""                                          # …and only once the call's output shows the old answer
    what: str = ""                                              # one line for the results (never shown to agents)


@dataclass
class CInstance:
    family: str
    seed: int
    profile: str
    title: str
    mission: str
    questions: list[tuple[str, str]]
    files: dict[str, bytes]
    change: Change
    pre: dict[str, dict[str, Any]]                              # question -> the answer before the change
    post: dict[str, dict[str, Any]]                             # question -> the answer after it (what is scored)
    affected: list[str]
    pages: dict[str, str] = field(default_factory=dict)
    harmless: bool = False


def _csv(header: str, rows: list[tuple[Any, ...]]) -> bytes:
    return (header + "\n" + "".join(",".join(map(str, r)) + "\n" for r in rows)).encode()


# ── C1 scientific: the vendor corrects B's labels ─────────────────────────────
def c1(seed: int) -> CInstance:
    n = 1000
    for k in range(200):
        rng = random.Random(7100 + 37 * seed + k)
        a = [int(rng.random() < 0.82) for _ in range(n)]
        b = [int(rng.random() < 0.775) for _ in range(n)]
        ka, kb = sum(a), sum(b)
        if two_prop_p(ka, kb, n) >= 0.05:
            continue                                            # the erroneous file must show a significant gap
        zeros = [i for i in range(n) if b[i] == 0]
        rng.shuffle(zeros)
        flip_at = next((c for c in range(1, 120) if two_prop_p(ka, kb + c, n) >= 0.05), None)
        if flip_at is None:
            continue
        c = (flip_at + rng.randrange(0, 6)) if seed in (0, 1, 2) else max(3, flip_at // 4) if seed == 3 else 0
        if seed == 3 and two_prop_p(ka, kb + c, n) >= 0.05:
            continue
        b2 = list(b)
        for i in zeros[:c]:
            b2[i] = 1
        break
    rows = [(i + 1, a[i], b[i]) for i in range(n)]
    if seed == HARMLESS_SEED:
        moved = list(rows)
        random.Random(seed).shuffle(moved)                      # re-exported in another order: same counts
        new = _csv("item,a,b", moved)
        what = "items.csv re-exported in a different row order (counts unchanged)"
    else:
        new = _csv("item,a,b", [(i + 1, a[i], b2[i]) for i in range(n)])
        what = f"items.csv corrected: {c} of B's labels fixed (wrong → right)"
    kb2 = kb if seed == HARMLESS_SEED else sum(b2)
    pre = {"Q1": {"a_correct": ka}, "Q2": {"b_correct": kb, "significant": two_prop_p(ka, kb, n) < 0.05}}
    post = {"Q1": {"a_correct": ka}, "Q2": {"b_correct": kb2, "significant": two_prop_p(ka, kb2, n) < 0.05}}
    return CInstance("C1", seed, "scientific", "Does A beat B",
                     "items.csv holds 1,000 items scored for two models, A and B (item,a,b; 1 = right). Use python on the "
                     "file for every number. " + FRESH_RULE,
                     [("Q1", 'How many of the 1,000 items is A right on? Answer as {"a_correct": <int>}.'),
                      ("Q2", 'How many items is B right on, and is A significantly more accurate than B (two-proportion '
                             'z-test, two-sided, 0.05)? Answer as {"b_correct": <int>, "significant": true|false}.')],
                     {"items.csv": _csv("item,a,b", rows)},
                     Change(files={"items.csv": new}, python=r"items\.csv", evidence=rf"(?<!\d){kb}(?!\d)", what=what),
                     pre, post, ["Q2"], harmless=seed == HARMLESS_SEED)


# ── C2 software: a teammate's commit lands after the first test run ───────────
_MONEY = '''"""Money parsing."""
from decimal import Decimal


def parse_amount(text: str) -> Decimal:
    """'1,234.56' -> Decimal('1234.56')"""
    return Decimal(text.replace(",", "").strip()).quantize(Decimal("0.01"))
'''
_FMT = '''"""Money and percent formatting."""
from decimal import ROUND_HALF_UP, Decimal


def format_amount(d: Decimal) -> str:
    """Decimal('1234.5') -> '1,234.50'"""
    return f"{d.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):,}"


def format_percent(x: Decimal) -> str:
    """Decimal('0.1234') -> '12.34%'"""
    return f"{(x * 100).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}%"
'''
_TESTS = '''from decimal import Decimal

from calc.fmt import format_amount, format_percent
from calc.money import parse_amount


def test_parses_cents():
    assert parse_amount("1,234.56") == Decimal("1234.56")


def test_parses_whole():
    assert parse_amount("12") == Decimal("12.00")


def test_parses_negative():
    assert parse_amount("-3.50") == Decimal("-3.50")


def test_format_thousands():
    assert format_amount(Decimal("1234.5")) == "1,234.50"


def test_format_rounds_half_up():
    assert format_amount(Decimal("2.005")) == "2.01"


def test_format_percent():
    assert format_percent(Decimal("0.1234")) == "12.34%"
'''
# what each seed's commit does to calc/fmt.py, and how many of the 6 tests still pass
_COMMITS = {
    0: ("drops the thousands separator", (":,}", ":}"), 5),
    1: ("switches rounding to half-even", ("rounding=ROUND_HALF_UP):,}", "rounding=ROUND_HALF_EVEN):,}"), 5),
    2: ("drops the separator and switches rounding", None, 4),
    3: ("drops the % sign from percentages", (')}%"', ')}"'), 5),
    4: ("adds a docstring line (no behaviour change)", ('"""Money and percent formatting."""',
                                                         '"""Money and percent formatting (house style)."""'), 6),
}


def c2(seed: int) -> CInstance:
    what, edit, passing = _COMMITS[seed]
    if seed == 2:
        fmt2 = _FMT.replace("rounding=ROUND_HALF_UP):,}", "rounding=ROUND_HALF_EVEN)}")
    else:
        assert edit
        fmt2 = _FMT.replace(*edit, 1)
    if "ROUND_HALF_EVEN" in fmt2:
        fmt2 = fmt2.replace("from decimal import ROUND_HALF_UP, Decimal", "from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal")
    files = {"calc/__init__.py": b"", "calc/money.py": _MONEY.encode(), "calc/fmt.py": _FMT.encode(),
             "tests/__init__.py": b"", "tests/test_calc.py": _TESTS.encode()}
    pre = {"Q1": {"cents_kept": True}, "Q2": {"passed": 6, "total": 6, "all_pass": True}}
    post = {"Q1": {"cents_kept": True}, "Q2": {"passed": passing, "total": 6, "all_pass": passing == 6}}
    return CInstance("C2", seed, "software", "Verify the release candidate",
                     "A release candidate: package calc/ and its tests in tests/. Verify it with python — run the tests "
                     "with subprocess (python -m pytest -q tests) — and report exactly what passed. Do not change the "
                     "code. " + FRESH_RULE,
                     [("Q1", "Does parse_amount('1,234.56') return Decimal('1234.56') on the current code? Answer as "
                             '{"cents_kept": true|false}.'),
                      ("Q2", "How many of the tests in tests/ pass on the current code, out of how many, and do all of "
                             'them pass? Answer as {"passed": <int>, "total": <int>, "all_pass": true|false}.')],
                     files, Change(files={"calc/fmt.py": fmt2.encode()}, python=r"pytest", evidence=r"(?<!\d)6 passed",
                                   what=f"a commit to calc/fmt.py {what}"),
                     pre, post, ["Q2"], harmless=seed == HARMLESS_SEED)


# ── C3 trading: the vendor removes bad prints from the held-out window ────────
def _series(seed: int, k: int) -> list[float]:
    rng = random.Random(7300 + 31 * seed + k)
    px, p = [], 100.0
    for d in range(1000):
        drift = 0.0
        if d >= 5 and px[-1] / px[-5] - 1 <= -0.03:
            drift = 0.006 if d < 600 else -0.004                 # in sample it rebounds; out of sample it doesn't
        p *= 1 + rng.gauss(drift, 0.012)
        px.append(p)
    return px


def c3(seed: int) -> CInstance:
    for k in range(400):
        true_px = _series(seed, k)
        rng = random.Random(7350 + 31 * seed + k)
        bad = list(true_px)
        n_bad = {0: 6, 1: 7, 2: 8, 3: 2, 4: 6}[seed]
        days = sorted(rng.sample(range(620, 985), n_bad))
        for d in days:
            bad[d] = true_px[d] * 0.955                          # a bad print 4.5 % low: a fake drop, a fake rebound
        b_oos, b_n = _backtest(bad, 600, 1000)
        t_oos, t_n = _backtest(true_px, 600, 1000)
        b_edge, t_edge = b_oos > 0 and b_n >= 3, t_oos > 0 and t_n >= 3
        if seed in (0, 1, 2) and b_edge and not t_edge and round(b_oos, 4) != round(t_oos, 4):
            break
        if seed == 3 and b_edge == t_edge and (b_n != t_n or round(b_oos, 4) != round(t_oos, 4)):
            break
        if seed == HARMLESS_SEED and b_edge:
            break
    fmt = "{:.4f}"
    before = "day,close\n" + "\n".join(f"{d},{fmt.format(v)}" for d, v in enumerate(bad)) + "\n"
    if seed == HARMLESS_SEED:
        after_px = [float(fmt.format(v)) for v in bad]           # re-exported with six decimals: the same values
        after = "day,close\n" + "\n".join(f"{d},{v:.6f}" for d, v in enumerate(after_px)) + "\n"
        what = "prices.csv re-exported with six decimals (values unchanged)"
    else:
        after_px = [float(fmt.format(v)) for v in true_px]
        after = "day,close\n" + "\n".join(f"{d},{fmt.format(v)}" for d, v in enumerate(true_px)) + "\n"
        what = f"prices.csv corrected: {n_bad} bad prints in the held-out window replaced with the real closes"
    bpx = [float(fmt.format(v)) for v in bad]
    pb_oos, pb_n = _backtest(bpx, 600, 1000)
    pa_oos, pa_n = _backtest(after_px, 600, 1000)
    pre = {"Q1": {"oos_net_per_trade": round(pb_oos, 4), "trades": pb_n, "edge": bool(pb_oos > 0 and pb_n >= 3)}}
    post = {"Q1": {"oos_net_per_trade": round(pa_oos, 4), "trades": pa_n, "edge": bool(pa_oos > 0 and pa_n >= 3)}}
    return CInstance("C3", seed, "trading", "Mean reversion after a 3 % five-day drop",
                     "prices.csv holds 1,000 daily closes (day,close). Thesis: after a five-day drop of 3 % or more, buy "
                     "and hold five days. Days 0-599 are the fitting window; days 600-999 are HELD OUT. Backtest with "
                     "python on the held-out window: enter at the close of the signal day, exit five days later, 10 bp "
                     "fees and 5 bp slippage per side; after a trade, look for the next signal from the exit day. Paper "
                     "only. " + FRESH_RULE,
                     [("Q1", "On the held-out window (days 600-999): what is the mean net return per trade after costs, "
                             "how many trades, and does the thesis have an edge after costs (mean > 0 with at least 3 "
                             'trades)? Answer as {"oos_net_per_trade": <float, 4 dp>, "trades": <int>, "edge": true|false}.')],
                     {"prices.csv": before.encode()},
                     Change(files={"prices.csv": after.encode()}, python=r"prices\.csv", evidence=rf"(?<!\d){pb_n}(?!\d)", what=what),
                     pre, post, ["Q1"], harmless=seed == HARMLESS_SEED)


# ── C4 knowledge: the page is edited after it was read ────────────────────────
def c4(seed: int) -> CInstance:
    rng = random.Random(7400 + seed)
    cap = 42_000 + rng.randrange(0, 9000, 250)
    cap2 = cap + rng.choice([-1, 1]) * rng.randrange(750, 4000, 250)
    opened = 1952 + rng.randrange(0, 30)

    def harlow(c: int, extra: str = "") -> str:
        return (f"<html><body><h1>Harlow Reservoir</h1><p>Harlow Reservoir in the Vale of Ketter was opened in {opened} by "
                f"the Ketter Water Board. Its storage capacity is {c:,} megalitres{extra}.</p></body></html>")
    pages = {"/harlow-reservoir": harlow(cap),
             "/ketter-dam": "<html><body><h1>Ketter Dam</h1><p>The Ketter Dam impounds Harlow Reservoir and was raised twice."
                            "</p></body></html>",
             "/vale-of-ketter": "<html><body><h1>Vale of Ketter</h1><p>A valley of sheep farms and three villages.</p></body></html>"}
    if seed == HARMLESS_SEED:
        new, cap2, what = harlow(cap, ". A visitor centre opened on the north shore in 2019"), cap, "an edit elsewhere on the page"
    else:
        new, what = harlow(cap2, " (revised after the 2026 survey)"), f"capacity revised from {cap:,} to {cap2:,}"
    pre = {"Q1": {"opened": opened}, "Q2": {"capacity_ml": cap}}
    post = {"Q1": {"opened": opened}, "Q2": {"capacity_ml": cap2}}
    return CInstance("C4", seed, "knowledge", "Two facts, sourced",
                     "Answer each question from a page you fetched with the fetch tool (only the pages on the local host it "
                     "serves exist). Cite the page's URL beside every answer; do not answer from memory. " + FRESH_RULE,
                     [("Q1", 'In what year was Harlow Reservoir opened? Answer as {"opened": <int>}.'),
                      ("Q2", "What is Harlow Reservoir's storage capacity in megalitres? Answer as "
                             '{"capacity_ml": <int>}.')],
                     {}, Change(pages={"/harlow-reservoir": new}, fetch="/harlow-reservoir", evidence=f"{cap:,}", what=what),
                     pre, post, ["Q2"],
                     pages=pages, harmless=seed == HARMLESS_SEED)


# ── C5 optimization: a depot's capacity is revised after the first solve ──────
def _solve(cost: list[list[int]], cap: list[int]) -> tuple[int | None, list[tuple[int, ...]]]:
    best, args = None, []
    for a in itertools.product(range(3), repeat=len(cost)):
        if any(a.count(d) > cap[d] for d in range(3)):
            continue
        c = sum(cost[i][d] for i, d in enumerate(a))
        if best is None or c < best:
            best, args = c, [a]
        elif c == best:
            args.append(a)
    return best, args


def c5(seed: int) -> CInstance:
    for k in range(200):
        rng = random.Random(7500 + 41 * seed + k)
        cost = [[rng.randrange(2, 12) for _ in range(3)] for _ in range(8)]
        cap = [3, 3, 3]
        opt, args = _solve(cost, cap)
        assert opt is not None
        cost2, cap2 = [list(r) for r in cost], list(cap)
        if seed == HARMLESS_SEED:
            used = {(i, d) for a in args for i, d in enumerate(a)}
            free = [(i, d) for i in range(1, 8) for d in range(3) if (i, d) not in used]
            if not free:
                continue
            i, d = free[rng.randrange(len(free))]
            cost2[i][d] += 3
            what = f"the cost of c{i} at d{d} (a pairing no optimal assignment uses) raised by 3"
        else:
            full = [d for d in range(3) if args[0].count(d) == 3]
            if not full:
                continue
            cap2[full[0]] = 2
            what = f"depot d{full[0]}'s capacity revised from 3 to 2"
        opt2, _ = _solve(cost2, cap2)
        if opt2 is None or (seed != HARMLESS_SEED and opt2 == opt) or (seed == HARMLESS_SEED and opt2 != opt):
            continue
        break

    def data(c: list[list[int]], p: list[int]) -> bytes:
        return ("customer,d0,d1,d2\n" + "".join(f"c{i}," + ",".join(map(str, r)) + "\n" for i, r in enumerate(c))
                + "capacity," + ",".join(map(str, p)) + "\n").encode()
    pre = {"Q1": {"cost": opt, "optimal": True}}
    post = {"Q1": {"cost": opt2, "optimal": True}}
    return CInstance("C5", seed, "optimization", "Assign eight customers to three depots at minimum cost",
                     "instance.csv: a cost per customer x depot and a capacity per depot (last row). Assign every customer "
                     "to one depot without exceeding capacity, at minimum total cost, with python. Say 'optimal' only with "
                     "a bound that proves it. " + FRESH_RULE,
                     [("Q1", "What is the minimum total cost, and is the solution found optimal? Answer as "
                             '{"cost": <int>, "optimal": true|false}.')],
                     {"instance.csv": data(cost, cap)},
                     Change(files={"instance.csv": data(cost2, cap2)}, python=r"instance\.csv", evidence=rf"(?<!\d){opt}(?!\d)",
                            what=what),
                     pre, post, ["Q1"], harmless=seed == HARMLESS_SEED)


def make_change(family: str, seed: int) -> CInstance:
    return {"C1": c1, "C2": c2, "C3": c3, "C4": c4, "C5": c5}[family](seed)


# ── the checker ──────────────────────────────────────────────────────────────
def _value(ans: Any, key: str, keys: list[str]) -> Any:
    if isinstance(ans, dict):
        for k, v in ans.items():
            if str(k).lower() == key.lower():
                return v
        return None
    return ans if len(keys) == 1 else None


def _same(got: Any, want: Any) -> bool:
    if got is None:
        return False
    if isinstance(want, bool):
        if isinstance(got, bool):
            return got == want
        return str(got).strip().lower() in (("true", "yes") if want else ("false", "no"))
    if isinstance(want, (int, float)):
        try:
            g = float(str(got).replace(",", "").replace("%", "").strip())
        except ValueError:
            return False
        if isinstance(want, float) and not float(want).is_integer() or (isinstance(want, float) and abs(want) < 1):
            return abs(g - want) <= 0.0005 or abs(g / 100 - want) <= 0.0005       # a fraction or the same as a percent
        return abs(g - float(want)) < 0.5
    return str(got).strip().lower() == str(want).strip().lower()


def _matches(ans: Any, want: dict[str, Any]) -> bool:
    keys = list(want)
    return all(_same(_value(ans, k, keys), v) for k, v in want.items())


def check_change(inst: CInstance, text: str) -> dict[str, Any]:
    """current: every affected answer is the post-change one. stale: an affected answer is the pre-change one (and
    that differs from the post-change one). unaffected_ok: the questions the change didn't touch are right."""
    ans = _answers(text or "")
    answered = all(ans.get(q) is not None for q in inst.post)
    current = all(_matches(ans.get(q), inst.post[q]) for q in inst.affected)
    stale = False
    for q in inst.affected:
        moved = {k: v for k, v in inst.pre[q].items() if inst.post[q].get(k) != v}
        if moved and _matches(ans.get(q), moved):
            stale = True
    unaffected = [q for q in inst.post if q not in inst.affected]
    unaffected_ok = all(_matches(ans.get(q), inst.post[q]) for q in unaffected) if unaffected else None
    return {"current": current, "stale": stale, "unaffected_ok": unaffected_ok, "answered": answered,
            "answers": {q: ans.get(q) for q in inst.post}}


# ── scripted answers (the stub run; honest, computed by real code from the files) ──
def _code_c1(q: str) -> str:
    if q == "Q1":
        return ("import csv\nrows = list(csv.DictReader(open('items.csv')))\n"
                "print('a_correct', sum(int(r['a']) for r in rows), 'of', len(rows))")
    return ("import csv, math\nrows = list(csv.DictReader(open('items.csv')))\nn = len(rows)\n"
            "ka = sum(int(r['a']) for r in rows); kb = sum(int(r['b']) for r in rows)\n"
            "p = (ka + kb) / (2 * n); se = math.sqrt(p * (1 - p) * 2 / n); z = (ka - kb) / n / se\n"
            "pv = 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))\n"
            "print('a_correct', ka, 'of', n); print('b_correct', kb, 'of', n); print('p', round(pv, 4))")


_C2_Q1 = ("from decimal import Decimal\nfrom calc.money import parse_amount\n"
          "print('cents_kept', int(parse_amount('1,234.56') == Decimal('1234.56')))")
_C2_Q2 = ("import re, subprocess, sys\nr = subprocess.run([sys.executable, '-m', 'pytest', '-q', 'tests'], capture_output=True, text=True)\n"
          "m = re.search(r'(\\d+) passed', r.stdout); f = re.search(r'(\\d+) failed', r.stdout)\n"
          "k = int(m.group(1)) if m else 0; n = k + (int(f.group(1)) if f else 0)\n"
          "print('passed', k, 'of', n); print('exit_code', r.returncode)")
_C3_CODE = ("import csv\npx = [float(r['close']) for r in csv.DictReader(open('prices.csv'))]\n"
            "rets, i = [], 605\nwhile i + 5 < 1000:\n    if px[i] / px[i - 5] - 1 <= -0.03:\n"
            "        rets.append(px[i + 5] / px[i] - 1 - 2 * (0.0010 + 0.0005)); i += 5\n    else:\n        i += 1\n"
            "m = sum(rets) / len(rets) if rets else 0.0\n"
            "print('oos_net_per_trade', round(m, 4)); print('trades', len(rets)); print('fees', 0.001); print('slippage', 0.0005); print('trials', 1)")
_C5_CODE = ("import csv, itertools\nrows = list(csv.reader(open('instance.csv')))\n"
            "cost = [[int(x) for x in r[1:]] for r in rows[1:-1]]; cap = [int(x) for x in rows[-1][1:]]\nbest = None\n"
            "for a in itertools.product(range(3), repeat=len(cost)):\n    if any(a.count(d) > cap[d] for d in range(3)):\n        continue\n"
            "    c = sum(cost[i][d] for i, d in enumerate(a))\n    best = c if best is None or c < best else best\n"
            "print('objective', best); print('feasible', 1); print('bound', best); print('gap', 0.0)")


def stub_answers(inst: CInstance) -> dict[str, dict[str, Any]]:
    """What the scripted seats write — before the change, and (``after``) once a notice of it reaches them."""
    pre, post = inst.pre, inst.post
    if inst.family == "C1":
        def q2(v: dict[str, Any]) -> dict[str, Any]:
            from families import two_prop_p as tp
            ka, kb = pre["Q1"]["a_correct"], v["b_correct"]
            p = round(tp(ka, kb, 1000), 4)
            word = "significantly more accurate" if p < 0.05 else "not significantly more accurate"
            return {"summary": "Compared A and B on the same items with a two-proportion z-test.",
                    "values": {"a_correct": {"k": ka, "n": 1000}, "b_correct": {"k": kb, "n": 1000}, "p": {"value": p}},
                    "claim": f"A is {word} than B ({ka} of 1000 vs {kb} of 1000, p = {p}).",
                    "scope": "The 1,000 paired items in items.csv; two-proportion z-test, two-sided, 0.05.",
                    "answer": {"b_correct": kb, "significant": p < 0.05}}
        return {"Q1": {"summary": "Counted A's correct items.", "values": {"a_correct": {"k": pre["Q1"]["a_correct"], "n": 1000}},
                       "code": _code_c1("Q1"), "claim": f"A is right on {pre['Q1']['a_correct']} of 1000 items.",
                       "scope": "The 1,000 items in items.csv.", "answer": {"a_correct": pre["Q1"]["a_correct"]}},
                "Q2": {**q2(pre["Q2"]), "code": _code_c1("Q2"), "after": q2(post["Q2"])}}
    if inst.family == "C2":
        def q2(v: dict[str, Any]) -> dict[str, Any]:
            k = v["passed"]
            ok = k == 6
            return {"summary": "Ran python -m pytest -q tests on the current code.",
                    "values": {"passed": {"k": k, "n": 6}, "exit_code": {"value": 0 if ok else 1}},
                    "outcome": "positive" if ok else "negative",
                    "claim": ("All 6 of 6 tests in tests/ succeed on the current head." if ok else
                              f"The suite does not pass on the current head: {k} of 6 tests succeed."),
                    "scope": "tests/ on the current head, run by the instrument.",
                    "answer": {"passed": k, "total": 6, "all_pass": ok}}
        return {"Q1": {"summary": "Checked parse_amount on the sample amount.", "values": {"cents_kept": {"value": 1}},
                       "code": _C2_Q1, "outcome": "positive", "claim": "parse_amount keeps the cents on the current code.",
                       "scope": "calc/money.py on the current head; the sample amount from the question.",
                       "answer": {"cents_kept": True}},
                "Q2": {**q2(pre["Q2"]), "code": _C2_Q2, "after": q2(post["Q2"])}}
    if inst.family == "C3":
        def q1(v: dict[str, Any]) -> dict[str, Any]:
            m, n, edge = v["oos_net_per_trade"], v["trades"], v["edge"]
            out: dict[str, Any] = {
                "summary": "Backtested the thesis on the held-out window after costs.",
                "values": {"oos_net_per_trade": {"value": m}, "trades": {"value": n}, "fees": {"value": 0.001},
                           "slippage": {"value": 0.0005}, "trials": {"value": 1}},
                "claim": (f"On the held-out window the thesis returns {m} per trade after costs over {n} trades"
                          + (", a positive return after costs." if edge else ", no positive return after costs.")),
                "scope": "Days 600-999 of prices.csv; 10 bp fees and 5 bp slippage per side; one configuration.",
                "answer": {"oos_net_per_trade": m, "trades": n, "edge": edge}}
            if edge:
                out["position"] = {"choice": "Paper position: 1 % of book on each signal, stop at -3 % from entry.",
                                   "kind": "position", "size": "1 % of book", "stop": "-3 % from entry",
                                   "review_date": "2027-12-31", "paper": True,
                                   "reasons": "The held-out return after costs is positive; sized small."}
            else:
                out["reasons"] = "No positive held-out return after costs; the thesis is declined."
            return out
        thesis = {"hypothesis": "After a five-day drop of 3 % or more, the next five days mean-revert.",
                  "prediction": "a positive mean held-out return per trade after costs",
                  "protocol": "Held out days 600-999; enter at the signal close, exit five days later; 10 bp fees and 5 bp slippage per side; one configuration.",
                  "expected": "a positive held-out return after costs if the thesis holds"}
        return {"Q1": {**thesis, **q1(pre["Q1"]), "code": _C3_CODE, "after": q1(post["Q1"])}}
    if inst.family == "C4":
        def q2(v: dict[str, Any]) -> dict[str, Any]:
            c = v["capacity_ml"]
            return {"source": {"citation": "Harlow Reservoir page", "url": "__BASE__/harlow-reservoir",
                               "passage": f"capacity is {c:,} megalitres", "kind": "secondary"},
                    "claim": f"Harlow Reservoir's storage capacity is {c:,} megalitres.",
                    "scope": "The Harlow Reservoir page on the source host.", "answer": {"capacity_ml": c}}
        o = pre["Q1"]["opened"]
        return {"Q1": {"source": {"citation": "Harlow Reservoir page", "url": "__BASE__/harlow-reservoir",
                                  "passage": f"opened in {o}", "kind": "secondary"},
                       "claim": f"Harlow Reservoir was opened in {o}.", "scope": "The Harlow Reservoir page on the source host.",
                       "answer": {"opened": o}},
                "Q2": {**q2(pre["Q2"]), "after": q2(post["Q2"])}}
    if inst.family == "C5":
        def q1(v: dict[str, Any]) -> dict[str, Any]:
            c = v["cost"]
            return {"summary": "Enumerated every capacity-feasible assignment.",
                    "values": {"objective": {"value": c}, "feasible": {"value": True}, "bound": {"value": c}, "gap": {"value": 0.0}},
                    "claim": f"The minimum total cost is {c}, and it is optimal: the bound from full enumeration equals the objective.",
                    "scope": "instance.csv as it is; every capacity-feasible assignment enumerated.",
                    "answer": {"cost": c, "optimal": True}}
        import hashlib
        art = {"sha256": hashlib.sha256(inst.files["instance.csv"]).hexdigest(), "path": "instance.csv", "kind": "instance",
               "size": len(inst.files["instance.csv"])}
        art2 = {**art, "sha256": hashlib.sha256(inst.change.files["instance.csv"]).hexdigest(),
                "size": len(inst.change.files["instance.csv"])}
        return {"Q1": {**q1(pre["Q1"]), "code": _C5_CODE, "artifact": art, "after": {**q1(post["Q1"]), "artifact": art2},
                       "hypothesis": "A capacitated assignment: each customer to one depot, capacities binding, cost = the sum of costs.",
                       "protocol": "Enumerate every capacity-feasible assignment; the minimum is the optimum and its own bound."}}
    raise ValueError(inst.family)


def stub_p_artifact(inst: CInstance, stale: bool = False) -> str:
    """P's scripted artifact: the answers after the change (honest), or before it (the stale one the checker must flag)."""
    ans = inst.pre if stale else inst.post
    return ("## Report\n\nThe answers below come from the files and pages as they were when I last read them.\n\n```answers\n"
            + json.dumps(ans) + "\n```\n")


__all__ = ["CHANGE_FAMILIES", "CInstance", "Change", "FRESH_RULE", "HARMLESS_SEED", "PROFILE", "check_change",
           "make_change", "stub_answers", "stub_p_artifact"]


if __name__ == "__main__":
    for f in CHANGE_FAMILIES:
        for s in range(5):
            i = make_change(f, s)
            print(f, s, "harmless" if i.harmless else "", i.change.what, "|", json.dumps(i.pre), "→", json.dumps(i.post))
    _ = re
