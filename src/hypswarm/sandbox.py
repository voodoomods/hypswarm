"""
A python tool for a working folder: a subprocess with a clean environment and a time limit. It is what
``hypswarm run --python`` gives the seats, and the instrument that re-runs their registered code. It is your own
machine, not a security boundary: the code a model writes runs as you. Register your own sandbox for anything
stronger (``toolkits.register("python", …)`` and ``run(..., reproducer=…)``).

    from hypswarm.sandbox import python_subprocess
    py = python_subprocess(Path("work"))
    run(task, seats, model, data_tools=[Tool.from_function(py, name="python")], reproducer=py, folder="work")
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

_COMMAND = re.compile(r"^(?:\$\s*)?(python3?|py|pytest|py\.test)(?=\s|$)")


def as_python(code: str) -> str:
    """Python for what a seat gave as code. Seats are told to register "the exact test command", and they do:
    ``python -m pytest test_x.py`` went to ``python -c``, was a SyntaxError on every re-run, and neither code-fix
    challenge settled anything (BC-250, 2026-11-05). One line that isn't Python and starts with python or pytest runs
    as that command; anything else is left to fail as it would."""
    line = code.strip()
    if "\n" in line:
        return code
    try:
        compile(line, "<code>", "exec")
        return code
    except (SyntaxError, ValueError):
        pass
    m = _COMMAND.match(line)
    if not m:
        return code
    try:
        words = shlex.split(line[m.end():])
    except ValueError:
        return code
    args = ["-m", "pytest", *words] if m.group(1).startswith(("pytest", "py.test")) else words
    return ("import subprocess, sys\n"
            f"r = subprocess.run([sys.executable, *{args!r}], capture_output=True, text=True)\n"
            "print(r.stdout)\nprint(r.stderr, file=sys.stderr)\nprint('exit code', r.returncode)\n")


def python_subprocess(folder: Path, seconds: int = 60) -> Callable[[str], str]:
    """``python(code) -> output``, run in ``folder`` with ``sys.executable -E -s``, at most ``seconds``. Scratch goes to
    a temp folder outside ``folder``: under the software workflow the folder is the watched tree, and every scratch file
    written there was a new head."""
    folder = Path(folder)
    scratch = Path(tempfile.mkdtemp(prefix="hypswarm-scratch-"))
    env = {"PATH": os.environ.get("PATH", ""), "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
           "SYSTEMDRIVE": os.environ.get("SYSTEMDRIVE", ""),        # unset, a library made a literal %SystemDrive%/
           "TMPDIR": str(scratch), "TEMP": str(scratch), "TMP": str(scratch)}

    def python(code: str) -> str:
        """Run python 3 in the working folder (the task's files are there); print what you need. Write scratch files
        under tempfile.gettempdir(), not the working folder."""
        try:
            p = subprocess.run([sys.executable, "-E", "-s", "-c", as_python(code)], check=False, cwd=folder,
                               capture_output=True, text=True, timeout=seconds, env=env)
        except subprocess.TimeoutExpired:
            return f"error: no output within {seconds} s"
        out = p.stdout + ("\n[stderr]\n" + p.stderr if p.stderr.strip() else "")
        return out[:8000] or "(no output)"
    return python


__all__ = ["as_python", "python_subprocess"]
