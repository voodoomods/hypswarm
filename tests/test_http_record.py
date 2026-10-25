"""One record server, stateless workers over HTTP: the swarm runs against `hypgraph serve --writable` with no
Graph object in the harness process. The same test as the in-process swarm, through the wire."""
import asyncio
import threading

from hypgraph import Graph
from hypgraph.server import make_server

from hypswarm import Budget, HttpRecord, Task, run

from .test_alpha import SEATS, TASK, make_models


def _served(path):
    Graph(str(path)).close()                                   # the file must exist before the server opens it
    srv = make_server(str(path), port=0, writable=True)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def test_a_swarm_runs_against_a_served_record(tmp_path):
    srv, url = _served(tmp_path / "served.hypgraph")
    try:
        rec = HttpRecord(url)
        r = asyncio.run(run(TASK, SEATS, make_models(), record=rec, budget=Budget(max_calls=60)))
        assert r.stopped == "settled" and r.record_path == url
        assert {q["code"]: q["status"] for q in r.board} == {"Q1": "settled", "Q2": "settled"}
        assert r.report_accepted and r.answers() == {"Q1": 0.812, "Q2": "no"}
        assert all(o["status"] == "accepted" for o in r.orders) and r.scheduler.lead_calls == 2
        rec.close()
        g = Graph(str(tmp_path / "served.hypgraph"))          # the server's file holds everything, verifiably
        assert g.verify_chain()["ok"] and len(g.orders(r.inv)) == 4
        runs = [n for n in g.search("hypswarm run", type="run", inv=r.inv)]
        assert runs and g.get(runs[0]["id"])["body"]["state"] == "succeeded"
    finally:
        srv.shutdown()


def test_the_wire_refuses_what_the_record_refuses(tmp_path):
    srv, url = _served(tmp_path / "r.hypgraph")
    try:
        rec = HttpRecord(url)
        inv = rec.start("Over the wire", "A record served over HTTP refuses the same overclaims.", [("Q1", "Does it refuse?")])
        import pytest
        from hypgraph import GraphError
        with pytest.raises(GraphError, match="ABSOLUTE_WITHOUT_COUNT"):
            rec.create(author="analyst", type="claim", inv=inv, fields={"statement": "It never fails.", "scope": "Every call so far."})
        with pytest.raises(GraphError, match="reserved"):
            rec.create(author="lab", type="question", inv=inv, fields={"text": "Can the lab write over the wire?"})
        with pytest.raises(KeyError):
            rec.get("n000000000000")
        o = rec.issue_work(author="harness", inv=inv, target="Q1", assignee="analyst", objective="Answer Q1 honestly.")
        assert o["code"] == "T1" and "WORK ORDER" in rec.order_text(o["order"])
        assert rec.check_work(o["order"])["all_met"] is False
        assert rec.question_board(inv)[0]["status"] == "in progress"
        rec.close()
    finally:
        srv.shutdown()


def test_task_notes_reach_the_served_preamble():
    t = Task("Short", "A mission statement that is long enough.", [("Q1", "A question long enough?")], notes="Use python.")
    assert "NOTES\nUse python." in t.preamble()
