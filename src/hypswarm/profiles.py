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


_NOTES = {
    "scientific@1": "Numbers come from registered results; claims are checked as written.",
    "software@1": "A requirement is verified only by a test the instrument ran: register_run with the exact test command "
                  "as code and print the counts (passed, failed); 'it passes' without that run is refused. Diffs and "
                  "builds are artifacts, by hash.",
    "trading@1": "A thesis is a hypothesis. A backtest result must carry the costs it charged and name its out-of-sample "
                 "window (oos_*). 'Edge' without both is refused. Positions are paper: a sized position with a stop is "
                 "a decision based_on the claim. Never a live order.",
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
    "software@2": "Register the change first: graph_add artifact {sha256, path, kind: 'diff', meta: {base_sha, head_sha, "
                  "files}} part_of the requirement. register_run with the exact test command as code and uses=[the diff]; "
                  "the instrument re-runs it on that head — tests on a superseded head don't count. Then the claim.",
    "trading@2": "Thesis first (a hypothesis answering the question), then the backtest preregistered as an experiment "
                 "(windows, costs, configurations to try; data.expected) BEFORE register_run. The result carries oos_*, "
                 "fees/slippage and trials (configurations tried). After the risk review, a decision based_on the claim: "
                 "kind=position with size, stop, review_date and paper=true — or kind=no_position when the thesis is "
                 "declined. Never a live order.",
    "knowledge@2": "A source carries citation, url|doi, the passage that says it, retrieved (the date you read it) and "
                   "kind (primary/secondary/tertiary); link it part_of the question. The claim cites it. If no source "
                   "answers, register the search as a run with a result (pages read, mentions found) and a claim "
                   "kind=inconclusive derived from it.",
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
