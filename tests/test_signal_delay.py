"""The trading note's timing rule carries the backtest as code: every seat runs the same function, so the as-given and
one-bar-later figures mean the same thing in every record. A signal built from the next close earns a fortune as given
and nothing a bar later; one built only from the past keeps its lead — and a loop that pairs signal[t] with the return
that ended at t (the first version's failure on the box, 2026-11-08) is not what the function computes."""
import random

from hypswarm.profiles import _NOTES, BACKTEST_CODE, get


def _run_note(close, signal, start, fee):
    """Execute the note's code as a seat would paste it."""
    ns = {"close": close, "signal": signal, "start": start, "fee": fee}
    exec(BACKTEST_CODE, ns)          # noqa: S102 — the point is that the pasted text is the recipe
    return ns["oos_return"], ns["oos_return_delayed"], ns["buy_and_hold"]


def _walk(rng, n, drift=lambda t: 0.0):
    close = [100.0]
    for t in range(n - 1):
        close.append(close[-1] * (1 + drift(t) + rng.gauss(0, 0.01)))
    return close


def test_every_seat_on_a_trading_desk_gets_the_code():
    for pid in ("trading@1", "trading@2"):
        assert BACKTEST_CODE in get(pid).notes and "oos_return_delayed" in _NOTES[pid]
    assert "def backtest(close, signal, start, fee, delay=0)" in BACKTEST_CODE


def test_a_signal_built_from_the_next_close_is_gone_one_bar_later():
    rng = random.Random(7)
    close = _walk(rng, 1500)
    signal = [int((close[t + 1] > close[t]) if rng.random() < 0.7 else rng.random() < 0.5) for t in range(1499)] + [0]
    as_given, delayed, hold = _run_note(close, signal, 1000, 0.001)
    assert as_given > hold + 0.5            # looks like an edge as given
    assert delayed < hold + 0.05            # and isn't one a bar later


def test_a_signal_built_from_the_past_keeps_its_lead_one_bar_later():
    rng = random.Random(11)
    close = _walk(rng, 1500, lambda t: 0.003 if (t // 150) % 2 == 0 else -0.003)        # long trends up and down
    signal = [0] * 20 + [int(close[t] > close[t - 20]) for t in range(20, 1500)]
    as_given, delayed, hold = _run_note(close, signal, 1000, 0.001)
    assert as_given > hold and delayed > hold   # the rule doesn't call a real trend look-ahead


def test_the_code_pairs_a_position_with_the_return_after_it_not_the_one_that_ended():
    """signal[t] = 1 exactly when close[t] rose from close[t-1]. Against the return that ended at t this 'earns'
    every up day (the peeking loop the box wrote); against the return after it, on a random walk, it earns nothing."""
    rng = random.Random(3)
    close = _walk(rng, 1200)
    signal = [0] + [int(close[t] > close[t - 1]) for t in range(1, 1200)]
    as_given, delayed, _hold = _run_note(close, signal, 600, 0.0)
    peeking = 1.0
    for t in range(600, 1199):
        if signal[t + 1]:
            peeking *= close[t + 1] / close[t]
    assert peeking - 1 > 1.0                  # the wrong pairing looks like a fortune
    assert abs(as_given) < 0.6 and abs(delayed) < 0.6      # the note's pairing finds no such thing
