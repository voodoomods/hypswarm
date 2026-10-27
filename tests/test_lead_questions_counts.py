"""Two fixes from the day-2 scientific runs. A lead's question that names record entries, or repeats an open
question, is an order in disguise (S2, S3, E6 each grew a Q4). A count printed next to its name is confirmed even
when its denominator isn't printed (S2: "n_tutored 80" for {k: 80, n: 600} was flagged CONTRADICTED)."""
from hypswarm.reproduce import check_output
from hypswarm.tools import _not_a_question

LINE = "n_tutored 80 n_eligible_not_tutored 80 n_not_eligible 440"


def test_a_count_printed_beside_its_name_is_confirmed_without_its_denominator():
    vals = {"n_tutored": {"k": 80, "n": 600}, "n_eligible_not_tutored": {"k": 80, "n": 600},
            "n_not_eligible": {"k": 440, "n": 600}}
    out = check_output(vals, LINE)
    assert sorted(out["confirmed"]) == sorted(vals) and not out["contradicted"]


def test_a_different_count_beside_its_name_is_still_contradicted():
    out = check_output({"n_tutored": {"k": 80, "n": 600}}, "n_tutored 81")
    assert out["contradicted"] == ["n_tutored"]
    out = check_output({"mean_gain": {"value": 8.975}}, "mean_gain 9.84")
    assert out["contradicted"] == ["mean_gain"]


EXISTING = [("Q1", "Which of the 20 outcomes differ between the arms at p < 0.05 without correction, and at what p-values?"),
            ("Q2", "After correcting for the 20 outcomes tested (Holm or Bonferroni), which differences remain significant?")]


def test_a_question_naming_record_entries_is_refused():
    why = _not_a_question("Q2 claim: the analyst's T10 must write, on the existing run result RS5, a claim?", EXISTING)
    assert why.startswith("refused") and "Q2" in why and "T10" in why and "rework" in why


def test_a_copy_of_an_open_question_is_refused():
    why = _not_a_question("After correcting for the 20 outcomes tested (Holm or Bonferroni), which differences "
                          "remain significant?", EXISTING)
    assert why.startswith("refused: Q2 already asks this")


def test_a_copy_with_a_clause_added_is_refused():
    """T2 (evening): Q4 was Q3 with "— given the honest out-of-sample, after-cost result …" added."""
    existing = [("Q3", "Should the desk take a paper position on the crossover, or decline?")]
    why = _not_a_question("Should the desk take a paper position on the crossover, or decline — given the honest "
                          "out-of-sample, after-cost result for the best of 20 settings and the risk review's figures?",
                          existing)
    assert why.startswith("refused: Q3 already asks this")
    assert _not_a_question("Would a slower crossover (fast=50, slow=200) survive the costs out of sample?", existing) == ""


def test_a_new_question_is_allowed():
    assert _not_a_question("Is the steps_k difference larger in participants over 60?", EXISTING) == ""


def test_an_exception_ends_on_the_lead_s_decision():
    """A lead that would read forever at an exception gets a last turn of decision tools only (studies S2, day 2:
    three of four escalations were cancelled as undecided after the lead spent its turns on show)."""
    import asyncio

    from hypswarm import Budget, Seat, Task, run
    from hypswarm.providers.stub import StubModel, calls_made
    from hypswarm.scheduler import LEAD_DECIDES

    from .test_alpha import lead_script

    offered: list[list[str]] = []

    def lazy(messages, tools):
        return None

    def reading_lead(messages, tools):
        names = sorted(t.name for t in tools)
        exception = any("EXCEPTION" in m.content for m in messages if m.role == "user")
        if not exception:
            return lead_script(messages, tools)
        offered.append(names)
        if "cancel_work" in names and "show" not in names:
            assert any(m.content == LEAD_DECIDES for m in messages if m.role == "user")
            code = next(m.content for m in messages if m.role == "user" and "EXCEPTION" in m.content).split("order ")[1].split()[0]
            return ("cancel_work", {"order": code, "why": "the worker can't answer it from the files"})
        if "cancel_work" in calls_made(messages):
            return None
        return ("show", {"node": "Q1"})

    r = asyncio.run(run(Task("Nobody can", "A task nobody can do.", [("Q1", "Unanswerable?")]),
                        [Seat("analyst", "worker"), Seat("lead", "lead")],
                        {"worker": StubModel(lazy), "lead": StubModel(reading_lead)}, budget=Budget(max_calls=60)))
    assert ["add", "cancel_work", "rework"] in offered                     # the last turn: decisions only
    assert offered.index(["add", "cancel_work", "rework"]) > 0             # reading was allowed before it
    why = [e.get("why") for e in r.scheduler.events if e["kind"] == "cancelled"]
    assert "undecided by the lead" not in why                              # the lead decided
    assert any(o["status"] == "cancelled" for o in r.orders)


def test_a_refused_last_decision_gets_one_retry():
    """S2 re-run: the lead's last-turn rework was refused and the order was cancelled as undecided."""
    import asyncio

    from hypswarm import Budget, Seat, Task, run
    from hypswarm.providers.stub import StubModel, tool_outputs

    from .test_alpha import lead_script

    def lazy(messages, tools):
        return None

    def clumsy_lead(messages, tools):
        names = sorted(t.name for t in tools)
        exception = next((m.content for m in messages if m.role == "user" and "EXCEPTION" in m.content), "")
        if not exception:
            return lead_script(messages, tools)
        code = exception.split("order ")[1].split()[0]
        if "show" in names:
            return ("show", {"node": "Q1"})
        outs = tool_outputs(messages)
        if outs and outs[-1].startswith("refused") and any("was refused" in m.content for m in messages if m.role == "user"):
            return ("cancel_work", {"order": code, "why": "the worker can't answer it from the files"})
        if not any(o.startswith("refused") for o in outs):
            return ("rework", {"order": code, "missing": "the claim", "done_when": [{"p": "no_such_predicate"}]})
        return None

    r = asyncio.run(run(Task("Nobody can", "A task nobody can do.", [("Q1", "Unanswerable?")]),
                        [Seat("analyst", "worker"), Seat("lead", "lead")],
                        {"worker": StubModel(lazy), "lead": StubModel(clumsy_lead)}, budget=Budget(max_calls=60)))
    why = [e.get("why") for e in r.scheduler.events if e["kind"] == "cancelled"]
    assert "undecided by the lead" not in why and any(o["status"] == "cancelled" for o in r.orders)
