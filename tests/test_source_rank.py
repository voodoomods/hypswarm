"""A check on a claim that cites a lesser source has to open the better one the record holds. On K1 the fact checker
checked "formally opened by the Mayor in 1889" from the 2004 guide twice in a row, having read the guide and the
retraction list and never the 1887 minutes the record cites on Q1 (BC-250, ho1 and ho2, 2026-11-07)."""
from pathlib import Path

from hypswarm import Seat
from hypswarm.budget import Budget, Meter
from hypswarm.record import LocalRecord
from hypswarm.tools import worker_tools

MINUTES = "archive/council-minutes-1887.md"
GUIDE = "archive/town-guide-2004.md"
SURVEY = "archive/population-survey-2019.md"


def _archive(tmp_path: Path) -> Path:
    root = tmp_path / "work"
    (root / "archive").mkdir(parents=True)
    (root / MINUTES).write_text("Opened to the public on 14 June 1887, without ceremony beyond a short address.\n", encoding="utf-8")
    (root / GUIDE).write_text("Opened with great ceremony by the Mayor in 1889.\n", encoding="utf-8")
    (root / SURVEY).write_text("| 1891 | 4,028 |\n", encoding="utf-8")
    (root / "archive" / "RETRACTIONS.md").write_text(
        "- **Ashby population survey (2019)** — withdrawn by its authors: the 1891 figure double-counted.\n", encoding="utf-8")
    return root


def _record(tmp_path: Path):
    root = _archive(tmp_path)
    rec = LocalRecord(":memory:", [Seat("researcher", "worker"), Seat("checker", "reviewer")])
    inv = rec.start("archive", "Answer from the archive.",
                    [("Q1", "On what date did the footbridge open?"), ("Q3", "Who formally opened the footbridge?")],
                    reviewers=["checker"], profile="knowledge@2")
    return root, rec, inv


def _worker(rec, inv, root, question="Q3"):
    order = rec.issue_work(author="harness", inv=inv, target=rec.resolve(question, inv), assignee="researcher",
                           objective="Answer it.")["order"]
    return {t.name: t.fn for t in worker_tools(rec, Seat("researcher", "worker"), inv, order,
                                               Meter(Budget(max_calls=50)), folder=root)}


def _reviewer(rec, inv, root, node="CL1", watched=True):
    order = rec.issue_work(author="harness", inv=inv, target=rec.resolve(node, inv), assignee="checker",
                           objective=f"Check {node}.")["order"]
    tools = worker_tools(rec, Seat("checker", "reviewer"), inv, order, Meter(Budget(max_calls=50)), folder=root)
    state = tools[-1].fn.__dict__["_state"]
    if watched:
        state["read"] = []
    return {t.name: t.fn for t in tools}["review"], state


def _source(add, kind, url, passage, question):
    out = add("source", {"citation": Path(url).stem, "passage": passage, "retrieved": "2026-11-07", "kind": kind, "url": url},
              [{"rel": "part_of", "to": question}])
    assert out.startswith("added "), out
    return out.split()[1]


def _mayor_claim(rec, inv, root, primary_url=f"file:{MINUTES}", primary_kind="primary"):
    """CL1 cites the guide on Q3; the record also holds the minutes, cited on Q1."""
    w1 = _worker(rec, inv, root, "Q1")
    s_min = _source(w1["graph_add"], primary_kind, primary_url, "Opened to the public on 14 June 1887, without ceremony beyond a short address.", "Q1")
    w3 = _worker(rec, inv, root, "Q3")
    s_guide = _source(w3["graph_add"], "tertiary", f"file:{GUIDE}", "Opened with great ceremony by the Mayor in 1889.", "Q3")
    out = w3["graph_add"]("claim", {"statement": "The footbridge was formally opened by the Mayor in 1889.",
                                    "scope": "the opening of the footbridge, as the 2004 guide tells it", "kind": "finding"},
                          [{"rel": "answers", "to": "Q3"}, {"rel": "cites", "to": s_guide}])
    assert out.startswith("added CL1"), out
    return s_min, s_guide


def _reviews(rec, inv, node="CL1"):
    return [e for e in rec.get(rec.resolve(node, inv))["in"] if e["rel"] == "reviews"]


def test_a_check_that_never_opened_the_primary_source_is_refused(tmp_path):
    root, rec, inv = _record(tmp_path)
    s_min, _ = _mayor_claim(rec, inv, root)
    review, state = _reviewer(rec, inv, root)
    state["read"].append(GUIDE)
    state["read"].append("archive/RETRACTIONS.md")
    out = review("CL1", "checked", "I read the guide and the retraction list.", "No contradictory source found.")
    assert out.startswith("refused: CL1 cites a tertiary source") and f"{s_min} ({MINUTES})" in out, out
    assert f"read_file('{MINUTES}')" in out
    assert not _reviews(rec, inv)


def test_after_reading_it_the_check_is_recorded(tmp_path):
    root, rec, inv = _record(tmp_path)
    _mayor_claim(rec, inv, root)
    review, state = _reviewer(rec, inv, root)
    state["read"] += [GUIDE, f"./{MINUTES}"]
    out = review("CL1", "checked", "I read the guide and the minutes.", "They disagree on the year; the guide is the later summary.")
    assert not out.startswith("refused"), out
    assert len(_reviews(rec, inv)) == 1


def test_an_objection_is_never_held_for_it(tmp_path):
    root, rec, inv = _record(tmp_path)
    _mayor_claim(rec, inv, root)
    review, _ = _reviewer(rec, inv, root)
    out = review("CL1", "objection", "I read the guide.", "It is a tertiary source and gives no evidence of a ceremony.")
    assert not out.startswith("refused"), out
    assert len(_reviews(rec, inv)) == 1


def test_a_claim_on_the_primary_source_needs_no_other_reading(tmp_path):
    root, rec, inv = _record(tmp_path)
    w1 = _worker(rec, inv, root, "Q1")
    s_min = _source(w1["graph_add"], "primary", f"file:{MINUTES}", "Opened to the public on 14 June 1887.", "Q1")
    w3 = _worker(rec, inv, root, "Q3")
    _source(w3["graph_add"], "tertiary", f"file:{GUIDE}", "Opened with great ceremony by the Mayor in 1889.", "Q3")
    out = w1["graph_add"]("claim", {"statement": "The footbridge opened to the public on 14 June 1887.",
                                    "scope": "the opening of the footbridge, from the council minutes", "kind": "finding"},
                          [{"rel": "answers", "to": "Q1"}, {"rel": "cites", "to": s_min}])
    assert out.startswith("added CL1"), out
    review, _ = _reviewer(rec, inv, root)
    out = review("CL1", "checked", "I read the minutes.", "The passage is there as quoted.")
    assert not out.startswith("refused"), out


def test_a_seat_outside_the_worker_loop_is_not_held(tmp_path):
    root, rec, inv = _record(tmp_path)
    _mayor_claim(rec, inv, root)
    review, _ = _reviewer(rec, inv, root, watched=False)
    assert not review("CL1", "checked", "I read the guide and nothing else.", "The passage is as quoted.").startswith("refused")


def test_a_withdrawn_or_remote_better_source_is_not_required(tmp_path):
    root, rec, inv = _record(tmp_path)
    # the survey is secondary and withdrawn; a paper on the web can't be opened with read_file
    rec2 = rec
    w1 = _worker(rec2, inv, root, "Q1")
    out = w1["graph_add"]("source", {"citation": "A later paper", "passage": "Says 1889.", "retrieved": "2026-11-07",
                                     "kind": "primary", "url": "https://example.org/paper"}, [{"rel": "part_of", "to": "Q1"}])
    assert out.startswith("added "), out
    w3 = _worker(rec2, inv, root, "Q3")
    s_guide = _source(w3["graph_add"], "tertiary", f"file:{GUIDE}", "Opened with great ceremony by the Mayor in 1889.", "Q3")
    out = w3["graph_add"]("claim", {"statement": "The footbridge was formally opened by the Mayor in 1889.",
                                    "scope": "the opening of the footbridge, as the 2004 guide tells it", "kind": "finding"},
                          [{"rel": "answers", "to": "Q3"}, {"rel": "cites", "to": s_guide}])
    assert out.startswith("added CL1"), out
    review, state = _reviewer(rec2, inv, root)
    state["read"].append(GUIDE)
    assert not review("CL1", "checked", "I read the guide.", "As quoted.").startswith("refused")


def test_a_bare_path_names_the_same_file(tmp_path):
    root, rec, inv = _record(tmp_path)
    s_min, _ = _mayor_claim(rec, inv, root, primary_url=MINUTES)
    review, state = _reviewer(rec, inv, root)
    state["read"].append(GUIDE)
    assert s_min in review("CL1", "checked", "I read the guide.", "As quoted.")
    state["read"].append(MINUTES)
    assert not review("CL1", "checked", "I read both.", "They disagree.").startswith("refused")
