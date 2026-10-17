"""Turn check results and Decider answers into one verdict. Pure: no I/O, no clock.

The model classifies; this table decides. Every branch is ordinary control flow over numbers,
so an agent cannot talk its way past it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from bylaw.pack import Action, Pack, Question

SEVERITY = {"guide": 1, "confirm": 2, "deny": 3}


def violation_probability(q: Question, answer: dict) -> float:
    """How likely the answer means the rule was broken, whatever the question type."""
    v = q.violation
    if q.type == "noul":
        p_true = float(answer["noul"])
        return p_true if v.when_true else 1.0 - p_true
    probs = answer["probabilities"]
    if q.type == "choice":
        return float(sum(probs.get(o, 0.0) for o in v.options or []))
    return float(sum(p for level, p in probs.items() if int(level) >= (v.at_or_above or 0)))


@dataclass(frozen=True)
class Finding:
    rule_id: str
    source: Literal["check", "decider"]
    item_id: str
    p_violation: float | None
    status: Literal["violation", "clear", "uncertain"]


@dataclass(frozen=True)
class Verdict:
    action: Action
    rule_id: str | None
    message: str
    confidence: float
    uncertain: bool
    findings: tuple[Finding, ...]


def _findings(pack: Pack, tool: str, check_results: Mapping[str, bool | None],
              answers: Mapping[str, dict]) -> list[Finding]:
    found: list[Finding] = []
    for c in pack.checks_for(tool):
        result = check_results.get(c.id)
        if result is True:
            found.append(Finding(c.rule_id, "check", c.id, 1.0, "violation"))
        elif result is False:
            found.append(Finding(c.rule_id, "check", c.id, 0.0, "clear"))
        else:
            found.append(Finding(c.rule_id, "check", c.id, None, "uncertain"))
    for q in pack.questions_for(tool):
        answer = answers.get(q.id)
        try:
            p = violation_probability(q, answer) if answer else None
        except (KeyError, TypeError, ValueError):
            p = None
        if p is None:
            status = "uncertain"
        elif p >= q.hi:
            status = "violation"
        elif p <= q.lo:
            status = "clear"
        else:
            status = "uncertain"
        found.append(Finding(q.rule_id, "decider", q.id, p, status))
    return found


def decide(pack: Pack, tool: str, check_results: Mapping[str, bool | None],
           answers: Mapping[str, dict]) -> Verdict:
    findings = _findings(pack, tool, check_results, answers)
    order = {r.id: i for i, r in enumerate(pack.rules)}

    violations = [f for f in findings if f.status == "violation"]
    if violations:
        top = min(violations, key=lambda f: (-SEVERITY[pack.rule(f.rule_id).on_violation],
                                             -(f.p_violation or 0.0), order[f.rule_id]))
        rule = pack.rule(top.rule_id)
        return Verdict(rule.on_violation, rule.id, rule.remedy, float(top.p_violation or 1.0), False,
                       tuple(findings))

    uncertain = [f for f in findings if f.status == "uncertain"]
    if uncertain:
        def closeness(f: Finding) -> float:
            p = 0.5 if f.p_violation is None else f.p_violation
            return abs(p - 0.5)

        top = min(uncertain, key=lambda f: (closeness(f), order[f.rule_id]))
        p = 0.5 if top.p_violation is None else top.p_violation
        rule = pack.rule(top.rule_id)
        return Verdict("confirm", rule.id, f"Needs a human look: {rule.text}", 1.0 - 2.0 * min(p, 1.0 - p),
                       True, tuple(findings))

    margins = [1.0 - f.p_violation for f in findings if f.source == "decider" and f.p_violation is not None]
    return Verdict("proceed", None, "", min(margins, default=1.0), False, tuple(findings))
