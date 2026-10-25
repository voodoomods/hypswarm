"""The identity boundary: a served record with write tokens. The swarm's client carries a token bound to the
harness and its seats; a client with the wrong token, or none, is refused before any write; an outside seat's
token can't act as the harness."""
import asyncio
import threading

import pytest
from hypgraph import Graph, Policy
from hypgraph.server import make_server, parse_tokens

from hypswarm import Budget, HttpRecord, Seat, run
from hypswarm.http_record import AuthError
from hypswarm.record import HARNESS

from .test_alpha import TASK, make_models

SWARM = "swarm-token-0123456789abcdef"
OUTSIDER = "outsider-token-0123456789abc"


@pytest.fixture
def served(tmp_path):
    g = Graph(str(tmp_path / "served.hypgraph"), policy=Policy(extra_reserved={HARNESS}))
    tokens = parse_tokens([f"{SWARM}={HARNESS},analyst,stats,critic,lead", f"{OUTSIDER}=nicolas"])
    srv = make_server(g, port=0, writable=True, tokens=tokens)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", tmp_path / "served.hypgraph"
    srv.shutdown()


def test_the_swarm_runs_with_its_token(served):
    url, path = served
    seats = [Seat("analyst", "worker", takes=("accuracy",)), Seat("stats", "worker", takes=("significant",)),
             Seat("critic", "reviewer"), Seat("lead", "lead")]
    rec = HttpRecord(url, token=SWARM)
    try:
        res = asyncio.run(run(TASK, seats, make_models(), record=rec, budget=Budget(max_calls=60)))
    finally:
        rec.close()
    assert res.stopped == "settled" and res.report_accepted
    g = Graph(str(path))
    try:
        assert g.verify()["ok"]
        assert {o["assignee"] for o in g.orders(res.inv)} <= {"analyst", "stats", "critic"}
    finally:
        g.close()


def test_no_token_and_wrong_token_are_auth_errors(served):
    url, _ = served
    for rec in (HttpRecord(url), HttpRecord(url, token="not-a-known-token-0123456789")):
        try:
            with pytest.raises(AuthError):
                rec.start("A task.", "An objective.", [("Q1", "What is it?")])
        finally:
            rec.close()


def test_an_outside_token_cannot_act_as_the_harness(served):
    url, _ = served
    rec = HttpRecord(url, token=OUTSIDER)
    try:
        with pytest.raises(AuthError, match="harness"):
            rec.start("A task.", "An objective.", [("Q1", "What is it?")])     # start writes as the harness
        inv = rec.create(author="nicolas", type="investigation",
                         fields={"title": "Nicolas's own investigation.", "objective": "Something."})["id"]
        with pytest.raises(AuthError):
            rec.issue_work(author=HARNESS, inv=inv, target=inv, assignee="nicolas", objective="Do a thing.")
    finally:
        rec.close()
