# 10 · Your own seat and your own toolkit, from scratch

**Profile** `scientific` · **seats** stats (your code), critic, lead · **toolkits** files, `csvstats` (yours)

Two extension points, nothing else.

```bash
python run.py --fresh
```

## A toolkit

```python
def csvstats_factory(ctx: ToolContext) -> list[Tool]:      # ctx: record, investigation, working folder
    def column_stats(file: str, column: str) -> dict:
        """Mean, median, min, max and n of a numeric column of a CSV in your working folder."""
        ...
    return [Tool.from_function(column_stats)]

toolkits.register("csvstats", csvstats_factory, "mean / median / min / max of a CSV column")
run(task, seats, models, folder=work, toolkits=["files", "csvstats"])
```

A factory is called once per run with the record, the investigation and the folder; a `Tool` is a function with
typed parameters and a docstring (the schema is built from them). Every worker whose seat allows it gets the
tool; `Seat(tools=("column_stats", "read_file"))` restricts a seat to named tools.

## A seat held by code

```python
async def stats_agent(order: AgentOrder) -> AgentOutcome:
    tool = {t.name: t for t in order.tools}               # the record's tools + your toolkits, as hypswarm Tools
    st = json.loads(await tool["column_stats"].call({"file": file, "column": column}))
    out = await tool["register_run"].call({... "values": {...}, "code": ..., "claim": ..., "answers": q, "scope": ...})
    if "return_work now" in out:
        await tool["return_work"].call({"note": "…"})
    return AgentOutcome(note="done", calls=0)

Seat("stats", "worker", agent=stats_agent, tools=("column_stats", "list_files", "read_file"))
```

An agent gets the order text, the system prompt a native seat would get, the tools, and how many calls are left.
It returns what it used (calls, tokens) and a note; if it didn't return the order itself, hypswarm returns it with
the note. This one calls no model at all — and the record treats it exactly like a seat held by a frontier model:
same order, same refusals, same instrument re-run of the code it registered.

```
=== SETTLED in 1.2s — 5 calls ===
  Q1   settled      CL1 (checked by critic)
```

The framework bridges (`hypswarm.bridges`) are this same function written three times — for LangChain, PydanticAI
and CrewAI. Write a fourth for yours.
