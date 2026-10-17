"""Labelled test cases: one proposed tool call, the state around it, and the verdict it deserves."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from bylaw.agent.session import Session
from bylaw.pack import Action


class Case(BaseModel):
    id: str
    tool: str
    args: dict
    context: dict
    conversation: list[tuple[str, str]]
    expected: Action
    rule_id: str | None = None
    tags: list[str] = []
    source: str
    review: str | None = None


class CaseDraft(BaseModel):
    """What a generator writes. The context is rebuilt from fixtures so it stays grounded."""

    employee_id: str
    tool: str
    args: dict
    conversation: list[tuple[str, str]]
    expected: Action
    rule_id: str | None = None
    tags: list[str] = []
    facts: dict | None = None
    trip: dict | None = None


def build_context(employee_id: str, tool: str, args: dict, facts: dict | None = None,
                  trip: dict | None = None) -> dict:
    """The context the live gate would see: fixtures first, generator-supplied values only where the
    fixtures have nothing (a city we have no hotels for, a trip already under way)."""
    session = Session(employee_id)
    ctx = session.context()
    if trip:
        ctx["trip"] = {**ctx["trip"], **trip}
    ctx["facts"] = session.facts_for(tool, args) or (facts or {})
    return ctx


def from_draft(d: CaseDraft, case_id: str, source: str) -> Case:
    from bylaw.agent.tools import args_problem

    if problem := args_problem(d.tool, d.args):
        raise ValueError(f"{d.tool}: {problem}")
    return Case(id=case_id, tool=d.tool, args=d.args, conversation=d.conversation, expected=d.expected,
                rule_id=d.rule_id, tags=d.tags, source=source,
                context=build_context(d.employee_id, d.tool, d.args, d.facts, d.trip))


def question_label(case: Case, q) -> bool | None:
    """Is `q`'s rule broken in this case? None when the case says nothing about that rule."""
    if case.rule_id == q.rule_id and case.expected != "proceed":
        return True
    if case.expected == "proceed":
        return False
    return None


def load_cases(path: str | Path) -> list[Case]:
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return [Case.model_validate_json(line) for line in lines if line.strip()]


def save_cases(cases: list[Case], path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("".join(c.model_dump_json() + "\n" for c in cases), encoding="utf-8")
