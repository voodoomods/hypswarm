"""A run ends when the record says the investigation is complete. In studies T2 the trading desk declined once, the
record's completion criteria were all met, and the scheduler still spent the rest of the budget reworking Q3's own
`positioned` gate (which wanted a decision based on Q3's claim, written after the desk had decided)."""
from hypswarm.scheduler import Scheduler


class FakeRecord:
    def __init__(self, complete: bool):
        self.complete = complete

    def stages(self, inv):
        return [{"question": "q1", "code": "Q1", "workflow": True, "complete": True},
                {"question": "q3", "code": "Q3", "workflow": True, "complete": False, "stage": "positioned"}]

    def completion(self, inv):
        return {"complete": self.complete, "pinned": True, "criteria": []}

    def orders(self, inv):
        return [{"code": "T10", "status": "open"}]


def _sched(rec):
    s = Scheduler.__new__(Scheduler)
    s.r, s.inv, s.inflight, s._pending_lead, s._stalled = rec, "inv", {}, [], set()
    return s


def test_a_complete_record_ends_the_run():
    assert _sched(FakeRecord(True))._done() == "settled"


def test_an_incomplete_record_keeps_working():
    assert _sched(FakeRecord(False))._done() == ""


def test_a_settled_question_whose_gates_stalled_ends_the_run():
    s = _sched(FakeRecord(False))
    s._stalled = {"q3"}
    assert s._done() == "settled"


class StalledRecord:
    """Q1 is settled on the board, and its workflow still wants an experiment that tests a hypothesis on it."""

    def question_board(self, inv):
        return [{"id": "q1", "code": "Q1", "status": "settled", "answers": []}]

    def orders(self, inv, **_):
        return []

    def get(self, nid):
        return {"body": {"text": "What is A's accuracy?"}}


def test_a_settled_question_gets_one_order_to_repair_its_gates_then_no_more():
    s = _sched(StalledRecord())
    s._after_settled, events, issued = {}, [], []
    s.workers = []
    s._pick_for_stage = lambda *a, **k: "analyst"
    s._issue = lambda seat, target, objective, gates: issued.append(target) or True
    s._ev = lambda kind, **kw: events.append(kind)
    gate = {"gate": "preregistered", "met": False, "optional": False, "stage": "preregistered", "who": "worker",
            "why": "no experiment tests a hypothesis on Q1"}
    row = {"question": "q1", "code": "Q1", "complete": False, "index": 3, "of": 8, "profile": "scientific@2",
           "gates": [gate]}
    for _ in range(3):
        s._assign_from_stages([row])
    assert issued == ["q1"] and events.count("stage_stalled") == 1 and s._stalled == {"q1"}
