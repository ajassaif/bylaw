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
OMITTED = "(earlier conversation omitted)"
MAX_ARG_CHARS = 400      # one free-text argument (a description, a justification)
MAX_PROFILE_LINE = 700   # one line of the profile (the trip ledger can grow with every booking)


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


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: max(0, limit - len(ELLIPSIS))] + ELLIPSIS


def _clip_args(args: dict) -> dict:
    return {k: _clip(v, MAX_ARG_CHARS) if isinstance(v, str) else v for k, v in args.items()}


def render_state(conversation: list[tuple[str, str]], tool: str, args: dict, context: dict,
                 max_turns: int = 12, max_chars: int = 6000) -> str:
    call = f"{CALL}\ntool: {tool}\narguments: {json.dumps(_clip_args(args), sort_keys=True)}"
    call = _clip(call, max_chars // 3)
    profile_lines = [PROFILE, *(_clip(f"{k}: {_value(v)}", MAX_PROFILE_LINE) for k, v in context.items())]
    profile = _clip("\n".join(profile_lines), max_chars - len(call) - len(CONVERSATION) - len(OMITTED) - 8)
    fixed = len(profile) + len(CONVERSATION) + len(call) + 5  # five newlines joining the sections
    budget = max(0, max_chars - fixed - len(OMITTED) - 1)

    lines = [f"{role}: {text}" for role, text in conversation[-max_turns:]]
    while len(lines) > 1 and sum(len(line) + 1 for line in lines) > budget:
        lines.pop(0)
    if lines and len(lines[0]) + 1 > budget:
        keep = max(0, budget - 1 - len(ELLIPSIS))
        lines[0] = ELLIPSIS + lines[0][-keep:] if keep else ""
    lines = [line for line in lines if line]
    if conversation and len(lines) < len(conversation):
        lines.insert(0, OMITTED)
    body = "\n".join(lines) or "(no conversation yet)"

    return "\n".join([profile, "", CONVERSATION, body, "", call])
