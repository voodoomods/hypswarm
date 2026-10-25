"""A small CSV importer. Issue #412: a comma inside a quoted field used to split the row."""
import csv
from pathlib import Path


def import_rows(path: str) -> list[dict[str, str]]:
    with Path(path).open(newline="", encoding="utf-8") as f:
        return [dict(r) for r in csv.DictReader(f)]
