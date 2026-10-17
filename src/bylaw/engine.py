"""Evaluate one proposed tool call against a pack. Shared by the agent, the tuner and the benchmark,
so every number we report measures the same code path the live agent runs."""

from __future__ import annotations

import dataclasses
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

from bylaw import expr
from bylaw.decide import Verdict, decide
from bylaw.decider import to_wire
from bylaw.pack import Pack, pack_hash
from bylaw.state import render_state


class Escalator(Protocol):
    def judge(self, state: str, tool: str) -> Verdict: ...


@dataclass
class Receipt:
    tool: str
    args: dict
    verdict: Verdict
    decider_ms: float | None
    total_ms: float
    input_tokens: int
    pack_hash: str
    escalated: bool = False
    escalation: Verdict | None = None
    error: str | None = None
    answers: dict = field(default_factory=dict)
    at: str = field(default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds"))

    @property
    def effective(self) -> Verdict:
        return self.escalation if self.escalation is not None else self.verdict

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


def evaluate_call(pack: Pack, decider, tool: str, args: dict, context: dict,
                  conversation: list[tuple[str, str]], escalator: Escalator | None = None) -> Receipt:
    """Checks in code, every question in one Decider request, then the decision table.
    `DeciderUnavailable` propagates: the caller decides how to fail closed."""
    started = time.perf_counter()
    state = render_state(conversation, tool, args, context)
    env = {"args": args, "ctx": context, "tables": pack.tables}
    check_results = {c.id: expr.evaluate(c.expr, env) for c in pack.checks_for(tool)}

    asked = [q for q in pack.questions_for(tool) if q.when is None or expr.evaluate(q.when, env) is not False]
    questions = {q.id: to_wire(q) for q in asked}
    answers: dict[str, dict] = {}
    decider_ms = None
    tokens = 0
    if questions:
        result = decider.ask(state, questions)
        answers, decider_ms, tokens = result.answers, result.latency_ms, result.input_tokens

    verdict = decide(pack, tool, check_results, answers, skipped={q.id for q in pack.questions_for(tool)} - set(questions))
    escalation = escalator.judge(state, tool) if verdict.uncertain and escalator is not None else None
    return Receipt(tool=tool, args=args, verdict=verdict, decider_ms=decider_ms,
                   total_ms=(time.perf_counter() - started) * 1000, input_tokens=tokens,
                   pack_hash=pack_hash(pack), escalated=escalation is not None, escalation=escalation,
                   answers=answers)
