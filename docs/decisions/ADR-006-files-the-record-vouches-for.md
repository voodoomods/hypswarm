# ADR-006 — A worker reads only bytes the record vouches for

**Date** 2026-10-25 · **Status** accepted · **Review finding** #6 (medium)

## Context

Data files reach workers as bytes in a working folder. The record holds each file as an artifact (sha256, path),
and a notice can withdraw one (the corrupt `site_b.csv` in the F7 family) and register its replacement — but
nothing checked the bytes a worker actually read against the record. A stale file still in the folder, or a file
nobody registered, could become evidence by being read.

## Decision

`hypswarm.files.file_tools(record, inv, folder)` gives a swarm `list_files` and `read_file` that consult the
record before trusting bytes:

- **live** — the sha256 matches an active artifact of the investigation: the file is read;
- **withdrawn** — it matches an artifact the record withdrew: refused, with the record's reason (`withdrawn.why`)
  and a pointer to the live replacement;
- **unknown** — no artifact has these bytes: refused ("not evidence").

Paths are confined to the folder. `verify(record, inv, data)` is the same check as a function, for hosts with
their own file tools. The study's A–D runner keeps its own sandboxed tools as preregistered; condition E adopts
these in its next deviation.

## Alternatives considered

- Trusting the folder and relying on the notice text: that is exactly the stale-premise trap B falls for.
- Deleting withdrawn files from the folder: the harness can't always (an outside seat's machine); the record's
  verdict travels with the bytes, a deletion doesn't.

## Consequences

- A planted or stale file cannot be read into a run: `tests/test_files.py` plants one, withdraws another with a
  reason, registers the corrected file, and checks each verdict and the listing.
- One `record.search` + one `get` per artifact on every read: fine at the sizes a task has (tens of files); a
  host with thousands should cache by sha256 for the run.
