"""The one thing a provider must do: turn messages and tools into a reply with usage."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from ..messages import Message, Reply, Tool


class ChatModel(Protocol):
    name: str

    async def complete(self, messages: Sequence[Message], tools: Sequence[Tool], *, temperature: float | None = None,
                       unit: str = "") -> Reply:
        """One model call. ``unit`` labels the call (order code) for the host's meter; it never changes the request
        except through headers the provider chooses to add."""
        ...
