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
    s.r, s.inv, s.inflight, s._pending_lead = rec, "inv", {}, []
    return s


def test_a_complete_record_ends_the_run():
    assert _sched(FakeRecord(True))._done() == "settled"


def test_an_incomplete_record_keeps_working():
    assert _sched(FakeRecord(False))._done() == ""
