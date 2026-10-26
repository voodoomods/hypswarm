"""
02 · Software — the instrument runs the tests, not the tester.

A CSV importer must keep a comma inside a quoted field. The tester registers the exact pytest command as the code
of its run; the instrument re-executes it in the sandbox and files a lab run. ``tests_pass`` is met by that run —
the tester's own report of passing never meets it, and a claim that says "passes" before the instrument has run
is refused with PASS_WITHOUT_INSTRUMENT_RUN. The scripted tester writes that claim too early on purpose, so the
trace shows the refusal, the rework, and the accepted claim after the lab run lands.

    python run.py
    python run.py --model deepseek-ai/DeepSeek-V4.1-Flash --fresh
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _common import budget, cli, main, models, pricing, register_python, reproducer, show, stage

from hypswarm import Seat, Task, run

HERE = Path(__file__).resolve().parent
FILES = {p.relative_to(HERE / "src").as_posix(): p.read_bytes() for p in (HERE / "src").rglob("*") if p.is_file()}

if __name__ == "__main__":
    args = cli("02 · software: the instrument runs the tests", HERE)
    work = stage(HERE, FILES)
    register_python(work)
    task = Task(title="Importer keeps quoted commas", profile="software",
                mission="The CSV importer in importer.py must keep a comma inside a quoted field (issue #412). "
                        "Verify it against fixtures/quoted.csv and the test file. Run the tests with python "
                        "(subprocess pytest) and register the exact command as your run's code.",
                questions=[("Q1", "Does import_rows('fixtures/quoted.csv') return 3 rows with the comma kept inside the quoted field?"),
                           ("Q2", "Do all tests in test_importer.py pass?")],
                files=FILES)
    code_q1 = ("from importer import import_rows\nrows = import_rows('fixtures/quoted.csv')\nprint('rows', len(rows))\n"
               "print('comma_kept', int(any(',' in v for r in rows for v in r.values())))")
    code_q2 = ("import subprocess, sys\nr = subprocess.run([sys.executable, '-m', 'pytest', '-q', 'test_importer.py'], capture_output=True, text=True)\n"
               "print(r.stdout[-300:])\nimport re\nm = re.search(r'(\\d+) passed', r.stdout)\n"
               "print('passed', int(m.group(1)) if m else 0, 'of', 3)\nprint('exit_code', r.returncode)")
    # the change under test, as the software workflow wants it: a diff artifact by hash (base → head, files). The
    # example starts from the fixed tree, so the base is the issue's tag; the head is the file as it is.
    import hashlib
    head = hashlib.sha256(FILES["importer.py"]).hexdigest()
    diff = {"sha256": head, "path": "importer.py", "kind": "diff",
            "meta": {"base_sha": "issue-412-base", "head_sha": head[:12], "files": ["importer.py"]}}
    answers = {
        "Q1": {"summary": "Imported fixtures/quoted.csv and checked the quoted comma survived.",
               "values": {"rows": {"value": 3}, "comma_kept": {"value": 1}}, "code": code_q1, "artifact": diff,
               "claim": "import_rows keeps the comma inside the quoted field of fixtures/quoted.csv.",
               "scope": "importer.py at this commit; fixtures/quoted.csv, 3 rows.", "answer": "yes"},
        "Q2": {"summary": "Ran pytest -q test_importer.py.", "values": {"passed": {"k": 3, "n": 3}, "exit_code": {"value": 0}},
               "code": code_q2, "outcome": "positive", "artifact": diff,
               "claim": "The importer passes all 3 of 3 tests in test_importer.py.",
               "scope": "test_importer.py at this commit, run by the instrument.", "answer": "yes"},
    }
    seats = [Seat("implementer", "worker", takes=("import_rows", "rows", "field")), Seat("tester", "worker", takes=("tests", "pass", "pytest")),
             Seat("reviewer", "reviewer"), Seat("lead", "lead")]
    res = main(run(task, seats, models(args, answers), record=args.record, budget=budget(args), pricing=pricing(args),
                   folder=work, toolkits=["files", "python"], reproducer=reproducer(work)))
    show(res, quiet=args.quiet, trace=args.trace)
