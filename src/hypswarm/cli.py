"""The placeholder's command line: says where the real thing is."""

from __future__ import annotations

import sys

from . import __doc__ as _about
from . import __version__


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args and args[0] in ("--version", "-V"):
        print(f"hypswarm {__version__} (name reservation; the alpha is at https://github.com/voodoomods/hypswarm)")
        return 0
    print((_about or "").strip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
