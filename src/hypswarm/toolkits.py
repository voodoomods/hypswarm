"""
The tool registry: named bundles of tools a host can hand a swarm by name, and that a profile can ask for.

    from hypswarm import toolkits
    toolkits.register("python", lambda ctx: [Tool.from_function(my_python)])     # the host's own sandbox
    tools = toolkits.build(["files", "python"], ctx)                              # for run(..., data_tools=tools)

A factory takes a ``ToolContext`` (record, investigation, working folder) and returns tools. hypswarm ships
``files`` (list_files / read_file that trust only bytes the record vouches for — ADR-006); everything that executes
code or reaches a network is the host's to register, so the swarm never runs anything the host did not choose.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .files import file_tools
from .messages import Tool


@dataclass(frozen=True)
class ToolContext:
    record: Any
    inv: str
    folder: Path | None = None


Factory = Callable[[ToolContext], list[Tool]]
_REGISTRY: dict[str, tuple[Factory, str]] = {}


def register(name: str, factory: Factory, about: str = "") -> None:
    """Add (or replace) a bundle. Names are lower-case identifiers."""
    key = name.strip().lower()
    if not key.isidentifier():
        raise ValueError(f"toolkit name {name!r}: letters, digits and underscores")
    _REGISTRY[key] = (factory, about)


def names() -> list[str]:
    return sorted(_REGISTRY)


def describe() -> dict[str, str]:
    return {k: v[1] for k, v in sorted(_REGISTRY.items())}


def build(wanted: Iterable[str], ctx: ToolContext) -> list[Tool]:
    """The tools of the named bundles, in order; an unknown name is an error (a profile that asks for `python` on a
    host that registered none should fail loudly, not run without it)."""
    out: list[Tool] = []
    for name in wanted:
        key = name.strip().lower()
        if key not in _REGISTRY:
            raise KeyError(f"no toolkit {name!r}; registered: {', '.join(names()) or 'none'} — the host registers its own "
                           "with toolkits.register(name, factory)")
        out += _REGISTRY[key][0](ctx)
    return out


def _files(ctx: ToolContext) -> list[Tool]:
    if ctx.folder is None:
        return []
    return file_tools(ctx.record, ctx.inv, ctx.folder)


register("files", _files, "list_files / read_file over the working folder; only bytes matching a live artifact are read")

__all__ = ["Factory", "ToolContext", "build", "describe", "names", "register"]
