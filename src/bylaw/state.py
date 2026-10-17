"""Render what the Decider sees for one proposed tool call.

The Decider server cuts a state that is too long for its window, and it would cut wherever it
likes. We bound the state ourselves so the two parts every question depends on, the employee
profile and the proposed call, always survive; the conversation gives way first, oldest turn first.
"""

from __future__ import annotations

import json
from typing import Any

PROFILE = "--- EMPLOYEE AND TRIP ---"
CONVERSATION = "--- CONVERSATION ---"
CALL = "--- PROPOSED TOOL CALL ---"
ELLIPSIS = "…"


def conversation_from_messages(messages: list[dict]) -> list[tuple[str, str]]:
    """Strands messages to (role, text) pairs. Tool-use and tool-result blocks are skipped."""
    turns: list[tuple[str, str]] = []
    for message in messages:
        role = message.get("role", "unknown")
        for block in message.get("content", []):
            if isinstance(block, dict) and isinstance(block.get("text"), str) and block["text"].strip():
                turns.append((role, block["text"].strip()))
    return turns


def _value(v: Any) -> str:
    if isinstance(v, dict | list):
        return json.dumps(v, sort_keys=True, separators=(",", ":"))
    return str(v)


def render_state(conversation: list[tuple[str, str]], tool: str, args: dict, context: dict,
                 max_turns: int = 12, max_chars: int = 6000) -> str:
    profile = "\n".join([PROFILE, *(f"{k}: {_value(v)}" for k, v in context.items())])
    call = f"{CALL}\ntool: {tool}\narguments: {json.dumps(args, sort_keys=True)}"
    fixed = len(profile) + len(CONVERSATION) + len(call) + 5  # five newlines joining the sections
    budget = max(0, max_chars - fixed)

    lines = [f"{role}: {text}" for role, text in conversation[-max_turns:]]
    while len(lines) > 1 and sum(len(line) + 1 for line in lines) > budget:
        lines.pop(0)
    if lines and len(lines[0]) + 1 > budget:
        keep = max(0, budget - 1 - len(ELLIPSIS))
        lines[0] = ELLIPSIS + lines[0][-keep:] if keep else ""
    body = "\n".join(line for line in lines if line) or "(no conversation yet)"

    return "\n".join([profile, "", CONVERSATION, body, "", call])
