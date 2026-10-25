"""
Condition P: one agent, the same model, the same tools, the profile's rules in the prompt — and no record.
It is hypswarm's own worker loop with the record's tools taken away, so the only difference from R is enforcement.
The final assistant message is the artifact. Calls and tokens are counted the same way R counts them.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from hypswarm import profiles
from hypswarm.messages import Message, Tool
from hypswarm.providers.base import ChatModel

ANSWERS = ("End with a fenced block that starts with ```answers and holds one JSON object: each question code -> the answer "
           "(null if unanswered).")


@dataclass
class PResult:
    artifact: str = ""
    calls: int = 0
    input_tokens: int = 0
    cached_tokens: int = 0
    output_tokens: int = 0
    stopped: str = ""
    tool_log: list[dict[str, Any]] = field(default_factory=list)
    seconds: float = 0.0


def rules_text(profile: str) -> str:
    sp = profiles.get(profile)
    return f"PROFILE {sp.id} — {sp.about}\n{sp.notes}".strip()


def system_prompt(profile: str, mission: str, questions: list[tuple[str, str]], files: list[str]) -> str:
    qs = "\n".join(f"- {c}: {t}" for c, t in questions)
    return (f"You are a careful analyst working alone. Do the work with the tools; every number you report must come from "
            f"a tool's output.\n\nRULES (follow them exactly)\n{rules_text(profile)}\n\nMISSION\n{mission}\n\nQUESTIONS\n{qs}\n\n"
            f"FILES: {', '.join(files) or 'none'}\n\nFINAL ANSWER FORMAT\n{ANSWERS}")


async def run_p(model: ChatModel, profile: str, mission: str, questions: list[tuple[str, str]], files: list[str],
                tools: list[Tool], *, max_calls: int = 60, unit: str = "P") -> PResult:
    res = PResult()
    by = {t.name: t for t in tools}
    messages = [Message("system", system_prompt(profile, mission, questions, files)),
                Message("user", "Begin. Write the final report when you have the answers.")]
    t0 = time.time()
    for _ in range(max_calls):
        try:
            reply = await model.complete(messages, tools, unit=unit)
        except Exception as e:  # noqa: BLE001
            res.stopped = f"error: {type(e).__name__}: {str(e)[:160]}"
            break
        res.calls += 1
        res.input_tokens += reply.input_tokens
        res.cached_tokens += reply.cached_tokens
        res.output_tokens += reply.output_tokens
        messages.append(reply.as_message())
        if not reply.tool_calls:
            res.artifact = reply.content
            res.stopped = "done"
            break
        for tc in reply.tool_calls:
            tool = by.get(tc.name)
            out = await tool.call(tc.args) if tool else f"error: there is no tool {tc.name!r}"
            res.tool_log.append({"tool": tc.name, "args": tc.args, "out": out[:1500]})
            messages.append(Message("tool", out[:12000], tool_call_id=tc.id))
    else:
        res.stopped = "calls"
        last = next((m.content for m in reversed(messages) if m.role == "assistant" and m.content.strip()), "")
        res.artifact = last
    res.seconds = round(time.time() - t0, 1)
    return res
