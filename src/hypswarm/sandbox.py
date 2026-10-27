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
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path


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
            p = subprocess.run([sys.executable, "-E", "-s", "-c", code], check=False, cwd=folder, capture_output=True,
                               text=True, timeout=seconds, env=env)
        except subprocess.TimeoutExpired:
            return f"error: no output within {seconds} s"
        out = p.stdout + ("\n[stderr]\n" + p.stderr if p.stderr.strip() else "")
        return out[:8000] or "(no output)"
    return python


__all__ = ["python_subprocess"]
