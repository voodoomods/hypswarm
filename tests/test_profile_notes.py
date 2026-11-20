"""A seat's note is keyed by profile version, and a new version must not run without one. trading@3, optimization@3
and software@3 (hypgraph 0.8.9 / 0.8.10) only add claim checks, and scientific@3, trading@4 and optimization@4 only
judge preregistration per link; keyed by exact id, every one of them ran with no note, and so did the bare name once it
resolved to the newest version. A version that keeps the seats and stages keeps its predecessor's note; one that
changes them gets none until it has its own, and the test over every shipped profile says so."""
import importlib
from dataclasses import replace

from hypgraph import profiles as gp

from hypswarm import Task, profiles
from hypswarm.profiles import _NOTES


def _note_source(p, registry=None):
    from hypswarm.profiles import _note_source as f  # here: main fails the other tests on what they check
    return f(p, registry)


def _newest(name):
    return max((p for p in gp.PROFILES.values() if p.name == name), key=lambda p: p.version)


def _next_version(name, **changes):
    """A version after the newest of ``name`` that changes only what ``changes`` say (default: nothing but checks)."""
    p = _newest(name)
    return replace(p, version=p.version + 1, about=p.about + " One more check.", **changes)


def test_a_version_that_only_adds_checks_keeps_its_predecessors_note():
    for name in ("scientific", "trading", "optimization", "software", "knowledge"):
        p = _next_version(name)
        reg = {**gp.PROFILES, p.id: p}
        assert _note_source(p, reg) == f"{name}@2", p.id


def test_a_version_with_its_own_note_keeps_it():
    for pid in _NOTES:
        assert _note_source(gp.get(pid)) == pid


def test_a_version_that_changes_the_seats_or_stages_borrows_nothing():
    p = _newest("trading")
    fewer_stages = _next_version("trading", workflow=replace(p.workflow, stages=p.workflow.stages[:-1]))
    other_seats = _next_version("trading", seats=p.seats[:-1])
    for q in (fewer_stages, other_seats):
        assert _note_source(q, {**gp.PROFILES, q.id: q}) is None
    # and the version after a changed one stops there too: it doesn't reach past the change for an older note
    after = replace(fewer_stages, version=fewer_stages.version + 1)
    assert _note_source(after, {**gp.PROFILES, fewer_stages.id: fewer_stages, after.id: after}) is None


def test_every_profile_hypgraph_ships_and_every_bare_name_carries_a_note():
    # a new family, or a version that changes the table, fails here instead of running its seats with no guidance
    for pid, p in gp.PROFILES.items():
        if getattr(p, "deprecated", ""):
            continue                                    # evaluation@1: pin scientific@2 with a claim policy instead
        assert profiles.get(pid).notes, f"{pid} has no seat note: add one to _NOTES"
    for name in {p.name for p in gp.PROFILES.values() if not getattr(p, "deprecated", "")}:
        assert profiles.get(name).notes == profiles.get(_newest(name).id).notes != ""


def test_a_task_pinned_to_trading_at_the_next_version_gets_the_trading_note(monkeypatch):
    t = _next_version("trading")
    monkeypatch.setitem(gp.PROFILES, t.id, t)
    try:
        importlib.reload(profiles)
        assert profiles.get(t.id).notes == _NOTES["trading@2"] and profiles.get("trading").id == t.id
        preamble = Task(title="t", mission="m", questions=[("Q1", "Is there an edge?")], profile=t.id).preamble()
        assert f"PROFILE {t.id}" in preamble and _NOTES["trading@2"] in preamble
    finally:
        monkeypatch.undo()
        importlib.reload(profiles)
    assert t.id not in profiles.PROFILES
