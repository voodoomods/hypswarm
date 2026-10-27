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


def test_a_new_question_is_allowed():
    assert _not_a_question("Is the steps_k difference larger in participants over 60?", EXISTING) == ""
