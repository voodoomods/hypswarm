"""The trading note's timing rule: backtest a supplied signal as given and one bar later. A signal built from the next
close earns a fortune as given and nothing a bar later; one built only from the past keeps its lead."""
import random

from hypswarm.profiles import _NOTES, get


def _backtest(close, signal, delay=0, start=0, fee=0.001):
    """The note's recipe: position[t] = signal[t - delay] earns close[t+1]/close[t] - 1, fees multiplied in."""
    equity, held = 1.0, 0
    for t in range(start, len(close) - 1):
        pos = signal[t - delay]
        if pos != held:
            equity *= 1 - fee
        held = pos
        if pos:
            equity *= close[t + 1] / close[t]
    return equity - 1


def _walk(rng, n, drift=lambda t: 0.0):
    close = [100.0]
    for t in range(n - 1):
        close.append(close[-1] * (1 + drift(t) + rng.gauss(0, 0.01)))
    return close


def test_every_seat_on_a_trading_desk_reads_the_rule():
    for pid in ("trading@1", "trading@2"):
        assert "oos_return_delayed" in get(pid).notes and "one bar later" in _NOTES[pid]


def test_a_signal_built_from_the_next_close_is_gone_one_bar_later():
    rng = random.Random(7)
    close = _walk(rng, 1500)
    signal = [int((close[t + 1] > close[t]) if rng.random() < 0.7 else rng.random() < 0.5) for t in range(1499)] + [0]
    hold = close[-1] / close[1000] - 1
    assert _backtest(close, signal, 0, 1000) > hold + 0.5            # looks like an edge as given
    assert _backtest(close, signal, 1, 1000) < hold + 0.05           # and isn't one a bar later


def test_a_signal_built_from_the_past_keeps_its_lead_one_bar_later():
    rng = random.Random(11)
    close = _walk(rng, 1500, lambda t: 0.003 if (t // 150) % 2 == 0 else -0.003)        # long trends up and down
    signal = [0] * 20 + [int(close[t] > close[t - 20]) for t in range(20, 1500)]
    hold = close[-1] / close[1000] - 1
    as_given, delayed = _backtest(close, signal, 0, 1000), _backtest(close, signal, 1, 1000)
    assert as_given > hold and delayed > hold                       # the rule doesn't call a real trend look-ahead
