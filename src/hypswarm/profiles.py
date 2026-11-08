"""
Swarm profiles: a HypGraph governance profile plus the seats and toolkits that usually work under it.

The record side (hypgraph.profiles) decides what counts — predicates, refusals, completion. This side decides who
sits at the table and what they hold: a seat template per role, the toolkits the host must provide, and a note
for every seat's prompt. ``Task(profile="software")`` pins ``software@1`` on the investigation; ``run()`` uses the
profile's seats when none are given and builds its toolkits from the registry.

    from hypswarm import Task, run, toolkits
    toolkits.register("python", my_sandbox_factory)
    result = await run(Task(..., profile="software"), seats=None, models=model, folder=workdir)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from hypgraph import profiles as _gp

from .seats import Seat


@dataclass(frozen=True)
class SwarmProfile:
    id: str                              # the record profile this binds to, e.g. "software@1"
    seats: tuple[Seat, ...]              # default roster
    toolkits: tuple[str, ...] = ()       # registry names every worker gets (the host must register them)
    notes: str = ""                      # appended to the task preamble for every seat
    about: str = ""
    extra: dict[str, object] = field(default_factory=dict)

    @property
    def record_profile(self):  # type: ignore[no-untyped-def]  # hypgraph is untyped here
        return _gp.get(self.id)

    @property
    def workflow(self):  # type: ignore[no-untyped-def]
        """The record profile's workflow (stages, gates, typed shapes), or None for a frozen @1 profile."""
        return getattr(self.record_profile, "workflow", None)


def _seats(p) -> tuple[Seat, ...]:  # type: ignore[no-untyped-def]
    out = []
    for row in p.seats:
        name, role, *takes = row
        out.append(Seat(str(name), str(role), takes=tuple(str(t) for t in takes)))
    return tuple(out)


# Every T1 record on the box (2026-11-07 and 08) holds the same few numbers for one signal: +146 % (as the vendor defines
# it), -4.1 % (each position against the return of the day it was printed, which nobody could trade) and -17 to -18 %
# (traded once the signal could be known). Reviewers checked whichever they reproduced, two of them in one run, and
# nothing said how to line up time. A signal built from the next close earns a fortune as given and nothing a bar later.
# A first version said this in prose (BC-250 df1, 2026-11-08): the seats then wrote their own loops and one paired
# signal[t] with the return that ENDED at t, which on a momentum signal peeks — a genuine edge was reported as look-ahead,
# and a right claim was objected to over a fee convention. Prose doesn't fix a convention; this function does.
BACKTEST_CODE = """def backtest(close, signal, start, fee, delay=0):
    # position[t] = signal[t - delay] earns close[t+1]/close[t] - 1; a change of position multiplies (1 - fee) in
    equity, held = 1.0, 0
    for t in range(start, len(close) - 1):
        pos = signal[t - delay] if t - delay >= 0 else 0
        if pos != held:
            equity *= 1 - fee
        held = pos
        if pos:
            equity *= close[t + 1] / close[t]
    return equity - 1
oos_return = backtest(close, signal, start, fee)                # as the signal says
oos_return_delayed = backtest(close, signal, start, fee, 1)     # one bar later: the signal known a bar late
buy_and_hold = close[-1] / close[start] - 1"""
_TIMING = (" A signal you were given is not trusted for timing, and a backtest of it is this code, pasted as written "
           "(close and signal are the file's columns in date order; start is the first out-of-sample row; fee is the "
           "cost per position change as a fraction):\n" + BACKTEST_CODE + "\nRegister all three values with those "
           "names. A claim about the return states oos_return and oos_return_delayed beside each other and against "
           "buy_and_hold, or the reviewer objects. The reviewer re-runs this same code; another loop is not a check, "
           "and a difference under one point from a fee or window convention is not an objection. Look-ahead means "
           "the lead over buy and hold is gone one bar later (oos_return_delayed at or below buy_and_hold while "
           "oos_return is above it): then there is no edge, and the position is declined. A lead that survives the "
           "bar is not look-ahead; say so, and the position question is decided on oos_return_delayed.")

_NOTES = {
    "scientific@1": "Numbers come from registered results; claims are checked as written.",
    "software@1": "A requirement is verified only by a test the instrument ran: register_run with the exact test command "
                  "as code and print the counts (passed, failed); 'it passes' without that run is refused. Diffs and "
                  "builds are artifacts, by hash.",
    "trading@1": "A thesis is a hypothesis. A backtest result must carry the costs it charged and name its out-of-sample "
                 "window (oos_*). 'Edge' without both is refused. Positions are paper: a sized position with a stop is "
                 "a decision based_on the claim. Never a live order." + _TIMING,
    "knowledge@1": "Every factual claim cites a source node you added (citation, url or doi, the passage). Recall is "
                   "not a source. The report is linted against the record.",
    "optimization@1": "A result reports objective, feasible (true/false) and bound or gap. 'Optimal' without a bound is "
                      "refused — say 'best found' and give the gap.",
    # @2: the discipline's workflow. Each order names the stage the question is in and the gates that move it on.
    "scientific@2": "Each question moves through stages the record derives: a hypothesis with predictions answers it; "
                    "an experiment tests the hypothesis (data.expected) BEFORE any run; register_run executes it; a claim "
                    "with its numbers bound answers the question; a reviewer checks it. Your order names the gates; "
                    "write them in order. An honest 'can't be answered' is a claim kind=inconclusive derived from what "
                    "you did find.",
    "software@2": "With a working folder the record watches it: edit the files and the change registers itself as the "
                  "current head; never graph_add a diff. Without one, register it: graph_add artifact {sha256, path, "
                  "kind: 'diff', meta: {base_sha, head_sha, files}} part_of the requirement. Then register_run with the "
                  "exact test command as code, after your last edit: the instrument re-runs it on that head and reads "
                  "the runner's summary, and tests on a superseded head don't count. Then the claim. Asked what causes "
                  "a failure, say what fails and what the code does, side by side: 'test_x fails on the original; "
                  "compare() compares the parts as strings.' 'because of', 'due to' and 'causes' are refused without an "
                  "experiment that intervened, and rewording them spends your turns.",
    "trading@2": "Thesis first (a hypothesis answering the question), then the backtest preregistered as an experiment "
                 "(windows, costs, configurations to try; data.expected) BEFORE register_run. The result carries oos_*, "
                 "fees/slippage and trials (configurations tried). After the risk review, a decision based_on the claim: "
                 "kind=position with size, stop, review_date and paper=true — or kind=no_position when the thesis is "
                 "declined. Never a live order." + _TIMING,
    "knowledge@2": "A source carries citation, a url or doi, the passage that says it, retrieved (the date you read it) and "
                   "kind (primary/secondary/tertiary); link it part_of the question. The claim cites it. Before you rely "
                   "on a source, writing or reviewing, list what else is there: a retraction, correction or erratum "
                   "outranks the source it names, and a withdrawn source is not evidence; a primary source outranks a "
                   "later summary of it. A table of parts answers a question about the whole: add it up with python, "
                   "register_run the sum with its code, and cite the table. If no source answers, register the search "
                   "as a run with a result (pages read, mentions found) and a claim kind=inconclusive derived from it.",
    "optimization@2": "Register the instance as an artifact {sha256, path, kind: 'instance'} part_of the question, state the "
                      "model as a hypothesis, the solve configuration as an experiment, then register_run with "
                      "uses=[the instance] and values {objective, feasible, bound|gap} (or feasible=false). A verifier "
                      "reviews the result before the claim.",
}

PROFILES: dict[str, SwarmProfile] = {}
for _pid, _p in _gp.PROFILES.items():
    PROFILES[_pid] = SwarmProfile(_pid, _seats(_p), toolkits=("files",), notes=_NOTES.get(_pid, ""), about=_p.about)
for _p in sorted(_gp.PROFILES.values(), key=lambda p: p.version):
    PROFILES[_p.name] = PROFILES[_p.id]         # "software" → the newest version (software@2: the workflow)


def get(name: str) -> SwarmProfile:
    key = str(name or "").strip().lower()
    if key not in PROFILES:
        raise KeyError(f"unknown profile {name!r}; profiles: {', '.join(sorted(k for k in PROFILES if '@' in k))}")
    return PROFILES[key]


def names() -> list[str]:
    return sorted(k for k in PROFILES if "@" in k)


__all__ = ["PROFILES", "SwarmProfile", "get", "names"]
