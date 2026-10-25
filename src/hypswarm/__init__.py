"""
hypswarm — run one agent or a swarm of them on a task, with a HypGraph record as the only shared state.

The record schedules the work (orders from the question board), accepts it (predicates, settled by the record),
stops what became pointless (premises that fell) and writes the report; models are called only to do work and
to judge exceptions. A solo scientist and an orchestrated swarm are the same program with different seats.

    from hypswarm import Task, Seat, Budget, run
    result = asyncio.run(run(Task(...), seats=[Seat(...), ...], record="study.hypgraph", budget=Budget(max_usd=2)))
"""

from . import profiles, toolkits
from .budget import Budget, Meter, Pricing
from .files import file_tools
from .http_record import HttpRecord
from .run import RunResult, Task, run
from .seats import Seat

__version__ = "0.1.0a1"
__all__ = ["Budget", "HttpRecord", "Meter", "Pricing", "RunResult", "Seat", "Task", "__version__", "file_tools", "profiles", "run", "toolkits"]
