"""The release workflow publishes only when the tag equals ``__version__``; pyproject must say the same. 0.1.0a4 was
tagged with pyproject bumped and ``__init__`` not, and never reached PyPI."""
import re
from pathlib import Path

import hypswarm


def test_the_package_and_pyproject_agree_on_the_version():
    py = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'^version = "(.+?)"', py, re.MULTILINE)
    assert m and m.group(1) == hypswarm.__version__
