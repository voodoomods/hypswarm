"""The report the harness assembles when the lead's doesn't pass (assemble.py). Found in the change suite: in 13 of 25
record runs the lead never submitted a report the check accepted, while the record held a current, checked claim for
most questions. The fallback reads the answers off those claims; it fills only fields a claim binds, takes a true /
false field only from a boolean, skips stale claims, and is used only when the text passes the record's check."""
import asyncio

from hypswarm import Budget, Seat, run
from hypswarm.assemble import asked_fields, assemble_answers, assembled_report
from hypswarm.providers.stub import StubModel, calls_made, tool_outputs
from hypswarm.record import LocalRecord

from .test_alpha import SEATS, TASK, make_models

H = "harness"


def _record():
    r = LocalRecord(None, [Seat("solver", "worker"), Seat("critic", "reviewer")])
    inv = r.create(author=H, type="investigation", fields={"title": "What does the cheapest assignment cost?",
                   "objective": "Solve the assignment instance and certify the optimum."})["id"]
    return r, inv


def _question(r, inv, code, text):
    return r.create(author=H, type="question", inv=inv, code=code, fields={"text": text})["id"]


def _solve(r, inv, q, values, statement, measurements=None, data=None, check=True):
    run_links = [{"rel": "uses", "to": data, "data": {"role": "data"}}] if data else []
    run_ = r.create(author="solver", type="run", inv=inv, fields={"kind": "agent", "name": "solve", "state": "succeeded"},
                    links=run_links)["id"]
    rs = r.create(author="solver", type="result", inv=inv, fields={"summary": "Solved the instance exactly.",
                  "values": values, "outcome": "positive"}, links=[{"rel": "produced", "from": run_}])
    fields = {"statement": statement, "scope": "The instance as registered."}
    if measurements:
        fields["measurements"] = [m | {"result": rs["id"]} for m in measurements]
    c = r.create(author="solver", type="claim", inv=inv, fields=fields,
                 links=[{"rel": "answers", "to": q}, {"rel": "derived_from", "to": rs["id"]}])["id"]
    if check:
        r.review(author="critic", target=c, verdict="checked", method="Re-solved the instance by enumeration.",
                 notes="Same optimum.")
    return rs["id"], c


def test_asked_fields_and_their_kinds():
    assert asked_fields('Answer as {"cost": <int>, "optimal": true|false}.') == [("cost", "value"), ("optimal", "bool")]
    assert asked_fields('Answer as {"passed": <int>, "total": <int>, "all_pass": true|false}') == \
        [("passed", "value"), ("total", "value"), ("all_pass", "bool")]
    assert asked_fields("What is A's accuracy?") == []


def test_fields_come_from_what_the_claim_binds_and_a_mislabelled_gap_is_not_an_answer():
    r, inv = _record()
    q = _question(r, inv, "Q1", 'What does it cost, and is it optimal? Answer as {"cost": <int>, "optimal": true|false}.')
    _solve(r, inv, q, {"objective": {"value": 40}, "gap": {"value": 0}},
           "The minimum total cost is 40 and the gap to the bound is 0.",
           [{"key": "objective", "name": "cost", "value": 40}, {"key": "gap", "name": "optimal", "value": 0}])
    answers, notes = assemble_answers(r, inv)
    assert answers == {"Q1": {"cost": 40}}                    # "optimal" is a label on the gap, not a boolean
    assert "not bound by it: optimal" in notes[0] and "checked" in notes[0]


def test_a_claim_with_no_measurements_answers_from_its_result_and_the_check_still_decides():
    r, inv = _record()
    q = _question(r, inv, "Q1", 'Do the tests pass? Answer as {"passed": <int>, "all_pass": true|false}.')
    _solve(r, inv, q, {"passed": {"value": 5}, "failed": {"value": 1}, "total": {"value": 6},
                       "all_pass": {"unit": "bool", "value": 0}},
           "On the current head not every test passes.")
    answers, _ = assemble_answers(r, inv)
    assert answers == {"Q1": {"passed": 5, "all_pass": False}}
    # the claim states no count, so the record's check refuses "passed: 5" — and an assembled report must pass it
    assert assembled_report(r, inv) == ""


def test_a_stale_claim_answers_nothing():
    r, inv = _record()
    q = _question(r, inv, "Q1", 'What does it cost? Answer as {"cost": <int>}.')
    a1 = r.create(author="solver", type="artifact", inv=inv, fields={"sha256": "a1" * 32, "path": "instance.csv"})["id"]
    _solve(r, inv, q, {"cost": {"value": 35}}, "The minimum total cost is 35.",
           [{"key": "cost", "name": "cost", "value": 35}], data=a1)
    r.create(author="solver", type="artifact", inv=inv, fields={"sha256": "b2" * 32, "path": "instance.csv"},
             links=[{"rel": "supersedes", "to": a1}])
    answers, notes = assemble_answers(r, inv)
    assert answers == {"Q1": None} and "no current claim" in notes[0]
    assert assembled_report(r, inv) == ""                     # nothing current: no report is assembled


def _refused_lead(messages, tools):
    """A lead whose report the record always refuses: its answer is a number no claim gives."""
    done, outs = calls_made(messages), tool_outputs(messages)
    if "report_facts" not in done:
        return ("report_facts", {})
    if "submit_report" not in done or (outs and outs[-1].startswith("report refused")):
        return ("submit_report", {"text": "## Interpretation\n\nA wins.\n\n```answers\n{\"Q1\": 0.5, \"Q2\": \"yes\"}\n```"})
    return None


def test_the_harness_assembles_the_report_when_the_lead_s_never_passes():
    models = make_models()
    models["lead"] = StubModel(_refused_lead, "refused-lead")
    res = asyncio.run(run(TASK, SEATS, models, record=None, budget=Budget(max_calls=60)))
    assert res.stopped == "settled" and not res.report_accepted and res.report_source == "assembled"
    assert any(e["kind"] == "report_assembled" for e in res.scheduler.events)
    assert res.answers() == {"Q1": {"acc_a": 812}, "Q2": {"a": 812, "b": 800}}
    models = make_models()
    models["lead"] = StubModel(_refused_lead, "refused-lead")
    off = asyncio.run(run(TASK, SEATS, models, record=None, budget=Budget(max_calls=60), assemble_report=False))
    assert off.report_source == "" and "did not submit an interpretation" in off.report


def test_a_lead_s_passing_report_is_the_lead_s():
    res = asyncio.run(run(TASK, SEATS, make_models(), record=None, budget=Budget(max_calls=60)))
    assert res.report_accepted and res.report_source == "lead"
