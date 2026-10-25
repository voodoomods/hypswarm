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
}

PROFILES: dict[str, SwarmProfile] = {}
for _pid, _p in _gp.PROFILES.items():
    PROFILES[_pid] = SwarmProfile(_pid, _seats(_p), toolkits=("files",), notes=_NOTES.get(_pid, ""), about=_p.about)
    PROFILES[_p.name] = PROFILES[_pid]          # "software" → the current version


def get(name: str) -> SwarmProfile:
    key = str(name or "").strip().lower()
    if key not in PROFILES:
        raise KeyError(f"unknown profile {name!r}; profiles: {', '.join(sorted(k for k in PROFILES if '@' in k))}")
    return PROFILES[key]


def names() -> list[str]:
    return sorted(k for k in PROFILES if "@" in k)


__all__ = ["PROFILES", "SwarmProfile", "get", "names"]
