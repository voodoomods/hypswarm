"""Swarm profiles: a task names a profile; the record pins it; the roster and toolkits come from it; the record
refuses what the profile refuses, and the scheduler's orders carry the profile's predicates."""
import asyncio

import pytest
from hypgraph import Graph

from hypswarm import Budget, Task, profiles, run, toolkits
from hypswarm.messages import Tool
from hypswarm.providers.stub import StubModel, calls_made, tool_outputs

from .test_alpha import _target, lead_script, reviewer_script


def test_profiles_mirror_the_record_and_carry_rosters():
    assert {"scientific@1", "software@1", "trading@1", "knowledge@1", "optimization@1",
            "scientific@2", "software@2", "trading@2", "knowledge@2", "optimization@2"} <= set(profiles.names())
    sw = profiles.get("software")                                   # the name → the newest version: the workflow
    assert sw.id == "software@2" and [s.name for s in sw.seats] == ["implementer", "tester", "reviewer", "lead"]
    assert sw.workflow is not None and [s.name for s in sw.workflow.stages][:3] == ["specified", "implemented", "verified"]
    assert "tests_pass_current" in sw.record_profile.predicates and "files" in sw.toolkits
    assert profiles.get("software@1").workflow is None and profiles.get("software@1").record_profile.predicates == ("tests_pass",)
    with pytest.raises(KeyError):
        profiles.get("alchemy")


def test_toolkit_registry_builds_by_name_and_fails_loudly(tmp_path):
    calls = []
    toolkits.register("echo_test", lambda ctx: [Tool.from_function(lambda text: calls.append(text) or text, name="echo")],
                      "a test bundle")
    assert "echo_test" in toolkits.names() and toolkits.describe()["echo_test"] == "a test bundle"
    tools = toolkits.build(["echo_test", "files"], toolkits.ToolContext(record=None, inv="", folder=None))
    assert [t.name for t in tools] == ["echo"]                  # files needs a folder; without one it adds nothing
    with pytest.raises(KeyError, match="no toolkit 'python'"):
        toolkits.build(["python"], toolkits.ToolContext(record=None, inv="", folder=None))


def knowledge_worker(messages, tools):
    """Adds a source, then a claim that cites it, in the knowledge profile."""
    done = calls_made(messages)
    outs = tool_outputs(messages)
    if any("return_work now" in o for o in outs) and "return_work" not in done:
        return ("return_work", {"note": "sourced"})
    if "graph_add" not in done:
        return ("graph_add", {"type": "source", "fields": {"citation": "An encyclopaedia entry on the treaty.",
                                                           "url": "https://example.org/treaty", "passage": "signed in 1648",
                                                           "retrieved": "2026-10-26", "kind": "secondary"},
                              "links": [{"rel": "part_of", "to": _target(messages)}]})
    if done.count("graph_add") == 1:
        return ("graph_add", {"type": "claim", "fields": {"statement": "The treaty was signed in 1648.",
                                                          "scope": "The Peace of Westphalia, 1648, as a date.", "kind": "finding"},
                              "links": [{"rel": "answers", "to": _target(messages)}, {"rel": "cites", "to": "S1"}]})
    return None


def test_knowledge_profile_run_pins_profile_and_needs_sources(tmp_path):
    task = Task(title="When was it signed", mission="Date the treaty from sources.",
                questions=[("Q1", "When was the treaty signed?")], profile="knowledge")
    models = {"worker": StubModel(knowledge_worker, "w"), "reviewer": StubModel(reviewer_script, "r"), "lead": StubModel(lead_script, "l")}
    path = tmp_path / "k.hypgraph"
    res = asyncio.run(run(task, None, models, record=path, budget=Budget(max_calls=40)))   # seats from the profile
    assert res.stopped == "settled"
    g = Graph(str(path))
    try:
        assert g.get(res.inv)["body"]["profile"] == "knowledge@2"
        assert {o["assignee"] for o in g.orders(res.inv)} <= {"researcher", "fact_checker"}
        first = g.orders(res.inv)[0]
        text = g.order_text(first["id"])
        assert "source_quoted" in text and "sourced" in text and "is at stage 'sourced'" in text   # the stage's gates are the order's done-when
        c = g.completion(res.inv)
        assert c["profile"] == "knowledge@2" and c["complete"]
        assert all(x["complete"] for x in g.stages(res.inv))
    finally:
        g.close()
    assert "PROFILE knowledge@2" in task.preamble() and "kind=inconclusive" in task.preamble()


def lazy_edge_worker(messages, tools):
    """Claims an edge from an in-sample result without costs: refused twice, then returns honestly."""
    done = calls_made(messages)
    outs = tool_outputs(messages)
    if any("return_work now" in o for o in outs) and "return_work" not in done:
        return ("return_work", {"note": "done"})
    if "register_run" not in done:
        return ("register_run", {"name": "backtest", "result_summary": "Backtested the thesis in sample.",
                                 "values": {"return": {"value": 0.31}, "sharpe": {"value": 1.4}}})
    if done.count("register_run") == 1 and "return_work" not in done:
        return ("return_work", {"note": "the result was refused: no costs"})
    return None


def test_trading_profile_refuses_a_costless_backtest():
    task = Task(title="Edge", mission="Does the strategy have an edge?", questions=[("Q1", "Is there an edge after costs?")],
                profile="trading")
    models = {"worker": StubModel(lazy_edge_worker, "w"), "reviewer": StubModel(reviewer_script, "r"), "lead": StubModel(lead_script, "l")}
    res = asyncio.run(run(task, None, models, record=None, budget=Budget(max_calls=40)))
    refusals = [row["out"] for w in res.scheduler.workers for row in w.tool_log if "BACKTEST_WITHOUT_COSTS" in row["out"]]
    assert refusals, [row["out"][:120] for w in res.scheduler.workers for row in w.tool_log]
    assert [s.name for s in profiles.get("trading").seats] == ["quant", "risk", "lead"]
    assert res.stopped in ("stuck", "settled")                 # no edge was ever accepted into the record
    assert not any(q["status"] == "settled" for q in res.board)
