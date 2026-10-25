"""An external seat: a person or another agent takes orders through the HypGraph MCP server while the scheduler
runs. The scheduler only waits; the record is the whole interface between them."""
import asyncio
import json

import pytest

from hypswarm import Budget, Seat, Task, run
from hypswarm.providers.stub import StubModel

from .test_alpha import TASK, lead_script, reviewer_script


def test_an_external_seat_works_orders_over_mcp(tmp_path):
    fastmcp = pytest.importorskip("fastmcp")
    from hypgraph.mcp import build

    db = tmp_path / "e.hypgraph"
    seats = [Seat("nicolas", "worker", external=True), Seat("critic", "reviewer"), Seat("lead", "lead")]
    models = {"reviewer": StubModel(reviewer_script), "lead": StubModel(lead_script)}

    async def go():
        run_task = asyncio.create_task(run(TASK, seats, models, record=db, budget=Budget(max_calls=40),
                                           lease_minutes=15, external_poll_s=0.05))
        await asyncio.sleep(0.2)                                      # the record exists; orders are issued
        server = build(str(db), author="nicolas")                     # how a person's agent would connect
        text = lambda r: r.content[0].text
        async with fastmcp.Client(server) as c:
            last = ""
            for _ in range(2):                                        # one external worker: two orders in turn
                for _try in range(100):
                    mine = text(await c.call_tool("my_work", {}))
                    if "WORK ORDER" in mine and mine.split()[2] != last:
                        break
                    await asyncio.sleep(0.05)
                assert "WORK ORDER" in mine
                code = last = mine.split()[2]
                q = next(l for l in mine.splitlines() if l.startswith("TARGET")).split()[1]
                vals = ({"acc_a": {"k": 812, "n": 1000}, "seed": {"value": 7}} if q == "Q1" else
                        {"a": {"k": 812, "n": 1000}, "b": {"k": 800, "n": 1000}, "seed": {"value": 11}})
                reg = text(await c.call_tool("register_run", {"name": f"count for {q}", "command": "python count.py",
                                                              "result_summary": f"Counted the items for {q}.",
                                                              "result_values": vals}))
                assert "Result RS" in reg and "your work orders" in reg.lower()
                stmt = ("A is right on 812 of 1000 items." if q == "Q1" else
                        "A is not significantly more accurate than B (812 of 1000 vs 800 of 1000).")
                added = text(await c.call_tool("add", {"type": "claim", "fields": {"statement": stmt, "scope": "The 1000 paired items."},
                                                       "links": [{"rel": "answers", "to": q}]}))
                assert "return_work now" in added
                back = text(await c.call_tool("return_work", {"order": code, "note": "done by hand"}))
                assert "every predicate met" in back
        return await run_task
    r = asyncio.run(go())
    assert r.stopped == "settled" and {q["status"] for q in r.board} == {"settled"}
    assert r.report_accepted
    ext = [w for w in r.scheduler.workers if w.seat == "nicolas"]
    assert len(ext) == 2 and all(w.returned and w.calls == 0 and not w.returned_by_record for w in ext)
    assert r.usage["calls"] == r.scheduler.lead_calls + sum(w.calls for w in r.scheduler.workers)   # no model calls for the person
    cfg = json.dumps(r.scheduler.events)
    assert '"external": true' in cfg


def test_a_lease_that_runs_out_is_returned_on_the_seats_behalf(tmp_path):
    seats = [Seat("ghost", "worker", external=True), Seat("lead", "lead")]
    models = {"lead": StubModel(lead_script)}
    r = asyncio.run(run(Task("Nobody comes", "A task whose external seat never shows up.",
                             [("Q1", "Does anyone ever take this order?")]),
                        seats, models, record=tmp_path / "g.hypgraph", budget=Budget(max_calls=20),
                        external_poll_s=0.02, external_timeout_s=0.1))
    ghosts = [w for w in r.scheduler.workers if w.seat == "ghost"]
    assert ghosts and all(w.returned_by_record and w.stopped == "lease" and w.calls == 0 for w in ghosts)
    kinds = [e["kind"] for e in r.scheduler.events]
    assert kinds.count("rework") == 2 and "escalate" in kinds          # the record did everything but decide
    assert r.stopped == "stuck"                                        # honest end: nothing settled
    assert not r.report_accepted and "## Facts" in r.report            # the stub lead cited CL1, which doesn't exist:
    assert "did not submit" in r.report                                # the record refused it and the facts stand alone


def test_external_seats_need_no_model_and_show_in_config(tmp_path):
    seats = [Seat("nicolas", "worker", external=True), Seat("lead", "lead")]
    hint = seats[0].mcp_hint("study.hypgraph")
    assert hint.startswith("hypgraph --db study.hypgraph --as nicolas mcp")
