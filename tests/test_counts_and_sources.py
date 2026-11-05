"""What the box's third sweep showed (BC-250, 2026-11-05): a test run has to bring its own count, a sampled number isn't
a contradiction, and a file another file withdraws can't be cited."""
import asyncio
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from hypswarm import Seat, Task
from hypswarm.budget import Budget, Meter
from hypswarm.record import LocalRecord
from hypswarm.reproduce import TESTS_KEY, check_output, reproduce_result
from hypswarm.scheduler import Scheduler
from hypswarm.tools import implied_uses, worker_tools
from hypswarm.world import seed_baseline, withdrawn_by

BROKEN = b"def add(a, b):\n    return a - b\n"
FIXED = b"def add(a, b):\n    return a + b\n"
TEST = (b"from calc import add\n\n\ndef test_one():\n    assert add(1, 1) == 2\n\n\n"
        b"def test_two():\n    assert add(0, 0) == 0\n\n\ndef test_three():\n    assert add(2, 0) == 2\n")
RUN_TESTS = "import subprocess, sys\nprint(subprocess.run([sys.executable, '-m', 'pytest', '-q', 'test_calc.py'], " \
            "capture_output=True, text=True).stdout)"


def _record(tmp_path: Path, code: bytes = FIXED, profile: str = "software@2"):
    work = tmp_path / "work"
    work.mkdir()
    (work / "calc.py").write_bytes(code)
    (work / "test_calc.py").write_bytes(TEST)
    files = {"calc.py": BROKEN, "test_calc.py": TEST}
    task = Task(title="calc", mission="Fix the tests.", profile="software", baseline=True, files=files,
                questions=[("Q1", "Which tests fail on the original calc.py?", "measure"),
                           ("Q2", "Do all tests pass on the changed calc.py?")])
    rec = LocalRecord(":memory:", [Seat("tester", "worker"), Seat("reviewer", "reviewer")])
    inv = rec.start(task.title, task.mission, task.questions, files=files, reviewers=["reviewer"], profile=profile)
    return work, rec, inv


def _python(work: Path):
    # no bytecode: BROKEN and FIXED are the same size, and a swap within a second reads as unchanged to the .pyc check,
    # so a re-run could score the old code (one CI job in six, 2026-11-05)
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}

    def run(code: str) -> str:
        p = subprocess.run([sys.executable, "-c", code], cwd=work, capture_output=True, text=True, check=False, env=env)
        return p.stdout + ("\n[stderr]\n" + p.stderr if p.stderr.strip() else "")
    return run


def _tools(rec, inv, question="Q2", **kw):
    order = rec.issue_work(author="harness", inv=inv, target=rec.resolve(question, inv), assignee="tester",
                           objective="Run the tests.")["order"]
    return {t.name: t.fn for t in worker_tools(rec, Seat("tester", "worker"), inv, order, Meter(Budget(max_calls=50)), **kw)}


def test_a_passing_run_can_say_all_tests_pass(tmp_path):
    work, rec, inv = _record(tmp_path)
    reg = _tools(rec, inv, run_code=_python(work))["register_run"]
    out = reg(name="tests", result_summary="pytest on the changed calc.py", code=RUN_TESTS, answers="Q2",
              claim="All tests in test_calc.py pass on the changed calc.py.")
    assert "→ claim CL1" in out, out
    res = rec.get(rec.resolve("RS1", inv))["body"]
    assert res["values"][TESTS_KEY] == {"k": 3, "n": 3} and res["outcome"] == "positive"


def test_a_claim_added_on_its_own_finds_the_count_too(tmp_path):
    work, rec, inv = _record(tmp_path)
    tools = _tools(rec, inv, run_code=_python(work))
    tools["register_run"](name="tests", result_summary="pytest on the changed calc.py", code=RUN_TESTS)
    out = tools["graph_add"]("claim", {"statement": "All tests in test_calc.py pass on the changed calc.py.",
                                       "scope": "pytest on the changed calc.py"},
                             [{"rel": "answers", "to": "Q2"}, {"rel": "derived_from", "to": "RS1"}])
    assert out.startswith("added CL1"), out


def test_all_pass_on_a_failing_run_is_refused_as_false(tmp_path):
    work, rec, inv = _record(tmp_path, BROKEN)
    reg = _tools(rec, inv, run_code=_python(work))["register_run"]
    out = reg(name="tests", result_summary="pytest on the current calc.py", code=RUN_TESTS, answers="Q2",
              claim="All tests in test_calc.py pass on the changed calc.py.")
    assert "claim refused" in out
    res = rec.get(rec.resolve("RS1", inv))["body"]
    assert res["values"][TESTS_KEY] == {"k": 2, "n": 3} and res["outcome"] == "negative"


def test_a_seats_own_count_stands_only_if_the_runner_agrees():
    assert check_output({TESTS_KEY: {"k": 6, "n": 6}}, "collected 6 items\n6 passed in 0.1s")["ok"]
    out = check_output({TESTS_KEY: {"k": 6, "n": 6}}, "collected 6 items\n1 failed, 5 passed in 0.1s")
    assert out["contradicted"] == [TESTS_KEY] and not out["ok"]


def test_no_runner_summary_no_count(tmp_path):
    _, rec, inv = _record(tmp_path)
    reg = _tools(rec, inv, run_code=lambda code: "nothing to see")["register_run"]
    reg(name="tests", result_summary="pytest on the changed calc.py", code=RUN_TESTS)
    assert TESTS_KEY not in rec.get(rec.resolve("RS1", inv))["body"].get("values", {})


def test_the_rerun_of_a_count_judges_it_by_the_runner(tmp_path):
    work, rec, inv = _record(tmp_path)
    py = _python(work)
    _tools(rec, inv, run_code=py)["register_run"](name="tests", result_summary="pytest on the changed calc.py",
                                                  code=RUN_TESTS)
    res = rec.resolve("RS1", inv)
    (work / "calc.py").write_bytes(BROKEN)
    out = asyncio.run(reproduce_result(rec, inv, res, py))
    lab = rec.get(rec.resolve(out["result"], inv))["body"]
    assert lab["outcome"] == "negative" and lab["values"] == {"passed": 2, "failed": 1}


def test_a_test_runner_in_a_subprocess_doesnt_run_the_original_by_sys_path(tmp_path):
    work, rec, inv = _record(tmp_path)
    seed_baseline(rec, inv, work, {"calc.py": BROKEN, "test_calc.py": TEST})
    reg = _tools(rec, inv, "Q1", run_code=_python(work))["register_run"]
    out = reg(name="tests", result_summary="pytest on the original", code="import sys\nsys.path.insert(0, '_base')\n" + RUN_TESTS,
              answers="Q1")
    assert out.startswith("refused: Q1 asks about the original")


def test_a_test_runner_that_names_the_kept_file_runs_the_original(tmp_path):
    work, rec, inv = _record(tmp_path)
    seed_baseline(rec, inv, work, {"calc.py": BROKEN, "test_calc.py": TEST})
    reg = _tools(rec, inv, "Q1", run_code=_python(work))["register_run"]
    code = RUN_TESTS.replace("'test_calc.py'", "'_base/test_calc.py'")
    assert not reg(name="tests", result_summary="pytest on the original", code=code, answers="Q1").startswith("refused")
    res = rec.get(rec.resolve("RS1", inv))["body"]
    assert res["values"][TESTS_KEY] == {"k": 2, "n": 3}, "the kept test imports the kept calc.py, not the fixed one"


def test_running_inside_the_kept_folder_is_the_original_too(tmp_path):
    work, rec, inv = _record(tmp_path)
    seed_baseline(rec, inv, work, {"calc.py": BROKEN, "test_calc.py": TEST})
    reg = _tools(rec, inv, "Q1")["register_run"]
    code = RUN_TESTS.replace("capture_output=True", "cwd='_base', capture_output=True")
    assert not reg(name="tests", result_summary="pytest on the original", code=code, answers="Q1").startswith("refused")


def _drawn(tmp_path, printed, value=100):
    _, rec, inv = _record(tmp_path)
    tools = _tools(rec, inv)
    tools["register_run"](name="draw", result_summary="repeats in a sample", values={"repeats": value}, code="print('x')")
    out = iter(printed)
    return rec, asyncio.run(reproduce_result(rec, inv, rec.resolve("RS1", inv), lambda code: next(out))), inv


def test_a_count_that_moves_between_runs_is_a_draw(tmp_path):
    rec, out, inv = _drawn(tmp_path, ["repeats 108", "repeats 95", "repeats 102"])
    assert out["ok"] and not out["contradicted"] and out["confirmed"] == ["repeats"]
    assert "varies from run to run" in rec.get(rec.resolve(out["run"], inv))["body"]["note"]


def test_a_steady_wrong_number_stays_contradicted(tmp_path):
    _, out, _ = _drawn(tmp_path, ["repeats 108", "repeats 108", "repeats 108"])
    assert out["contradicted"] == ["repeats"] and not out["ok"]


def test_a_number_far_from_the_draws_stays_contradicted(tmp_path):
    _, out, _ = _drawn(tmp_path, ["repeats 108", "repeats 95", "repeats 102"], value=400)
    assert out["contradicted"] == ["repeats"]


def _archive(tmp_path):
    a = tmp_path / "archive"
    a.mkdir()
    (a / "population-survey-2019.md").write_text("# Ashby population survey (2019)\n\n1891: 4,028\n", encoding="utf-8")
    (a / "census-1891.csv").write_text("parish,persons\nSt Anne,575\n", encoding="utf-8")
    (a / "RETRACTIONS.md").write_text("- **Ashby population survey (2019)** withdrawn by its authors: use the census.\n",
                                      encoding="utf-8")
    return tmp_path


def test_a_withdrawn_file_is_found_by_its_name(tmp_path):
    root = _archive(tmp_path)
    assert withdrawn_by(root, "file:archive/population-survey-2019.md").startswith("archive/RETRACTIONS.md: ")
    assert withdrawn_by(root, "archive/population-survey-2019.md").startswith("archive/RETRACTIONS.md: ")


def test_a_file_nobody_withdraws_stands(tmp_path):
    root = _archive(tmp_path)
    assert withdrawn_by(root, "file:archive/census-1891.csv") == ""
    assert withdrawn_by(root, "https://example.org/x") == ""
    assert withdrawn_by(None, "file:archive/population-survey-2019.md") == ""


def test_one_word_of_a_name_isnt_enough(tmp_path):
    (tmp_path / "paper.md").write_text("a paper\n", encoding="utf-8")
    (tmp_path / "other.md").write_text("Another paper was withdrawn.\n", encoding="utf-8")
    assert withdrawn_by(tmp_path, "file:paper.md") == ""


def test_a_withdrawn_source_cant_be_added(tmp_path):
    root = _archive(tmp_path)
    rec = LocalRecord(":memory:", [Seat("researcher", "worker"), Seat("checker", "reviewer")])
    inv = rec.start("archive", "Answer from the archive.", [("Q1", "What was the population in 1891?")],
                    reviewers=["checker"], profile="knowledge@2")
    order = rec.issue_work(author="harness", inv=inv, target=rec.resolve("Q1", inv), assignee="researcher",
                           objective="Find the source.")["order"]
    add = {t.name: t.fn for t in worker_tools(rec, Seat("researcher", "worker"), inv, order,
                                              Meter(Budget(max_calls=50)), folder=root)}["graph_add"]
    fields = {"citation": "Ashby population survey", "passage": "1891: 4,028", "retrieved": "2026-11-05",
              "kind": "secondary", "url": "file:archive/population-survey-2019.md"}
    out = add("source", fields)
    assert out.startswith("refused: archive/RETRACTIONS.md: ") and "withdrawn source is not evidence" in out
    assert add("source", {**fields, "citation": "1891 census", "passage": "St Anne,575", "kind": "primary",
                          "url": "file:archive/census-1891.csv"}).startswith("added ")


def test_a_run_on_the_kept_files_doesnt_use_the_head(tmp_path):
    work, rec, inv = _record(tmp_path)
    seed_baseline(rec, inv, work, {"calc.py": BROKEN, "test_calc.py": TEST})
    order = rec.issue_work(author="harness", inv=inv, target=rec.resolve("Q1", inv), assignee="tester",
                           objective="Run the tests.")["order"]
    rec.create(author="harness", type="artifact", inv=inv, links=[{"rel": "part_of", "to": rec.resolve("Q1", inv)}],
               fields={"sha256": "a" * 64, "path": ".", "format": "tree", "kind": "diff",
                       "meta": {"base_sha": "task", "head_sha": "b" * 12, "files": ["calc.py"]}})
    kept = [rec.get(a)["body"] for a in implied_uses(rec, inv, order, "pytest _base/test_calc.py")]
    assert [b["path"] for b in kept] == ["test_calc.py"] and kept[0]["meta"]["baseline"]
    head = [rec.get(a)["body"].get("kind") for a in implied_uses(rec, inv, order, "pytest test_calc.py")]
    assert "diff" in head


def test_a_claim_takes_a_results_field_without_a_refusal(tmp_path):
    work, rec, inv = _record(tmp_path)
    tools = _tools(rec, inv, run_code=_python(work))
    tools["register_run"](name="tests", result_summary="pytest on the changed calc.py", code=RUN_TESTS)
    out = tools["graph_add"]("claim", {"statement": "All tests in test_calc.py pass on the changed calc.py.",
                                       "scope": "pytest on the changed calc.py", "values": {"n": 3}, "outcome": "positive"},
                             [{"rel": "answers", "to": "Q2"}])
    assert out.startswith("added CL1"), out


def test_a_loading_server_is_waited_for(monkeypatch):
    import httpx

    from hypswarm.providers import openai_compat as oc
    monkeypatch.setattr(oc, "LOADING_POLL_S", 0.0)
    answers = [httpx.Response(503, text='{"error":{"message":"Loading model"}}')] * 8 + [
        httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "ok"}}]})]

    class Client:
        async def post(self, *a, **k):
            r = answers.pop(0)
            r.request = httpx.Request("POST", "http://x")
            return r

    model = oc.OpenAICompatible("m", base_url="http://x", api_key="k", client=Client(), max_retries=1)
    assert asyncio.run(model.complete([], [])).content == "ok" and not answers


def _survey(work):
    (work / "survey-2019-report.md").write_text("| 1891 | 4,028 |\n", encoding="utf-8")
    (work / "RETRACTIONS.md").write_text("The survey 2019 report is retracted.\n", encoding="utf-8")


def test_a_withdrawn_source_is_found_under_doi_and_citation(tmp_path):
    work, rec, inv = _record(tmp_path)
    _survey(work)
    add = _tools(rec, inv, folder=work)["graph_add"]
    for field, value in (("doi", "file:survey-2019-report.md"), ("citation", "survey-2019-report.md"),
                         ("url|doi", "file:survey-2019-report.md")):
        body = {"citation": "A population survey of the town, 2019", "passage": "| 1891 | 4,028 |", "kind": "secondary", field: value}
        assert "RETRACTIONS.md" in add("source", body, [{"rel": "part_of", "to": "Q1"}]), field


def test_a_source_can_be_named_url_or_doi_in_one_field(tmp_path):
    work, rec, inv = _record(tmp_path)
    add = _tools(rec, inv, folder=work)["graph_add"]
    out = add("source", {"citation": "A paper on the same question", "passage": "It says so.", "kind": "primary", "url|doi": "10.1000/xyz"},
              [{"rel": "part_of", "to": "Q1"}])
    assert out.startswith("added"), out
    assert rec.get(rec.resolve("S1", inv))["body"]["doi"] == "10.1000/xyz"


def test_a_diff_is_read_as_an_artifact(tmp_path):
    work, rec, inv = _record(tmp_path)
    assert "unknown type" not in _tools(rec, inv, run_code=_python(work))["graph_add"]("diff", {"path": "."})


def test_a_claim_about_the_original_cant_rest_on_the_current_files(tmp_path):
    work, rec, inv = _record(tmp_path)
    seed_baseline(rec, inv, work, {"calc.py": BROKEN, "test_calc.py": TEST})
    tools = _tools(rec, inv, run_code=_python(work))
    tools["register_run"](name="tests", result_summary="pytest on the changed calc.py", code=RUN_TESTS, answers="Q2")
    out = tools["graph_add"]("claim", {"statement": "The tests on the original calc.py pass.", "scope": "pytest on calc.py"},
                             [{"rel": "answers", "to": "Q1"}, {"rel": "derived_from", "to": "RS1"}])
    assert out.startswith("refused: RS1 came from the current files") and "_base/test_calc.py" in out, out


def test_the_refusal_names_the_kept_test_file(tmp_path):
    work, rec, inv = _record(tmp_path)
    seed_baseline(rec, inv, work, {"calc.py": BROKEN, "test_calc.py": TEST})
    out = _tools(rec, inv, question="Q1", run_code=_python(work))["register_run"](
        name="tests", result_summary="pytest on the original calc.py", code=RUN_TESTS, answers="Q1")
    assert "python -m pytest -q _base/test_calc.py" in out, out


def _claim_on_a_draw(work, rec, inv):
    code = "print('hits:', 100)"
    reg = _tools(rec, inv, run_code=_python(work))["register_run"]
    out = reg(name="draw", result_summary="Hits in one draw of the sampler.", values={"hits": {"value": 100, "unit": "count"}},
              code=code, answers="Q2", claim="One draw of the sampler gave 100 hits.")
    assert "→ claim CL1" in out, out
    res = rec.get(rec.resolve("RS1", inv))
    run = next(e["src"] for e in res["in"] if e["rel"] == "produced")
    rec.create(author="instrument", type="run", inv=inv, fields={
        "kind": "lab", "name": "re-execution", "state": "succeeded", "note": "re-ran it",
        "config": {"reproduces": run, "sampled": {"hits": [96, 112]}}}, links=[{"rel": "replicates", "to": run, "data": {"differs": "same_code"}}])


def _review_tool(rec, inv, node):
    order = rec.issue_work(author="harness", inv=inv, target=rec.resolve(node, inv), assignee="reviewer",
                           objective=f"Check {node}.")["order"]
    return {t.name: t.fn for t in worker_tools(rec, Seat("reviewer", "reviewer"), inv, order,
                                               Meter(Budget(max_calls=50)))}["review"]


def test_a_different_draw_is_not_an_objection_the_first_time(tmp_path):
    work, rec, inv = _record(tmp_path)
    _claim_on_a_draw(work, rec, inv)
    review = _review_tool(rec, inv, "CL1")
    first = review("CL1", "objection", "I ran the sampler once myself.", "I got 106, not 100.")
    assert first.startswith("not recorded yet") and "hits: 96 to 112" in first, first
    assert not [e for e in rec.get(rec.resolve("CL1", inv))["in"] if e["rel"] == "reviews"]
    second = review("CL1", "objection", "I ran the sampler once myself.", "It also counts the wrong thing.")
    assert not second.startswith("not recorded"), second


def test_a_steady_claim_can_be_objected_to_at_once(tmp_path):
    work, rec, inv = _record(tmp_path)
    tools = _tools(rec, inv, run_code=_python(work))
    tools["register_run"](name="tests", result_summary="pytest on the changed calc.py", code=RUN_TESTS, answers="Q2",
                          claim="All tests in test_calc.py pass on the changed calc.py.")
    review = _review_tool(rec, inv, "CL1")
    assert not review("CL1", "objection", "I read the claim against its run.", "It is wrong.").startswith("not recorded")


def test_a_rework_names_what_this_work_already_measured(tmp_path):
    work, rec, inv = _record(tmp_path)
    order = rec.issue_work(author="harness", inv=inv, target=rec.resolve("Q2", inv), assignee="tester",
                           objective="Run the tests.")["order"]
    tools = {t.name: t.fn for t in worker_tools(rec, Seat("tester", "worker"), inv, order, Meter(Budget(max_calls=50)),
                                                run_code=_python(work))}
    tools["register_run"](name="hits", result_summary="Hits counted over the whole file.",
                          values={"hits": {"value": 77, "unit": "count"}}, code="print('hits:', 77)")
    host = SimpleNamespace(r=rec, inv=inv)
    said = Scheduler._already_measured(host, "tester", order)
    assert "RS1 (hits=77)" in said and "don't compute it again" in said and '"from": "RS1"' in said, said
    assert Scheduler._already_measured(host, "reviewer", order) == ""
