"""
The record tools a seat gets. Every reply ends with what the record did for the writer (numbers it bound, results
it found restated), whether the seat's order is done, and the calls left in the run — the control state, said
where the work happens, so no agent needs a tool call to learn where it stands.
"""

from __future__ import annotations

import inspect
import json
import logging
import re
from collections.abc import Callable
from typing import Any

from hypgraph import GraphError

from .assemble import answers_block, null_over_a_checked_claim
from .budget import Meter
from .messages import Tool
from .record import Record
from .reproduce import TESTS_KEY, printed_by, runner_summary
from .seats import Seat
from .world import BASELINE_DIR, about_the_original, withdrawn_by

log = logging.getLogger("hypswarm.tools")


def _tail(n: dict[str, Any], meter: Meter) -> str:
    s = "".join(f"\n  note: {x}" for x in n.get("notes") or [])
    if n.get("restates"):
        s += f"\n  note: this restates {', '.join(n['restates'])}"
    if n.get("orders"):
        s += "\n  your order: " + "; ".join(n["orders"])
    return s + f"\n  (calls left in this run: {meter.calls_left()})"


def _err(e: Exception) -> str:
    return f"refused: {e.args[0] if isinstance(e, KeyError) and e.args else e}"


OnWrite = Callable[[str, dict[str, Any]], None]


def _live(n: dict[str, Any]) -> bool:
    st = n.get("state") or {}
    return (st.get("lifecycle") or "active") == "active" and not st.get("fallen")


_RUNS_TESTS = re.compile(r"\b(?:pytest|py\.test|unittest)\b")
_IN_BASE = re.compile(r"""(?:cwd\s*=\s*['"]_base|\bcd\s+_base|chdir\(\s*['"]_base)""")
_RULES_ON_ALL = re.compile(r"\b(?:all|every|each|none|no|zero|never|always|any)\b", re.IGNORECASE)
_TIME_UNIT = re.compile(r"^(?:s|secs?|seconds?|ms|msecs?|milliseconds?|us|µs|μs|microseconds?|ns|nanoseconds?)$",
                        re.IGNORECASE)
# The code measures time: only then is a value in seconds a timing. A duration that is the data (parse_duration("2.6s")
# returns 3 seconds) re-runs to the same digits; it was refused as a timing (studies E4, evening run).
_MEASURES_TIME = re.compile(r"\b(?:perf_counter(?:_ns)?|monotonic(?:_ns)?|process_time(?:_ns)?|thread_time(?:_ns)?|"
                            r"time_ns|timeit|default_timer|time\.time|datetime\.now|utcnow)\b")
_TIME_KEY = re.compile(r"(?:_|^)(?:s|sec|secs|seconds|ms|us|ns)$|(?:^|_)(?:time|timing|elapsed|duration|latency)(?:_|$)",
                       re.IGNORECASE)


_METHOD_MAX = 1500                     # a review's method, as the record's schema caps it


def _timings_without_spread(values: dict[str, Any]) -> list[str]:
    """Values that are timings (a time unit, or a key such as median_slow_s / elapsed_ms) and carry no spread."""
    out = []
    for k, v in values.items():
        if isinstance(v, dict):
            if "spread" in v or "rel_tol" in v or "k" in v or not isinstance(v.get("value"), (int, float)):
                continue
            unit = str(v.get("unit") or "").strip()
            if _TIME_UNIT.match(unit) or (not unit and _TIME_KEY.search(k)):
                out.append(k)
        elif isinstance(v, (int, float)) and not isinstance(v, bool) and _TIME_KEY.search(k):
            out.append(k)
    return out


def implied_uses(record: Record, inv: str, order: str, code: str) -> list[str]:
    """The artifacts a registered run used, as far as the record can tell without the author saying so: every live
    file artifact whose path the code names, and — under a workflow — the live diff or instance that is part of the
    order's question (the tests you ran while holding the order ran on the current head). Freshness then works
    without the model remembering to declare ``uses``. A run on the kept originals (_base/) used those and not the
    head: filed under the head, every fix made its results stale, and E1 spent 3 orders of its budget re-establishing
    what the original does, which no fix can change (BC-250, 2026-11-05). Such a run says ``import raffle`` as often as
    it says raffle.py, and a run that names no file goes stale on any later edit, so there the module name counts."""
    out: list[str] = []
    kept = BASELINE_DIR in code
    if code.strip():
        for a in record.search("", "artifact", inv, 500):
            n = record.get(a["id"])
            b = n.get("body") or {}
            path = str(b.get("path") or "")
            if not path or path == "." or "://" in path or b.get("kind") == "excerpt" or not _live(n):
                continue
            if kept and not (b.get("meta") or {}).get("baseline"):
                continue
            names = {path, path.rsplit("/", 1)[-1]}
            module = kept and re.search(r"\b" + re.escape(path.rsplit("/", 1)[-1].rsplit(".", 1)[0]) + r"\b", code)
            if module or any(re.search(r"(?<![\w.-])" + re.escape(x) + r"(?![\w.-])", code) for x in names):
                out.append(a["id"])
    try:
        target = next((e["dst"] for e in record.get(order).get("out", []) if e.get("rel") == "works_on"), "")
        if target and record.get(target)["type"] == "question":
            for e in record.get(target).get("in", []):
                if e.get("rel") != "part_of":
                    continue
                n = record.get(e["src"])
                if n["type"] == "artifact" and (n.get("body") or {}).get("kind") in ("diff", "instance") and _live(n) \
                        and not kept:
                    out.append(n["id"])
    except (GraphError, KeyError):
        pass
    return list(dict.fromkeys(out))


_CODE = re.compile(r"\b(?:Q|T|CL|RS|RUN|RV|H|X|D)\d+\b")


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]{3,}", text.lower()))


_FIGURE = re.compile(r"(?<![\w.])-?\d[\d,]*(?:\.\d+)?%?")


def _figures(text: str) -> set[float]:
    """The numbers a sentence states, percentages as fractions (81.4 % and 0.814 are one figure)."""
    out: set[float] = set()
    for m in _FIGURE.findall(text):
        pct = m.endswith("%")
        try:
            v = float(m.rstrip("%").replace(",", ""))
        except ValueError:
            continue
        out.add(round(v / 100 if pct else v, 9))
    return out


def _copied(record: Record, inv: str, me: str, question: str, statement: str, kind: str = "") -> list[dict[str, Any]]:
    """The seat's own live answers to the question that a claim would copy. A copy states no figure the earlier claim
    doesn't (or, with no figures, nearly the same words) and has the same kind."""
    try:
        q = record.get(record.resolve(question, inv))
    except (GraphError, KeyError):
        return []
    out: list[dict[str, Any]] = []
    nums, words = _figures(statement), _words(statement)
    for e in q.get("in", []):
        if e.get("rel") != "answers":
            continue
        try:
            c = record.get(e["src"])
        except (GraphError, KeyError):
            continue
        if c.get("type") != "claim" or c.get("by") != me or not _live(c):
            continue
        body = c.get("body") or {}
        if (body.get("kind") or "finding") != (kind or "finding"):
            continue
        other = str(body.get("statement") or "")
        theirs, their_words = _figures(other), _words(other)
        if nums:
            same = nums <= theirs
        else:
            same = not theirs and bool(words) and bool(their_words) and \
                len(words & their_words) / len(words | their_words) >= 0.8
        if same:
            out.append(c)
    return out


def _same_answer(record: Record, inv: str, me: str, question: str, statement: str, kind: str = "") -> str:
    """Why a claim is a copy of the seat's own standing answer to the same question ('' = it isn't). The record holds a
    question at "answered" until every answer to it is checked, so a copy is one more claim to review before it
    settles: on a 3-slot gpt-oss swarm the analyst filed the same Q1 answer five times and the run's budget ran out
    with two unchecked copies beside a checked one (BC-250, 2026-11-04). A stale answer isn't one to copy: the order to
    redo it says to write the claim again, and refusing that left right answers unchecked (_stale_copies)."""
    for c in _copied(record, inv, me, question, statement, kind):
        if not (c.get("state") or {}).get("stale"):
            code = record.get(record.resolve(question, inv))["code"]
            return (f"refused: your {c['code']} already answers {code} with this ({c['state']['sentence'][:90]}). "
                    f"A copy is one more answer to check before {code} settles. If {c['code']} is wrong, revise "
                    "it; if it is right there is nothing new to file — return your order")
    return ""


def _stale_copies(record: Record, inv: str, me: str, question: str, statement: str,
                  kind: str = "") -> list[dict[str, Any]]:
    """The seat's stale answers a claim says again. The new claim replaces them: left beside it, a stale answer that
    was never checked holds the question open, and a seat told to link the two often doesn't."""
    return [c for c in _copied(record, inv, me, question, statement, kind) if (c.get("state") or {}).get("stale")]


def _replacing(links: list[dict[str, Any]], old: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The links with ``supersedes`` to each of the old claims, unless the seat named it."""
    named = {str(l.get("to")) for l in links if l.get("rel") == "supersedes"}
    return [*links, *({"rel": "supersedes", "to": c["id"]} for c in old if not named & {c["code"], c["id"]})]


def _not_a_question(text: str, existing: list[tuple[str, str]]) -> str:
    """Why a lead's question isn't one ('' = it is). Leads added orders as questions — "Q2 claim: the analyst's T10
    must write, on the existing run result RS5 …?" — and copies of open questions, and each owed the whole workflow
    (studies S2, S3, E6 day 2: every one of the three runs grew a Q4)."""
    codes = _CODE.findall(text)
    if codes:
        return (f"refused: a question asks what the run must find out about the world; this one names record entries "
                f"({', '.join(dict.fromkeys(codes))}). To send that work to a seat, rework its order (rework) with "
                "done_when")
    mine = _words(text)
    for code, other in existing:
        theirs = _words(other)
        # a copy, or a copy with a clause added ("… or decline — given the honest out-of-sample result …": the
        # added words diluted the overlap below 0.8, and the run owed Q3 twice; studies T2, evening)
        if mine and theirs and (len(mine & theirs) / len(mine | theirs) >= 0.8 or len(mine & theirs) / len(theirs) >= 0.9):
            return (f"refused: {code} already asks this. To get it answered, rework the order on {code} (rework) — "
                    "a second copy owes the whole workflow again")
    return ""


# 14 of the 47 refused calls in six runs, and the lead's most repeated one: show on a file name (BC-250, 2026-11-05)
NOT_A_NODE = ". show reads the record's entries by code (Q1, CL2, RS3, T4), not files; only a worker's tools read files"


def _count_of_tests(run_code: Any, code: str, values: dict[str, Any] | None) -> dict[str, int] | None:
    """{k, n} for a registered test run, by the test runner's own summary, or None. Seats registered "All 6 tests
    passed" with no values, so "all tests pass" had no count behind it, and 12 such claims were refused in 3 runs of E1
    while its second question stayed open (BC-250, 2026-11-05). Only ``run_code`` says: a seat's number isn't needed."""
    if not run_code or not _RUNS_TESTS.search(code) or TESTS_KEY in (values or {}):
        return None
    try:
        out = run_code(code)
    except Exception:  # noqa: BLE001 — the instrument re-runs it and reports the failure
        return None
    if inspect.isawaitable(out):
        out.close() if inspect.iscoroutine(out) else None
        return None
    ran = runner_summary(str(out))
    return {"k": ran["passed"], "n": ran["passed"] + ran["failed"]} if ran else None


def _on_its_count(record: Record, fields: dict[str, Any], result: str) -> dict[str, Any]:
    """A claim that rules on all of a test run, bound to the run's count, and saying it: "all" over the tests a run ran
    is that count, not a rate past them, and the record only takes it so when the sentence states n. From there the
    record checks it: "all tests pass" on 2 of 3 is refused as false."""
    statement = str(fields.get("statement") or "")
    v = ((record.get(result).get("body") or {}).get("values") or {}).get(TESTS_KEY)
    if fields.get("measurements") or not isinstance(v, dict) or not _RULES_ON_ALL.search(statement):
        return fields
    k, n = v.get("k"), v.get("n")
    # named in both forms: the record asks that a count's name meets the sentence, and "pass" and "passed" don't stem alike
    said = statement if k not in (0, n) or re.search(rf"\b{n}\b", statement) else f"{statement.rstrip('. ')} ({k} of {n} tests)."
    return {**fields, "statement": said,
            "measurements": [{"name": "tests pass, tests passed", "result": result, "key": TESTS_KEY, "k": k, "n": n}]}


def worker_tools(record: Record, seat: Seat, inv: str, order: str, meter: Meter,
                 on_write: OnWrite | None = None, runs_code: bool = True, run_code: Any = None,
                 folder: Any = None) -> list[Tool]:
    """What a worker or reviewer can do to the record while holding an order. ``on_write(kind, payload)`` is told
    after every accepted ``graph_add`` / ``register_run`` (a host's hook; it never changes the reply).
    ``run_code``: the host's ``(code) -> output``, for the count of a registered test run. ``folder``: the working
    folder, where a cited file's withdrawal may be written down.
    ``runs_code=False``: nothing the seat holds executes code, so ``register_run`` refuses code — it can't have run.
    Through the CLI with only the files toolkit, seats registered code with its "output" 14 times in one run; with no
    instrument nothing checked it, and code text counts as the code behind a result (studies O1, evening)."""
    me = seat.name
    state: dict[str, Any] = {"returned": False, "reviewed": False, "ran": []}

    def _told(kind: str, payload: dict[str, Any]) -> None:
        if on_write:
            try:
                on_write(kind, payload)
            except Exception as e:  # noqa: BLE001 — a host hook never costs a worker its write
                log.warning("on_write hook failed on %s: %s", kind, e)

    def _question() -> str:
        """The question this order works on, "" when it works on something else."""
        try:
            target = next((e["dst"] for e in record.get(order).get("out", []) if e.get("rel") == "works_on"), "")
            return target if target and record.get(target)["type"] == "question" else ""
        except (GraphError, KeyError):
            return ""

    def _results_with_a_count(links: list[dict[str, Any]]) -> list[str]:
        """Results a claim may lean on for a test count: the ones it links, then this seat's own, newest first. E1's
        tester ran the tests, wrote "all tests pass", and gave no link, so the count sat one node away."""
        mine = [r["id"] for r in record.search("", "result", inv, 500)
                if record.get(r["id"]).get("by") == me and _live(record.get(r["id"]))
                and TESTS_KEY in ((record.get(r["id"]).get("body") or {}).get("values") or {})]
        return _linked_results(links) + mine[::-1]

    def _linked_results(links: list[dict[str, Any]]) -> list[str]:
        out: list[str] = []
        for l in links:
            try:
                ref = str(l.get("to") or l.get("from") or "")
                if l.get("rel") in ("derived_from", "supports") and record.get(_node(ref))["type"] == "result":
                    out.append(_node(ref))
            except (GraphError, KeyError):
                continue
        return out

    def _rests_on_the_head(links: list[dict[str, Any]]) -> str:
        """The refusal for a claim about the original whose linked result ran on the current files. register_run only
        sees the question it's told about: E1's tester ran the tests under Q2's order and then answered Q1 with them,
        "all 6 pass on the original", where 3 fail (BC-250, 2026-11-05)."""
        asked = next((str(l.get("to") or "") for l in links if l.get("rel") == "answers"), "")
        if not asked:
            return ""
        for rid in _linked_results(links):
            res = record.get(rid)
            for e in res["in"]:
                if e["rel"] == "produced":
                    source = str(((record.get(e["src"]).get("body") or {}).get("config") or {}).get("source") or "")
                    said = _not_the_original(source, asked)
                    if said:
                        return said.replace("refused: ", f"refused: {res['code']} came from the current files. ", 1)
        return ""

    def _draws(target: str) -> str:
        """What the instrument found to vary in the work a claim or result rests on: "name: lo to hi", or ''."""
        n = record.get(target)
        results = [target] if n["type"] == "result" else [
            e["src"] for e in n["in"] if e["rel"] == "supports"] + [
            e["dst"] for e in n["out"] if e["rel"] == "derived_from"]
        out: list[str] = []
        for rid in results:
            for e in record.get(rid)["in"]:
                if e["rel"] != "produced":
                    continue
                for x in record.get(e["src"])["in"]:
                    if x["rel"] == "replicates":
                        config = (record.get(x["src"]).get("body") or {}).get("config") or {}
                        out += [f"{k}: {lo:g} to {hi:g}" for k, (lo, hi) in (config.get("sampled") or {}).items()]
        return "; ".join(dict.fromkeys(out))

    def _not_the_original(code: str, answers: str) -> str:
        """The refusal for a run on the current files that answers a question about the original. A file a fix changes
        gives a different count, or a re-run contradicts the first one, so it has to run the copy under _base/. Only
        when the code names a kept file: a question can say "original" about something else."""
        running = bool(_RUNS_TESTS.search(code))
        if not code.strip() or (BASELINE_DIR in code and not running) or _IN_BASE.search(code):
            return ""
        try:
            q = record.get(_node(answers)) if answers.strip() else record.get(_question() or inv)
        except (GraphError, KeyError):
            return ""
        if q.get("type") != "question" or not about_the_original(str((q.get("body") or {}).get("text") or "")):
            return ""
        for a in record.search("", "artifact", inv, 500):
            body = record.get(a["id"]).get("body") or {}
            base = str((body.get("meta") or {}).get("baseline") or "")
            stem = str(body.get("path") or "").rsplit("/", 1)[-1].rsplit(".", 1)[0]
            # a test runner in a subprocess never sees sys.path: E1 "ran the original" with sys.path.insert and then
            # pytest test_semver.py, which is the current file. There the file itself has to be the kept one
            named = rf"(?<!{BASELINE_DIR}/)\b{re.escape(stem)}\b" if running else rf"\b{re.escape(stem)}\b"
            if base and stem and re.search(named, code):
                how = (f"name that file: python -m pytest -q {base}" if running else
                       f"put it first on the path: sys.path.insert(0, '{BASELINE_DIR}')")
                return (f"refused: {q.get('code')} asks about the original, and this code runs the current "
                        f"{body.get('path')}, which a fix changes. The original is {base}: {how}, then register that")
        return ""

    def _open_experiment() -> str:
        """The experiment a run under this order executes when the seat didn't name it: the one it wrote on the
        order's question that no run has executed. "" unless there is exactly one. A run registered with no experiment
        left the question at "no run executes Q2", and the next order filed another hypothesis, experiment and claim
        (BC-250, 2026-11-05)."""
        q = _question()
        if not q:
            return ""
        on_q = [e["src"] for e in record.get(q).get("in", []) if e.get("rel") in ("answers", "part_of", "motivated_by")]
        found = []
        for nid in on_q:
            n = record.get(nid)
            found += [nid] if n["type"] == "experiment" else \
                [e["src"] for e in n.get("in", []) if e.get("rel") == "tests"] if n["type"] == "hypothesis" else []
        fresh = []
        for x in dict.fromkeys(found):
            n = record.get(x)
            if n.get("by") == me and _live(n) and not any(e.get("rel") == "executes" for e in n.get("in", [])):
                fresh.append(x)
        return fresh[0] if len(fresh) == 1 else ""

    def _named(ref: str) -> str:
        """The node a seat meant by what it knows it as: a file's path, an experiment's aim, a run's name. The node's
        id, or "" when that names none, or more than one."""
        want = ref.strip().casefold()
        hits = []
        for type_, field in (("artifact", "path"), ("experiment", "aim"), ("run", "name")):
            for a in record.search("", type_, inv, 500):
                n = record.get(a["id"])
                said = str((n.get("body") or {}).get(field) or "").casefold()
                if want and _live(n) and want in {said, said.rsplit("/", 1)[-1]}:
                    hits.append(a["id"])
        return hits[0] if len(hits) == 1 else ""

    def _node(ref: str) -> str:
        """``record.resolve``, for what a seat calls a node. A name that fits nothing is refused with the codes that
        exist, so the next call can use one."""
        try:
            return record.resolve(ref, inv)
        except KeyError:
            found = _named(ref)
            if found:
                return found
            there = [str(a.get("code")) for t in ("question", "hypothesis", "experiment", "result", "artifact")
                     for a in record.search("", t, inv, 12) if a.get("code")]
            raise KeyError(f"no node {ref!r}. Name a node by its code ({', '.join(there[:24]) or 'none yet'})") from None

    def _result_of(nid: str) -> str:
        """What a seat means by "this run supports the claim": the run's own result, when it has exactly one."""
        n = record.get(nid)
        made = [e["dst"] for e in n.get("out", []) if e.get("rel") == "produced"]
        return made[0] if n.get("type") == "run" and len(made) == 1 else nid

    def _links(links: list[dict[str, Any]] | None, type_: str = "") -> list[dict[str, Any]]:
        out = []
        for l in links or []:
            d = dict(l)
            if "dst" in d:                                # hypgraph's own name for it; a link says to / from
                d.setdefault("to", d.pop("dst"))
            if type_ == "claim" and d.get("rel") == "uses":
                d["rel"] = "derived_from"                 # a claim doesn't use what it rests on; it derives from it
            for k in ("to", "from"):
                if d.get(k):
                    d[k] = _node(str(d[k]))
            if d.get("rel") == "supports" and d.get("from"):
                d["from"] = _result_of(d["from"])
            out.append(d)
        return out

    def _measurable(m: Any) -> bool:
        """A measurement the record can read: a result of this record and a value of that result."""
        if not isinstance(m, dict):
            return False
        try:
            res = record.get(record.resolve(str(m.get("result") or ""), inv))
        except (GraphError, KeyError):
            return False
        return res.get("type") == "result" and str(m.get("key")) in ((res.get("body") or {}).get("values") or {})

    def _as_claim(fields: dict[str, Any] | None, links: list[dict[str, Any]] | None
                  ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """A claim's fields where graph_add takes them. Seats wrote register_run's names here (``claim_kind``,
        ``answers``) and the number itself as a measurement's result (BC-250, 2026-11-05). The record binds a
        statement's numbers to results itself and refuses a number it can't, so a measurement it couldn't read adds
        nothing, and every check still runs on what's left."""
        f, ln = dict(fields or {}), list(links or [])
        kind = f.pop("claim_kind", None)
        if kind and not f.get("kind"):
            f["kind"] = kind
        if f.get("kind") == "claim":
            del f["kind"]
        for stray in ("values", "value", "outcome", "summary"):      # a result's: three refusals in one E1 run
            f.pop(stray, None)
        asked = f.pop("answers", None)
        for q in [asked] if isinstance(asked, str) else asked or []:
            if q and not any(l.get("rel") == "answers" and l.get("to") == q for l in ln):
                ln.append({"rel": "answers", "to": q})
        if "measurements" in f:
            f["measurements"] = [m for m in f["measurements"] or [] if _measurable(m)]
            if not f["measurements"]:
                del f["measurements"]
        if len(str(f.get("scope") or "").strip()) < 10:   # as register_run does: the result says what it was run on
            for l in ln:
                try:
                    res = record.get(_node(str(l.get("to") or "")))
                except (GraphError, KeyError):
                    continue
                said = str((res.get("body") or {}).get("summary") or "")
                if l.get("rel") in ("derived_from", "uses") and res.get("type") == "result" and said:
                    f["scope"] = said
                    break
        return f, ln

    def graph_add(type: str, fields: dict[str, Any], links: list[dict[str, Any]] | None = None) -> str:
        """Add to the record. claim {statement, scope, kind} — statement: what was measured, on what, what it came to
        ("The median latency of the 240 requests in access.log is 31 ms."); scope: the data, method and sample, in a
        sentence; kind: finding (default) | exclusion | inconclusive. The record binds a claim's numbers to your
        results, so give it links, not measurements. hypothesis {statement, predictions[]}, links [{"rel": "answers",
        "to": "Q1"}] · experiment {aim, protocol, success_criteria}, each a full sentence, links [{"rel": "tests",
        "to": "H1", "data": {"expected": "what it should show if H1 is true"}}]. A claim's links: [{"rel": "answers",
        "to": "Q1"}, {"rel": "derived_from", "to": "RS1"}, {"rel": "supports", "to": "H1", "why": …}]. Name nodes by
        the code a reply gave you (Q1, H1, X1, RS1). A number you computed goes through register_run;
        a result here is one you didn't compute: {summary, outcome, values: {name: {value, unit} | {k, n}}, kind:
        observed | cited}. The task's files are already in the record. A refused claim says exactly what to fix.
        A reviewer writes reviews, not claims: a claim by the only reviewer could never be reviewed."""
        fields = dict(fields or {})
        if type == "diff":                                # 14 refused calls in 24 runs, for the name of a type
            type, fields = "artifact", {**fields, "kind": "diff"}
        if isinstance(fields.get("links"), list):         # the seat wrote them inside fields
            links = list(links or []) + fields.pop("links")
        if type in ("claim", "hypothesis", "experiment", "result"):
            fields.pop("name", None)                      # none of these has one; a code names them
        if type == "artifact" and (fields or {}).get("kind") == "diff":
            arts = [record.get(a["id"]) for a in record.search("", "artifact", inv, 500)]
            heads = [a for a in arts if (a.get("body") or {}).get("format") == "tree" and _live(a)]
            if heads:
                # the watcher owns the head: a seat's own diff made a second line of heads, one of them an empty
                # file registered mid-write, and the tests never ran on "the current head" (studies/challenges E1)
                return (f"refused: the record watches the working tree — {heads[-1].get('code', 'its head')} is the "
                        "current head, and an edit to the files registers the next one. Edit the files; don't "
                        "register a diff")
        if type == "artifact" and not (fields or {}).get("sha256"):
            # no bytes to register: the seat wants the file it read, and the harness registered the task's files
            have = _named(str((fields or {}).get("path") or (fields or {}).get("name") or ""))
            if have:
                return f"{record.get(have)['code']} is that file, already in the record: use that code"
        if seat.role == "reviewer" and type == "claim":
            return ("refused: you are a reviewer — record a verdict on the claim you were asked to check (review); if "
                    "the right answer is missing, say so in your review notes and return the order, and a worker "
                    "will be asked to write it")
        if type == "source":
            either = fields.pop("url|doi", None)          # the record's help writes it so, and seats copy it: 17 refusals
            if either and not fields.get("url") and not fields.get("doi"):
                fields["doi" if str(either).startswith("10.") else "url"] = either
            # the name can be in any of these: K1's 4,028 came in with the file under doi, past a check on url
            for said in (fields.get("url"), fields.get("doi"), fields.get("citation")):
                where = withdrawn_by(folder, str(said or ""))
                if where:
                    return (f"refused: {where} A withdrawn source is not evidence, so it can't be cited for an answer. "
                            "Use what that line points to; if it points nowhere, say no source answers")
        off = ""
        if type == "claim":
            replaced: list[dict[str, Any]] = []
            fields, links = _as_claim(fields, links)
            wrong = _rests_on_the_head(links)
            if wrong:
                return wrong
            for rid in _results_with_a_count(links):
                fields = _on_its_count(record, fields, rid)
            for l in links:
                if l.get("rel") == "answers" and l.get("to"):
                    why = _same_answer(record, inv, me, str(l["to"]), str((fields or {}).get("statement") or ""),
                                       str((fields or {}).get("kind") or ""))
                    if why:
                        return why
                    replaced += _stale_copies(record, inv, me, str(l["to"]), str((fields or {}).get("statement") or ""),
                                              str((fields or {}).get("kind") or ""))
            links = _replacing(links, replaced)
            if replaced:
                off = f" (it replaces {', '.join(c['code'] for c in replaced)}, whose evidence is stale)"
        q = _question()
        try:
            if type == "hypothesis" and q and not any(l.get("rel") == "answers" for l in links or []):
                links = [*(links or []), {"rel": "answers", "to": q}]   # what the order asks about, unless it says
            if type == "experiment" and q:
                for l in links or []:
                    h = record.get(_node(str(l.get("to") or ""))) if l.get("rel") == "tests" else None
                    if h and not any(e.get("rel") == "answers" and e.get("dst") == q for e in h.get("out", [])):
                        off += (f" (note: {h['code']} doesn't answer {record.get(q)['code']}, your order's question, "
                                "so this experiment doesn't count for it)")
            n = record.create(author=me, type=type, inv=inv, fields=fields, links=_links(links, type))
        except (GraphError, KeyError) as e:
            return _err(e)
        _told("graph_add", {"type": type, "fields": fields, "code": n["code"], "id": n["id"]})
        return f"added {n['code']} — {n['state']['sentence']}{off}" + _tail(n, meter)

    def graph_link(src: str, rel: str, dst: str, why: str = "", expected: str = "") -> str:
        """Link two nodes you can see: part_of (an artifact or source → a question), uses (a run → an artifact),
        supports / challenges (why required), supersedes (a newer diff or instance → the old one), tests (an
        experiment → a hypothesis; expected required: what it should show if the hypothesis is true)."""
        try:
            data = {"expected": expected} if expected.strip() else None
            record.link(author=me, src=_node(src), rel=rel, dst=_node(dst), why=why, data=data)
        except (GraphError, KeyError) as e:
            return _err(e)
        return f"linked {src} -{rel}-> {dst}"

    def _restated(e: Exception) -> dict[str, Any] | None:
        """The seat's own result a RESULT_RESTATES refusal names (None = some other refusal)."""
        probs = [p for p in getattr(e, "problems", None) or [] if p.get("code") == "RESULT_RESTATES"]
        m = re.search(r"your own (\S+)$", str(probs[0].get("message") or "")) if probs else None
        try:
            return record.get(record.resolve(m.group(1), inv)) if m else None
        except (GraphError, KeyError):
            return None

    def _onto_codeless(old: dict[str, Any], run: dict[str, Any]) -> bool:
        """The code-bearing run becomes the code of the seat's own bare result (``run -produced-> result``). Without
        this a seat that first registered a number bare could never put code behind it — the gate asked for a
        re-runnable result, a new one was refused as a restatement, and the seat filed copies of its claim until the
        budget ran out (BC-250, 2026-11-04). The instrument then re-runs the code against the result's own values, so
        nothing is credited that a re-run doesn't show. False = it already has code: a real restatement."""
        producers = [record.get(x["src"]) for x in old.get("in", []) if x.get("rel") == "produced"]
        if any(((p.get("body") or {}).get("config") or {}).get("source") for p in producers):
            return False
        try:
            record.link(author=me, src=run["id"], rel="produced", dst=old["id"],
                        why="the code that computes this result, registered after the result itself")
        except (GraphError, KeyError):
            return False
        return True

    def register_run(name: str, result_summary: str, values: dict[str, Any] | None = None, outcome: str = "",
                     experiment: str = "", code: str = "", claim: str = "", answers: str = "", scope: str = "",
                     claim_kind: str = "", uses: list[str] | None = None) -> str:
        """Record a computation you ran and the result it produced: values {name: {value, unit} | {k, n}} — a value
        that varies run to run (a timing, an unseeded sample) also takes its spread: {value, unit, spread: [lo, hi]}
        or rel_tol (a fraction), and the instrument confirms a re-run inside it; code: the
        exact code you ran — the instrument re-executes it and checks that the output shows every value you register,
        so PRINT each registered value with its name (print("n_items", n_items)). experiment: the experiment it
        executes, if any. uses: what the run read, by code or file path — the diff it tested, the instance it solved,
        the data file (a workflow reads 'tests on the current head' and freshness off these). claim (optional): the
        whole sentence this result lets you assert, not a label — written in the same call, derived from the result,
        its numbers bound to these values; if only the claim is refused, call again with it corrected and it goes on
        the same result. answers: the question code it answers; scope: under which conditions it holds, in a
        sentence; claim_kind: finding (default) | exclusion | inconclusive. The result counts toward your order by
        itself; a claim settles a question."""
        if code.strip() and not runs_code:
            return ("refused: nothing in this run executes code, so this code wasn't run and isn't evidence. Register "
                    "only what you read off the files (values, no code), or return the order and say it needs a tool "
                    "that runs code")
        adopted = printed_by(values, state["ran"]) if values and runs_code and not code.strip() else ""
        code = adopted or code
        wrong_copy = _not_the_original(code, answers)
        if wrong_copy:
            return wrong_copy
        no_claim = ""
        if seat.role == "reviewer" and claim.strip():
            # graph_add refuses this too; here the run and result are still evidence for the review. A reviewer's
            # claim can't be reviewed, so it held its question open to the end of the run (BC-250, 2026-11-05)
            no_claim = " (a reviewer's claim couldn't be reviewed, so none was written: give your verdict with review)"
            claim = ""
        count = _count_of_tests(run_code, code, values)
        if count:
            # the count decides the outcome too: a run with no outcome read as positive, and tests_pass reads that
            values = {**{k: v for k, v in (values or {}).items() if k != "stdout"}, TESTS_KEY: count}
            outcome = "positive" if count["k"] and count["k"] == count["n"] else "negative"
        bare = _timings_without_spread(values or {}) if _MEASURES_TIME.search(code) else []
        if bare and code.strip():
            # the instrument re-runs the code: a re-timed value never lands on the same digits, and every timing
            # registered bare came back CONTRADICTED while the ones with a spread were confirmed (studies E2)
            return (f"refused: {', '.join(bare)} {'is a timing' if len(bare) == 1 else 'are timings'} — a re-run "
                    "never prints the same digits, so the instrument would contradict it. Give each its spread over "
                    "your repeats: {value, unit, spread: [lo, hi]} or rel_tol (a fraction)")
        if claim.strip() and answers.strip():
            why = _same_answer(record, inv, me, answers, claim, claim_kind)
            if why:
                return why
        r: dict[str, Any] | None = None
        attached = again = False
        skipped: list[str] = []
        declared: list[str] = []
        for a in uses or []:
            if str(a).strip():
                # what a run read is provenance: a name the record doesn't hold costs it that line, not the run
                try:
                    nid = _node(str(a))
                    if record.get(nid)["type"] != "artifact":
                        raise KeyError(a)
                    declared.append(nid)
                except (GraphError, KeyError):
                    skipped.append(str(a))
        executes = ""
        if experiment.strip():
            try:
                nid = _node(experiment)
                executes = nid if record.get(nid)["type"] == "experiment" else ""
            except (GraphError, KeyError):
                pass
        if not executes and seat.role != "reviewer":
            executes = _open_experiment()
        unnamed = experiment if experiment.strip() and not executes else ""
        try:
            links: list[dict[str, Any]] = [{"rel": "executes", "to": executes}] if executes else []
            links += [{"rel": "uses", "to": a, "data": {"role": "data"}}
                      for a in dict.fromkeys(declared + implied_uses(record, inv, order, code))]
            rfields: dict[str, Any] = {"kind": "agent", "name": name[:300], "state": "succeeded", "note": code[:1500]}
            if code.strip():
                rfields["config"] = {"source": code[:18000], "language": "python"}
            r = record.create(author=me, type="run", inv=inv, links=links, fields=rfields)
            rf: dict[str, Any] = {"summary": result_summary, "values": values or {}, "kind": "computed"}
            if outcome:
                rf["outcome"] = outcome
            res = record.create(author=me, type="result", inv=inv, fields=rf,
                                links=[{"rel": "produced", "from": r["id"]}])
        except (GraphError, KeyError) as e:
            old = _restated(e) if r is not None else None
            if old is None or r is None:
                return _err(e)
            attached = bool(code.strip()) and _onto_codeless(old, r)
            again = not attached and bool(claim.strip())
            if not attached and not again:
                return _err(e)
            res = record.get(old["id"])
        assert r is not None                              # the except above returns unless the run was created
        _told("register_run", {"code": code, "values": (res.get("body") or {}).get("values") or values or {},
                               "result": res["code"], "run": r["code"]})
        out = f"run {r['code']} → result {res['code']}"
        if attached:
            out += (f" (your earlier {res['code']} had no code behind it; {r['code']} is now its code, and the "
                    "instrument re-runs it — claims on it need no copy)")
        if adopted:
            out += " (the code is your python call that printed these values, and the instrument re-runs it)"
        if again:                                         # the call came back after a refused claim
            out += f" (these are the numbers of your {res['code']}, so the claim goes on it)"
        if skipped:
            out += f" (not in the record, left out of uses: {', '.join(skipped)})"
        if unnamed:
            out += (f" (no experiment {unnamed!r} in the record, so this run executes none; if it should, "
                    f"graph_link({r['code']}, 'executes', <its X code>))")
        out += no_claim
        if claim.strip():
            cf: dict[str, Any] = _on_its_count(record, {"statement": claim, "scope": scope or result_summary}, res["id"])
            if claim_kind:
                cf["kind"] = claim_kind
            cl_links: list[dict[str, Any]] = [{"rel": "derived_from", "to": res["id"]},
                                              {"rel": "supports", "from": res["id"],
                                               "why": "the result this claim's numbers come from"}]
            if answers.strip():
                try:
                    cl_links.append({"rel": "answers", "to": _node(answers)})
                except (GraphError, KeyError) as e:
                    return out + f"\n  claim not written: {e}" + _tail(res, meter)
                cl_links = _replacing(cl_links, _stale_copies(record, inv, me, answers, claim, claim_kind))
            try:
                c = record.create(author=me, type="claim", inv=inv, fields=cf, links=cl_links)
            except (GraphError, KeyError) as e:
                why = str(e)
                if why.startswith("claim refused:"):      # the record's own prefix; don't say it twice
                    why = why[len("claim refused:"):].strip()
                if not re.search(r"\s", claim.strip()):
                    why = f"claim is the sentence itself, not a label ({claim.strip()[:20]!r}). {why}"
                return out + f"\n  claim refused: {why}" + _tail(res, meter)
            out += f" → claim {c['code']} — {c['state']['sentence']}"
            return out + _tail(c, meter)
        return out + _tail(res, meter)

    told_of_draws: set[str] = set()

    def review(node: str, verdict: str, method: str, notes: str) -> str:
        """Review a claim or result: checked | pass | fail | objection | resolved | inconclusive | comment. method:
        how you checked, in a full sentence; notes: what you found. Never your own author's work."""
        if len(method) > _METHOD_MAX:
            # a thorough method over the record's limit lost the whole review (studies E3): the rest goes in notes
            cut = method.rfind(" ", 0, _METHOD_MAX - 40)
            cut = cut if cut > 0 else _METHOD_MAX - 40
            method, notes = (method[:cut] + " … (continued in notes)",
                             f"Method, continued: {method[cut:].strip()}\n\n{notes}"[:4000])
        try:
            target = record.resolve(node, inv)
            if verdict.strip().lower() in ("objection", "fail") and target not in told_of_draws:
                # E3: 81 of 1,000 objected to because a reviewer's own run gave 106, on code that gives about 98 ± 9
                spread = _draws(target)
                if spread:
                    told_of_draws.add(target)
                    return (f"not recorded yet: the instrument re-ran this and it varies from run to run ({spread}), so "
                            "a different number from your own run is another draw, not an error. If that is your only "
                            "objection, review it checked and put the spread in your notes. If something else is wrong, "
                            "send the objection again and say what.")
            out = record.review(author=me, target=target, verdict=verdict.strip().lower(), method=method, notes=notes)
        except (GraphError, KeyError) as e:
            return _err(e)
        state["reviewed"] = True
        return f"{out['code']}: {out['state']['sentence']}" + _tail(out, meter)

    def show(node: str) -> str:
        """A node's fields, standing and links."""
        try:
            n = record.get(record.resolve(node, inv))
        except (GraphError, KeyError) as e:
            return _err(e) + NOT_A_NODE
        return json.dumps({"code": n["code"], "type": n["type"], "standing": n["state"]["sentence"], "body": n["body"],
                           "links": [f"{e['rel']} {record.get(e['dst'])['code']}" for e in n["out"]]},
                          default=str)[:6000]

    def find(text: str = "", type: str = "") -> str:
        """Nodes in this investigation matching words and/or a type."""
        rows = record.search(text, type, inv, 30)
        return str("\n".join(f"{r['code']} {r['type']} — {r['title'][:100]} — {r['state']['sentence'][:80]}"
                             for r in rows) or "nothing matches")

    def return_work(note: str = "") -> str:
        """Hand your order back with a note of at most 120 words: what you did, what you could not."""
        try:
            c = record.return_work(author=me, order=order, note=note)
        except (GraphError, KeyError) as e:
            return _err(e)
        state["returned"] = True
        return "returned — " + ("every predicate met" if c["all_met"] else "NOT every predicate met: "
                                                                        + "; ".join(x["why"] for x in c["predicates"] if not x["met"]))

    tools = [Tool.from_function(f) for f in (graph_add, graph_link, register_run, review, show, find, return_work)]
    for t in tools:
        t.fn.__dict__["_state"] = state     # the worker loop reads whether return_work / review ran
    return tools


def lead_tools(record: Record, seat: Seat, inv: str, meter: Meter, *, report_box: dict[str, Any],
               roster: list[dict[str, str]], order_author: str = "", needs_answers: bool = False) -> list[Tool]:
    """What the lead can do at an exception and for the report: plan, re-plan, judge; never the workers' work.
    ``order_author``: the author that issued the orders (the scheduler), so the lead's rework and cancel act on
    them — only an order's author may withdraw it. ``needs_answers``: the task asks for an answers block, so a report
    without one is refused."""
    me = seat.name
    oa = order_author or me
    seq = {"n": 0}

    def briefing() -> str:
        """Your context, compiled from the record: the question board, exceptions, orders in flight and returned."""
        b = record.briefing(inv, roster=roster, since_seq=seq["n"])
        seq["n"] = b["seq"]
        return str(b["text"]) + f"\n(calls left in this run: {meter.calls_left()})"

    def add(type: str, fields: dict[str, Any], links: list[dict[str, Any]] | None = None) -> str:
        """Plan: a hypothesis {statement, predictions[]} or an experiment {aim, protocol, success_criteria} with
        tests links [{"rel": "tests", "to": "H1", "data": {"expected": …}}]; or a question {text, asks?: "measure"}
        (asks=measure when it wants a number or a check of what exists: no change, hypothesis or backtest)."""
        if type not in ("hypothesis", "experiment", "question"):
            return "the lead plans (hypothesis, experiment, question); results and claims come from workers"
        if type == "question" and "?" not in str((fields or {}).get("text") or ""):
            # a lead once added "Assign it to risk as a REVIEW of CL2 …" as a question, and the run then owed it a
            # whole trading workflow (studies/challenges T1 Q4)
            return ("refused: a question asks what the run must find out, ending with '?'. To send work to a seat, "
                    "rework its order (rework) with done_when; a question owes the whole workflow")
        if type == "question":
            why = _not_a_question(str((fields or {}).get("text") or ""),
                                  [(q.get("code") or "", str((q.get("body") or {}).get("text") or ""))
                                   for q in (record.get(x["id"]) for x in record.search("", "question", inv, 200))])
            if why:
                return why
        try:
            ls = [dict(l, to=record.resolve(str(l["to"]), inv)) if l.get("to") else l for l in (links or [])]
            n = record.create(author=me, type=type, inv=inv, fields=fields, links=ls)
        except (GraphError, KeyError) as e:
            return _err(e)
        return f"added {n['code']}"

    def rework(order: str, missing: str, done_when: list[Any] | None = None) -> str:
        """Send an order back as a new order to the same worker, saying what was missing; done_when changes the
        predicates (a stuck predicate must change)."""
        try:
            r = record.rework(author=oa, order=record.resolve(order, inv), missing=missing, done_when=done_when)
        except (GraphError, KeyError) as e:
            return _err(e)
        return f"reworked as {r['code']}"

    def cancel_work(order: str, why: str) -> str:
        """Cancel an order, with the reason."""
        try:
            record.cancel_work(author=oa, order=record.resolve(order, inv), why=f"{me}: {why}")
        except (GraphError, KeyError) as e:
            return _err(e)
        return f"{order} cancelled"

    def report_facts() -> str:
        """The facts of the investigation generated from the record. Start the report from them."""
        return str(record.report(inv)["markdown"])

    def submit_report(text: str) -> str:
        """Submit the final report: the facts plus your interpretation. It is checked against the record; errors
        come back to fix."""
        r = record.check_text(text, inv)
        errs = [f for f in r["findings"] if f["level"] == "error"]
        if errs:
            report_box["refusals"] = int(report_box.get("refusals", 0)) + 1
            report_box.setdefault("refused", []).append([f"{f['code']}: {f['excerpt'][:100]}" for f in errs[:6]])
            return "report refused: " + "; ".join(f"line {f['line']} {f['code']}: {f['excerpt'][:100]} → "
                                                  f"{str(f.get('message') or '')[:200]}"
                                                  for f in errs[:6]) + " — fix these and submit again"
        if needs_answers and answers_block(text) is None:
            # gpt-oss put Python in submit_report's text: 4 of 17 runs ended on a "report" that was a code snippet,
            # accepted because the checks found no claim in it to refuse (BC-250, 2026-11-05)
            report_box["refusals"] = int(report_box.get("refusals", 0)) + 1
            report_box.setdefault("refused", []).append(["no answers block"])
            return ("report refused: it has no ```answers block. A report is prose for a reader: the facts from "
                    "report_facts, your interpretation under them, then the block of JSON the task asks for. Code "
                    "isn't a report")
        nulls = null_over_a_checked_claim(record, inv, text)
        if nulls:
            report_box["refusals"] = int(report_box.get("refusals", 0)) + 1
            report_box.setdefault("refused", []).append(nulls[:6])
            return ("report refused: " + "; ".join(nulls[:6]) + " — null means no claim answers the question. Write "
                    'the answer the claim gives (false or "no" for a negative, its words if it found nothing) and '
                    "submit again")
        report_box["text"] = text
        return "report accepted"

    def show(node: str) -> str:
        """A node's fields, standing and links."""
        try:
            n = record.get(record.resolve(node, inv))
        except (GraphError, KeyError) as e:
            return _err(e) + NOT_A_NODE
        return json.dumps({"code": n["code"], "type": n["type"], "standing": n["state"]["sentence"], "body": n["body"]},
                          default=str)[:6000]

    return [Tool.from_function(f) for f in (briefing, add, rework, cancel_work, report_facts, submit_report, show)]
