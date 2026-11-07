"""The examples' python sandbox keeps a seat's output whatever bytes it prints. On Windows a print of an en dash came
out of the child as cp1252 byte 0x96 (the child ran with -E, which ignores PYTHONUTF8), the UTF-8 reader thread died
on it, and the call's whole output was lost; E1 spent 158 calls on nothing (BC-250, pa1, 2026-11-07)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples"))
from _common import python_sandbox  # noqa: E402


def test_a_raw_non_utf8_byte_doesnt_lose_the_output(tmp_path):
    run = python_sandbox(tmp_path, seconds=30)
    out = run("import sys\nsys.stdout.buffer.write(bytes([0x96]) + b' dash\\n')\nsys.stdout.flush()\nprint('after')")
    assert "dash" in out and "after" in out, out
    assert "error" not in out.lower()


def test_utf8_passes_through(tmp_path):
    run = python_sandbox(tmp_path, seconds=30)
    assert run("print('en – dash, café')").startswith("en – dash, café")
