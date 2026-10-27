"""
hypswarm.com's own HypGraph record: every figure on the homepage, bound to the measurement it came from, re-measured
by a second method, and the page copy linted against it — the site held to the rules HypSwarm runs agents under.

    python dev/site_record.py      # site/data/{site-record.bundle.json, homepage-checked.md}, site/assets/site-data.js

Three authors, as the record's roles intend:
- ``lab`` (the instrument) measures: the test suite, the pyproject's dependencies, and the five example runs the page
  replays (site/data/examples/*.bundle.json, from dev/site_examples.py): how many settled, and how many writes the
  record refused, both read from each run's telemetry;
- ``site`` writes the page's claims, each bound to the lab's result for its numbers;
- ``site-check`` (the reviewer) re-measures each another way — the suite run again and its tests counted by
  collection, the pyproject parsed with tomllib instead of a regex, the five examples run again from scratch with
  settling read from each record's completion and the refusals from its refusal log — and records what it found.

Then the page's text (site/index.html, figures filled in from the claims) goes through `hypgraph check` against this
record. Words quoted as examples of what gets refused are marked `data-quote`; a phrase true by design is marked
`data-ok="<why>"` and listed on the page.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
import sys
import tempfile
import time
import tomllib
from datetime import UTC, datetime
from pathlib import Path

from hypgraph import Graph, Policy, report_check
from hypgraph import derive as D
from hypgraph.bundle import verify_bundle

from hypswarm import __version__

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
PAGE = SITE / "index.html"
EXAMPLES = {"scientific": "01-eval-report", "software": "02-software-tests", "trading": "03-paper-trading",
            "knowledge": "04-sourced-brief", "optimization": "05-optimal-with-bound"}


def now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def sh(*cmd: str, cwd: Path = ROOT, timeout: int = 1800) -> subprocess.CompletedProcess:
    return subprocess.run(list(cmd), cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=timeout, check=False)


# ── measurements ────────────────────────────────────────────────────────────────────────────────────────────────
def run_tests() -> dict:
    t0 = now()
    p = sh(sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider")
    num = lambda w: int((re.search(rf"(\d+) {w}", p.stdout) or [0, 0])[1])
    return {"passed": num("passed"), "failed": num("failed"), "skipped": num("skipped"), "exit": p.returncode,
            "started": t0, "finished": now(), "cmd": "python -m pytest -q"}


def collect_tests() -> int:
    p = sh(sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider")
    return int((re.search(r"(\d+) tests? collected", p.stdout) or [0, 0])[1])


def deps_by_regex() -> int:
    txt = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    return len(re.findall(r'"[^"]+"', re.search(r"^dependencies = \[(.*?)\]", txt, re.MULTILINE | re.DOTALL).group(1)))


def deps_by_toml() -> int:
    return len(tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["dependencies"])


def runs_from_telemetry() -> dict:
    """The page's five runs, as their bundles' telemetry tells it: settled or not, and the writes refused."""
    out = {}
    for name in EXAMPLES:
        b = json.loads((SITE / "data" / "examples" / f"{name}.bundle.json").read_text(encoding="utf-8"))
        assert verify_bundle(b)["ok"], name
        tel = b["telemetry"]["events"]
        end = next((t for t in tel if t["kind"] == "run_end"), {})
        refused = sum(1 for t in tel if t["kind"] == "tool_end" and t.get("ok") is False and "refused" in (t.get("error") or ""))
        out[name] = {"settled": end.get("stopped") == "settled", "refused": refused}
    return out


def runs_fresh() -> dict:
    """The five examples run again from scratch: settled from each record's completion, refusals from its log."""
    out = {}
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        for name, folder in EXAMPLES.items():
            rec = Path(tmp) / f"{name}.hypgraph"
            sh(sys.executable, "run.py", "--fresh", "--quiet", "--record", str(rec), cwd=ROOT / "examples" / folder)
            g = Graph(rec)
            try:
                inv = g.investigations()[0]["id"]
                out[name] = {"settled": bool(g.completion(inv)["complete"]), "refused": g.refusal_report(inv)["refused"]}
            finally:
                g.close()
    return out


# ── the record ──────────────────────────────────────────────────────────────────────────────────────────────────
def build() -> tuple[Graph, str, dict]:
    g = Graph(Path(tempfile.mkdtemp()) / "site-record.hypgraph",
              policy=Policy(reviewers=frozenset({"site-check"}), max_creates_per_minute=10**6))
    site, lab, check = g.author("site"), g.author("lab"), g.author("site-check")
    inv = site.investigation("What the hypswarm.com homepage claims",
                             "Bind every figure on the homepage to the measurement it came from, and have each "
                             "re-measured another way before the page is published.")["id"]
    nodes: dict[str, dict] = {}

    def measure(key, question, run_name, code, summary, values, started, finished, exit_code=0):
        q = site.add("question", inv, text=question)["id"]
        r = lab.add("run", inv, kind="lab", state="succeeded" if exit_code == 0 else "failed", name=run_name,
                    code=[code], started=started, finished=finished, exit_code=exit_code)["id"]
        rs = lab.add("result", inv, kind="computed", outcome="positive" if exit_code == 0 else "failed", summary=summary,
                     values=values, links=[{"rel": "produced", "from": r}])["id"]
        nodes[key] = {"question": q, "result": rs}

    def claim(key, statement, scope, measurements):
        rs = nodes[key]["result"]
        cl = site.add("claim", inv, statement=statement, scope=scope,
                      measurements=[{**m, "result": rs} for m in measurements],
                      links=[{"rel": "answers", "to": nodes[key]["question"]}, {"rel": "derived_from", "to": rs},
                             {"rel": "supports", "from": rs, "why": "the lab's measurement of exactly this"}])
        nodes[key].update(claim=cl["id"], code=cl.get("code"))

    t = run_tests()
    total = t["passed"] + t["failed"]
    measure("tests", "Does the test suite pass, and how many tests does it run?", "The test suite", t["cmd"],
            f"pytest passed {t['passed']} of {total} tests run; {t['skipped']} skipped.",
            {"tests": {"k": t["passed"], "n": total}, "skipped": t["skipped"]}, t["started"], t["finished"], t["exit"])
    claim("tests", f"The test suite passes {t['passed']} of the {total} tests it runs; {t['skipped']} are skipped here.",
          f"hypswarm {__version__} at this commit; the skipped tests need optional extras this build doesn't install.",
          [{"name": "tests passed", "key": "tests", "k": t["passed"], "n": total},
           {"name": "skipped", "key": "skipped", "value": t["skipped"]}])

    d0 = now()
    deps = deps_by_regex()
    measure("deps", "How many runtime dependencies does the package declare?", "Read pyproject.toml",
            "count the strings in [project] dependencies", f"pyproject.toml declares {deps} runtime dependencies.",
            {"runtime_dependencies": deps}, d0, now())
    claim("deps", f"The package declares {deps} runtime dependencies.",
          f"pyproject.toml of hypswarm {__version__}; optional extras are not counted.",
          [{"name": "runtime dependencies", "key": "runtime_dependencies", "value": deps}])

    r0 = now()
    tel = runs_from_telemetry()
    settled, refused, n = sum(r["settled"] for r in tel.values()), sum(r["refused"] for r in tel.values()), len(tel)
    measure("settled", "Do the example runs the page replays settle?", "The five example runs' telemetry",
            "run_end.stopped in each site/data/examples/*.bundle.json", f"{settled} of {n} example runs settled.",
            {"settled": {"k": settled, "n": n}}, r0, now())
    claim("settled", f"{settled} of the {n} example runs on the page settled.",
          "Examples 01–05, one per profile, on scripted models (dev/site_examples.py).",
          [{"name": "runs settled", "key": "settled", "k": settled, "n": n}])
    measure("refused", "How many writes did the record refuse in those runs?", "The five example runs' telemetry",
            "tool calls the record refused, in each run's telemetry",
            f"The record refused {refused} writes across the {n} example runs.", {"refused_writes": refused, "runs": n},
            r0, now())
    claim("refused", f"The record refused {refused} writes across the {n} example runs on the page.",
          "Examples 01–05 on scripted models; some make a deliberately wrong first write.",
          [{"name": "refused writes", "key": "refused_writes", "value": refused}, {"name": "runs", "key": "runs", "value": n}])

    # ── the reviewer ──
    t2, c2 = run_tests(), collect_tests()
    check.review(nodes["tests"]["claim"], "replicated" if t2["passed"] == t["passed"] and c2 == total + t["skipped"] else "objection",
                 method="Ran python -m pytest -q again and counted the tests by collection.",
                 notes=f"Second run: {t2['passed']} passed, {t2['skipped']} skipped; {c2} collected.")
    dt = deps_by_toml()
    check.review(nodes["deps"]["claim"], "checked" if dt == deps else "objection",
                 method="Parsed pyproject.toml with tomllib instead of a regex.", notes=f"[project] dependencies has {dt} entries.")
    fresh = runs_fresh()
    s2, r2 = sum(r["settled"] for r in fresh.values()), sum(r["refused"] for r in fresh.values())
    check.review(nodes["settled"]["claim"], "replicated" if s2 == settled else "objection",
                 method="Ran the five examples again from scratch and read each record's completion.",
                 notes=f"{s2} of {len(fresh)} complete.")
    check.review(nodes["refused"]["claim"], "replicated" if r2 == refused else "objection",
                 method="Ran the five examples again from scratch and read each record's refusal log.",
                 notes=f"{r2} refusals logged.")
    facts = {"tests": t, "total": total, "deps": deps, "settled": settled, "n": n, "refused": refused}
    return g, inv, {"facts": facts, "nodes": nodes}


def fill(f: dict) -> dict:
    t = f["tests"]
    return {"tests": f"{t['passed']} of {f['total']}", "tests-s": f"passing on this build; {t['skipped']} skipped here (optional extras not installed)",
            "deps": str(f["deps"]), "settled": f"{f['settled']} of {f['n']}", "refused": str(f["refused"]),
            "version-pill": f"v{__version__}", "licence": "Apache-2.0"}


def page_text(values: dict) -> tuple[str, list[dict]]:
    body = PAGE.read_text(encoding="utf-8").split("<main", 1)[1].split("</main>", 1)[0]
    ok = [{"text": html.unescape(re.sub(r"<[^>]+>", "", m.group(2))), "why": html.unescape(m.group(1))}
          for m in re.finditer(r'<span data-ok="([^"]*)">(.*?)</span>', body, re.DOTALL)]
    body = re.sub(r'<span data-ok="[^"]*">(.*?)</span>', " ", body, flags=re.DOTALL)
    body = re.sub(r"<span data-quote>.*?</span>", " ", body, flags=re.DOTALL)
    body = re.sub(r"<(script|pre|code)\b.*?</\1>", " ", body, flags=re.DOTALL)
    for k, v in values.items():
        body = re.sub(rf'(<[^>]*data-fact="{k}"[^>]*>)[^<]*', lambda m, v=v: m.group(1) + v, body)
    text = re.sub(r"</(p|h1|h2|h3|li|div|td|th|tr|section)>", "\n", body)
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    text = "\n".join(re.sub(r"\s+", " ", ln).strip() for ln in text.splitlines())
    return re.sub(r"\n{2,}", "\n\n", text).strip() + "\n", ok


def main() -> None:
    argparse.ArgumentParser(description=__doc__.splitlines()[1]).parse_args()
    t0 = time.time()
    g, inv, built = build()
    values = fill(built["facts"])
    text, ok = page_text(values)
    lint = report_check.check(g, text, inv)
    b = g.export(inv)
    assert verify_bundle(b)["ok"]
    (SITE / "data").mkdir(exist_ok=True)
    (SITE / "data" / "site-record.bundle.json").write_text(json.dumps(b, ensure_ascii=False, separators=(",", ":")),
                                                           encoding="utf-8")
    (SITE / "data" / "homepage-checked.md").write_text(
        "<!-- the homepage's text as `hypgraph check` read it, figures filled in from the page's record "
        "(dev/site_record.py) -->\n\n" + text, encoding="utf-8")
    s = g.snapshot()
    standing = {}
    for key, n in built["nodes"].items():
        st = D.state(s, n["claim"])
        rv = st.get("review", {})
        standing[key] = {"code": n["code"], "id": n["claim"], "review": rv.get("state"),
                         "verdicts": rv.get("positive", []) + rv.get("negative", []),
                         "statement": s.nodes[n["claim"]]["body"].get("statement", ""), "summary": st.get("sentence", "")}
    g.close()
    data = {"facts": values, "standing": standing, "lint": lint, "data_ok": ok, "inv": inv, "built": now(), "head": b["head"]}
    (SITE / "assets" / "site-data.js").write_text("// generated by dev/site_record.py — do not edit\nwindow.SITE_DATA = "
                                                  + json.dumps(data, indent=1, ensure_ascii=False) + ";\n", encoding="utf-8")
    print(f"record: {len(b['events'])} events, {len(b['nodes'])} nodes, chain head {b['head'][:16]}…")
    for key, st in standing.items():
        print(f"  {st['code']:5} {key:9} {st['review']}")
    print(f"copy check: {lint['errors']} error(s), {lint['warnings']} warning(s), {lint['notes']} note(s); "
          f"{len(ok)} phrase(s) true by design")
    for f in lint["findings"]:
        print(f"  line {f['line']} {f['level']}: {f['code']}: {f['excerpt'][:90]} — {f['message'][:140]}")
    print(f"({time.time() - t0:.0f} s)")
    sys.exit(1 if lint["errors"] else 0)


if __name__ == "__main__":
    main()
