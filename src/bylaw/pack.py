"""The policy pack: what the compiler writes and what the gate loads.

A pack is plain data. Rules carry the policy's intent, checks carry the facts that code can
decide on its own, and questions carry the judgements handed to Strands Decider 2B.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, model_validator

Action = Literal["proceed", "guide", "confirm", "deny"]
OnViolation = Literal["guide", "confirm", "deny"]
ACTIONS: tuple[Action, ...] = ("proceed", "guide", "confirm", "deny")


class Rule(BaseModel):
    id: str
    text: str
    tools: list[str]
    on_violation: OnViolation
    remedy: str


class Check(BaseModel):
    """A restricted expression (see `bylaw.expr`). True means the rule is violated."""

    id: str
    rule_id: str
    expr: str
    description: str


class Violation(BaseModel):
    """Which answer counts as breaking the rule. Exactly one field is set, matching the question type."""

    when_true: bool | None = None
    options: list[str] | None = None
    at_or_above: int | None = None


class QuestionMetrics(BaseModel):
    n: int
    accuracy: float
    brier: float
    candidates: int


_VIOLATION_FIELD = {"noul": "when_true", "choice": "options", "score": "at_or_above"}


class Question(BaseModel):
    id: str
    rule_id: str
    type: Literal["noul", "choice", "score"]
    instructions: str
    criteria: dict[str, str | None] | list[str] | None = None
    violation: Violation
    lo: float = 0.2
    hi: float = 0.8
    dev: QuestionMetrics | None = None

    @model_validator(mode="after")
    def _violation_matches_type(self) -> Question:
        set_fields = {k for k, v in self.violation.model_dump().items() if v is not None}
        expected = _VIOLATION_FIELD[self.type]
        if set_fields != {expected}:
            raise ValueError(f"{self.type} question {self.id} needs violation.{expected} and nothing else")
        if not 0.0 <= self.lo <= self.hi <= 1.0:
            raise ValueError(f"question {self.id}: thresholds must satisfy 0 <= lo <= hi <= 1")
        return self


class Pack(BaseModel):
    version: Literal[1] = 1
    policy_title: str
    policy_sha256: str
    compiled_at: str
    models: dict[str, str]
    rules: list[Rule]
    checks: list[Check]
    questions: list[Question]
    tables: dict[str, Any] = {}

    @model_validator(mode="after")
    def _references_exist(self) -> Pack:
        rule_ids = {r.id for r in self.rules}
        for item in [*self.checks, *self.questions]:
            if item.rule_id not in rule_ids:
                raise ValueError(f"{item.id} refers to unknown rule {item.rule_id}")
        return self

    def rule(self, rule_id: str) -> Rule:
        return next(r for r in self.rules if r.id == rule_id)

    def _rules_for(self, tool: str) -> set[str]:
        return {r.id for r in self.rules if tool in r.tools}

    def questions_for(self, tool: str) -> list[Question]:
        ids = self._rules_for(tool)
        return [q for q in self.questions if q.rule_id in ids]

    def checks_for(self, tool: str) -> list[Check]:
        ids = self._rules_for(tool)
        return [c for c in self.checks if c.rule_id in ids]

    def gated_tools(self) -> set[str]:
        return {t for r in self.rules for t in r.tools}


def load_pack(path: str | Path) -> Pack:
    return Pack.model_validate_json(Path(path).read_text(encoding="utf-8"))


def save_pack(pack: Pack, path: str | Path) -> None:
    Path(path).write_text(pack.model_dump_json(indent=2), encoding="utf-8")


def pack_hash(pack: Pack) -> str:
    canonical = json.dumps(pack.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:12]
