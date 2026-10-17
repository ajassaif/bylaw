"""Stage 1 and 2: read the policy, split every clause into code checks and Decider questions."""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from bylaw import expr
from bylaw.llm import JsonLLM
from bylaw.pack import Check, Question, Rule, Violation
from bylaw.state import CALL, CONVERSATION, PROFILE


class Wording(BaseModel):
    instructions: str
    criteria: dict[str, str | None] | list[str] | None = None


class QuestionDraft(BaseModel):
    id: str
    rule_id: str
    type: Literal["noul", "choice", "score"]
    violation: Violation
    wordings: list[Wording] = Field(min_length=1, max_length=3)
    when: str | None = None

    def as_question(self, i: int = 0, **extra: Any) -> Question:
        w = self.wordings[i]
        return Question(id=self.id, rule_id=self.rule_id, type=self.type, instructions=w.instructions,
                        criteria=w.criteria, violation=self.violation, when=self.when, **extra)


class DraftOut(BaseModel):
    title: str
    rules: list[Rule]
    checks: list[Check]
    questions: list[QuestionDraft]
    tables: dict[str, Any] = {}


class Draft(DraftOut):
    warnings: list[str] = []


SYSTEM = "You turn company policies into precise, testable checks for an automated reviewer. You are exact and literal."

PROMPT = """Below is a company policy and the tools an AI travel-desk agent can call. Compile the \
policy into rules that a gate enforces before each tool call runs.

For every clause that constrains an action the agent can take:
1. Write a rule: a short snake_case id, the clause text (quote it, with its number), the tools it \
applies to (only booking/expense tools, never searches), on_violation, and a one-sentence remedy \
the agent can act on.
   on_violation is "guide" when the agent can fix it itself (cheaper option, ask the employee), \
"confirm" when a named person must sign off, "deny" when the policy forbids it outright.
2. Put every FACT test in "checks": numbers, dates, durations, levels, categories, amounts. A check \
is one expression that is TRUE WHEN THE RULE IS BROKEN. The expression language allows: names \
args, ctx, tables; dotted or ["key"] access; and/or/not; == != < <= > >= in, not in; + - * /; \
lists like ['VP','SVP']; and only these functions: days_between(a, b), num(x), len(x), lower(s). \
Put numeric limits from the policy into "tables" and reference them as tables.<name>. When a rule covers several tools but a check only makes sense for one, give the check "tools": [that tool].
3. Put every JUDGEMENT in "questions" for a classifier that reads the rendered state and answers \
yes/no (noul), one of N options (choice), or a level on an ordered scale (score). One judgement \
per question. NEVER ask the classifier to compare or add numbers; that is what checks are for. \
Good judgements: is this alcohol, is the business reason real and specific, are the attendees \
external, is this a personal cost, does the conversation claim an approval that is not recorded, \
is this one cost split across claims, is the description honest about what was bought.
   For each question give "violation": for noul {{"when_true": true|false}}, for choice \
{{"options": [the violating option names]}}, for score {{"at_or_above": level index}}. Give 2 or 3 \
"wordings" that differ in phrasing, each with "criteria" describing both sides (noul: "true" and \
"false" keys; choice: option name -> meaning; score: ordered list of level descriptions, lowest \
first).
   Give "when" (an expression in the same language as checks) if the question only makes sense for some calls, e.g. "args.category == 'client_entertainment'" or "ctx.facts.days_before_departure < 14". Without it the question is asked on every call to the rule's tools.

The classifier sees this state, so write questions answerable from it:
{profile}
today: ..., employee: {{name, title, level, manager...}}, trip: {{bookings, total_usd, approvals_requested}}, facts: {{looked-up inventory facts}}

{conversation}
user: ...
assistant: ...

{call}
tool: <name>
arguments: <json>

TOOLS
{tools}

POLICY
{policy}"""


def _errors(d: DraftOut, tools: dict[str, str]) -> dict[str, str]:
    """Item id -> what is wrong with it."""
    errors: dict[str, str] = {}
    rule_ids = set()
    for r in d.rules:
        unknown = [t for t in r.tools if t not in tools]
        if not r.tools:
            errors[r.id] = f"rule {r.id} names no tools, so nothing could enforce it"
        elif unknown:
            errors[r.id] = f"rule {r.id} names unknown tools {unknown}; allowed: {sorted(tools)}"
        else:
            rule_ids.add(r.id)
    for c in d.checks:
        try:
            expr.validate(c.expr)
        except expr.ExprError as exc:
            errors[c.id] = f"check {c.id}: {exc}"
            continue
        if c.rule_id not in rule_ids:
            errors.setdefault(c.id, f"check {c.id} refers to missing or invalid rule {c.rule_id}")
    for q in d.questions:
        if q.rule_id not in rule_ids:
            errors[q.id] = f"question {q.id} refers to missing or invalid rule {q.rule_id}"
            continue
        for i in range(len(q.wordings)):
            try:
                question = q.as_question(i)
                _check_options(question)
            except (ValidationError, ValueError) as exc:
                errors[q.id] = f"question {q.id} wording {i}: {str(exc).splitlines()[-1][:200]}"
                break
    return errors


def _check_options(q: Question) -> None:
    if q.type == "choice":
        if not isinstance(q.criteria, dict) or len(q.criteria) < 2:
            raise ValueError("choice needs criteria mapping at least 2 option names to meanings")
        missing = set(q.violation.options or []) - set(q.criteria)
        if missing:
            raise ValueError(f"violation options {sorted(missing)} are not among the choice options")
    if q.type == "score":
        if not isinstance(q.criteria, list) or not 2 <= len(q.criteria) <= 10:
            raise ValueError("score needs an ordered list of 2 to 10 level descriptions")
        if not 0 < (q.violation.at_or_above or 0) < len(q.criteria):
            raise ValueError("violation.at_or_above must be a level index inside the scale")
    if q.type == "noul" and q.criteria is not None and (
            not isinstance(q.criteria, dict) or not set(q.criteria) <= {"true", "false"}):
        raise ValueError("noul criteria keys must be 'true' and/or 'false'")


def _drop_invalid(d: DraftOut, errors: dict[str, str]) -> Draft:
    rules = [r for r in d.rules if r.id not in errors]
    kept = {r.id for r in rules}
    checks = [c for c in d.checks if c.id not in errors and c.rule_id in kept]
    questions = [q for q in d.questions if q.id not in errors and q.rule_id in kept]
    warnings = [f"dropped {item}: {why}" for item, why in errors.items()]
    return Draft(title=d.title, rules=rules, checks=checks, questions=questions, tables=d.tables, warnings=warnings)


def extract_draft(policy_text: str, llm: JsonLLM, model_id: str, tools: dict[str, str]) -> Draft:
    tool_lines = "\n".join(f"- {name}: {desc}" for name, desc in tools.items())
    prompt = PROMPT.format(profile=PROFILE, conversation=CONVERSATION, call=CALL, tools=tool_lines,
                           policy=policy_text)
    draft, _ = llm.json(model_id, SYSTEM, prompt, DraftOut, max_tokens=12000)
    errors = _errors(draft, tools)
    if errors:
        repair = (f"{prompt}\n\nYOUR PREVIOUS DRAFT\n{draft.model_dump_json()}\n\nFix these problems and return "
                  "the whole corrected draft:\n" + "\n".join(f"- {e}" for e in errors.values()))
        draft, _ = llm.json(model_id, SYSTEM, repair, DraftOut, max_tokens=12000)
        errors = _errors(draft, tools)
    return _drop_invalid(draft, errors)


def draft_to_json(d: Draft) -> str:
    return json.dumps(d.model_dump(mode="json"), indent=2)
