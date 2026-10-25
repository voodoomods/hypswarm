"""A worker reads only bytes the record vouches for: a file matching a withdrawn artifact is refused with the
record's reason, an unregistered file is refused, a live one is read."""
import asyncio

from hypswarm import Seat
from hypswarm.files import file_tools, verify
from hypswarm.record import HARNESS, LocalRecord

SEATS = [Seat("analyst", "worker"), Seat("lead", "lead")]


def _seed(tmp_path):
    folder = tmp_path / "work"
    folder.mkdir()
    (folder / "site_a.csv").write_bytes(b"site,nitrate\nA,4.1\nA,3.9\n")
    (folder / "site_b.csv").write_bytes(b"site,nitrate\nB,43.2\nB,41.9\n")        # the corrupt original
    (folder / "site_b_fixed.csv").write_bytes(b"site,nitrate\nB,4.32\nB,4.19\n")
    (folder / "planted.csv").write_bytes(b"site,nitrate\nA,0.1\n")                 # never registered
    rec = LocalRecord(tmp_path / "r.hypgraph", SEATS)
    inv = rec.start("Nitrate at two sites.", "Which sites exceed the limit?", [("Q1", "Mean at A?")],
                    files={"site_a.csv": (folder / "site_a.csv").read_bytes(),
                           "site_b.csv": (folder / "site_b.csv").read_bytes()})
    return rec, inv, folder


def test_live_withdrawn_and_unknown(tmp_path):
    rec, inv, folder = _seed(tmp_path)
    tools = {t.name: t for t in file_tools(rec, inv, folder)}
    assert asyncio.run(tools["read_file"].call({"name": "site_a.csv"})).startswith("site,nitrate")
    assert "not registered" in asyncio.run(tools["read_file"].call({"name": "planted.csv"}))
    assert "not registered" in asyncio.run(tools["read_file"].call({"name": "site_b_fixed.csv"}))   # not yet
    # the notice: site_b.csv withdrawn, the corrected file registered
    stale = next(a for a in rec.search("site_b.csv", "artifact", inv) if a["title"] == "site_b.csv")
    rec.withdraw(author=HARNESS, node=stale["id"], why="site_b.csv was exported in µg/L, not mg/L")
    rec.create(author=HARNESS, type="artifact", inv=inv, fields={
        "sha256": __import__("hashlib").sha256((folder / "site_b_fixed.csv").read_bytes()).hexdigest(),
        "path": "site_b_fixed.csv", "size": 3, "format": "csv"})
    out = asyncio.run(tools["read_file"].call({"name": "site_b.csv"}))
    assert out.startswith("refused") and "withdrew" in out and "µg/L" in out
    assert asyncio.run(tools["read_file"].call({"name": "site_b_fixed.csv"})).startswith("site,nitrate\nB,4.32")
    listing = asyncio.run(tools["list_files"].call({}))
    assert "site_b.csv" in listing and "withdrawn" in listing and "planted.csv" in listing and "unknown" in listing
    assert verify(rec, inv, b"nonsense")["status"] == "unknown"


def test_paths_stay_inside_the_folder(tmp_path):
    rec, inv, folder = _seed(tmp_path)
    tools = {t.name: t for t in file_tools(rec, inv, folder)}
    assert asyncio.run(tools["read_file"].call({"name": "../r.hypgraph"})).startswith("refused")
