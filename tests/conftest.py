"""Tests run against the HypGraph source next to this repo when HYPGRAPH_SRC points at it or ../HypGraph/src
exists (the coordination layer isn't on PyPI yet); otherwise the installed hypgraph."""
import os
import sys
from pathlib import Path

src = os.environ.get("HYPGRAPH_SRC") or str(Path(__file__).resolve().parents[2] / "HypGraph" / "src")
if Path(src).exists():
    sys.path.insert(0, src)
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
