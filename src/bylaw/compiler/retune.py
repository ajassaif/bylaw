"""Set an existing pack's question thresholds from practice cases, the way the compiler's tune stage does.

Works on any pack, including a hand-written one, and on practice cases written for a different pack:
`rule_map` says which of the cases' rule ids correspond to which of this pack's rules. Only the
`lo`/`hi` band moves; wording and the decision table stay as they are. The test cases are never
used here, so the benchmark that follows is still a test of something it hasn't seen.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence

from bylaw import expr
from bylaw.cases import Case
from bylaw.compiler.tune import Scored, accuracy, brier, thresholds
from bylaw.decide import violation_probability
from bylaw.decider import to_wire
from bylaw.pack import Pack, Question, QuestionMetrics
from bylaw.state import render_state

MIN_BREACHES = 3   # fewer labelled examples than this and the defaults are a better guess
MIN_CLEAN = 5


def _label(case: Case, q: Question, rule_map: Mapping[str, Sequence[str]]) -> bool | None:
    if case.expected == "proceed":
        return False
    if case.rule_id is not None and q.rule_id in rule_map.get(case.rule_id, [case.rule_id]):
        return True
    return None


def _asked(pack: Pack, case: Case) -> list[Question]:
    env = {"args": case.args, "ctx": case.context, "tables": pack.tables}
    return [q for q in pack.questions_for(case.tool) if q.when is None or expr.evaluate(q.when, env) is not False]


def retune(pack: Pack, cases: list[Case], decider,
           rule_map: Mapping[str, Sequence[str]]) -> tuple[Pack, dict[str, dict]]:
    """One Decider request per case for every question that applies. Returns the new pack and, per
    question, what changed and on how many labelled examples."""
    scored: dict[str, Scored] = defaultdict(list)
    for case in cases:
        asked = _asked(pack, case)
        if not asked:
            continue
        state = render_state(case.conversation, case.tool, case.args, case.context)
        answers = decider.ask(state, {q.id: to_wire(q) for q in asked}).answers
        for q in asked:
            label = _label(case, q, rule_map)
            if label is not None and q.id in answers:
                scored[q.id].append((violation_probability(q, answers[q.id]), label, state))

    questions, report = [], {}
    for q in pack.questions:
        rows = scored.get(q.id, [])
        breaches, clean = sum(lab for _, lab, _ in rows), sum(not lab for _, lab, _ in rows)
        lo, hi = (q.lo, q.hi)
        if breaches >= MIN_BREACHES and clean >= MIN_CLEAN:
            lo, hi = thresholds(rows)
        metrics = QuestionMetrics(n=len(rows), accuracy=accuracy(rows), brier=brier(rows), candidates=1) if rows else q.dev
        questions.append(q.model_copy(update={"lo": lo, "hi": hi, "dev": metrics}))
        report[q.id] = {"breaches": breaches, "clean": clean, "before": [q.lo, q.hi], "after": [lo, hi],
                        "changed": (lo, hi) != (q.lo, q.hi)}

    note = f"retuned on {len(cases)} practice cases (thresholds only)"
    return pack.model_copy(update={"questions": questions, "models": {**pack.models, "thresholds": note}}), report
