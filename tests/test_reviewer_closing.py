"""A reviewer's order ends on its verdict, not its turn limit. Real-model reviewers re-ran a claim's code turn after
turn and ran out of turns with no review (studies E6: one review in five reviewer orders). The order's last two
turns offer only `review`, with a note saying so."""
import asyncio

from hypswarm import Budget, Seat, run
from hypswarm.providers.stub import StubModel, calls_made, tool_outputs
from hypswarm.worker import CLOSING_REVIEW

from .test_alpha import TASK, _target, make_models

OFFERED: list[list[str]] = []
NOTED: list[bool] = []


def browsing_reviewer(messages, tools):
    """Reads the claim forever, and reviews only when review is the one tool it is offered."""
    names = [t.name for t in tools]
    OFFERED.append(names)
    done = calls_made(messages)
    if any("return_work now" in o for o in tool_outputs(messages)) and "return_work" not in done:
        return ("return_work", {"note": "checked"})
    if names == ["review"]:
        NOTED.append(any(CLOSING_REVIEW in str(getattr(m, "content", "")) for m in messages))
        return ("review", {"node": _target(messages), "verdict": "checked", "method": "Recounted from items.csv.",
                           "notes": "The numbers hold as stated."})
    if "review" in done:
        return None
    return ("show", {"node": _target(messages)})


def test_the_last_turns_offer_only_review():
    OFFERED.clear()
    NOTED.clear()
    models = make_models()
    models["reviewer"] = StubModel(browsing_reviewer, "browsing-reviewer")
    seats = [Seat("analyst", "worker", takes=("accuracy", "question")), Seat("stats", "worker", takes=("significant",)),
             Seat("critic", "reviewer", max_turns=6), Seat("lead", "lead")]
    res = asyncio.run(run(TASK, seats, models, record=None, budget=Budget(max_calls=80)))
    assert res.stopped == "settled"
    assert ["review"] in OFFERED                                    # closing turns happened
    first = OFFERED.index(["review"])
    assert first >= 4 and all("show" in o for o in OFFERED[:4])     # browsing was allowed until the last two turns
    assert NOTED and all(NOTED)                                     # and the reviewer was told why
    assert all(q["status"] == "settled" for q in res.board)
