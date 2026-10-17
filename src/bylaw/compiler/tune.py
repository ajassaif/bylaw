"""Stage 5: measure every wording of every question on the dev cases, keep the best, set thresholds,
and send weak questions back to Bedrock for a rewrite.

All wordings for one case go to the Decider in a single request: the state is encoded once and
shared, so trying three phrasings costs about the same as trying one.
"""

from __future__ import annotations

from collections import defaultdict

from pydantic import BaseModel

from bylaw.cases import Case, question_label
from bylaw.compiler.extract import Draft, QuestionDraft, Wording
from bylaw.decide import violation_probability
from bylaw.decider import to_wire
from bylaw.llm import JsonLLM, LLMOutputError
from bylaw.pack import Question, QuestionMetrics
from bylaw.state import render_state

HI_GRID = [round(0.5 + 0.05 * i, 2) for i in range(10)]   # 0.50 .. 0.95
LO_GRID = [round(0.05 + 0.05 * i, 2) for i in range(10)]  # 0.05 .. 0.50
VIOLATION_PRECISION = 0.95
CLEAR_PRECISION = 0.97
WEAK_ACCURACY = 0.8
NL, NL2 = "\n", "\n\n"

Scored = list[tuple[float, bool, str]]  # (p_violation, label, rendered state)


class RewriteOut(BaseModel):
    wordings: list[Wording]


def _tools_by_rule(draft: Draft) -> dict[str, list[str]]:
    return {r.id: r.tools for r in draft.rules}


def _score(qd: QuestionDraft, wordings: list[tuple[int, Wording]], cases: list[Case], decider,
           tools_by_rule: dict[str, list[str]]) -> dict[int, Scored]:
    """One Decider request per relevant case, carrying every given wording of this question."""
    scored: dict[int, Scored] = defaultdict(list)
    for case in cases:
        label = question_label(case, qd)
        if label is None or case.tool not in tools_by_rule[qd.rule_id]:
            continue
        questions = {f"{qd.id}::{i}": to_wire(qd.as_question(0), w.instructions, w.criteria) for i, w in wordings}
        state = render_state(case.conversation, case.tool, case.args, case.context)
        answers = decider.ask(state, questions).answers
        for i, _ in wordings:
            answer = answers.get(f"{qd.id}::{i}")
            if answer:
                scored[i].append((violation_probability(qd.as_question(0), answer), label, state))
    return scored


def _score_all(draft: Draft, cases: list[Case], decider) -> dict[str, dict[int, Scored]]:
    """First pass: every question's every wording, one request per case for all of them together."""
    tools_by_rule = _tools_by_rule(draft)
    result: dict[str, dict[int, Scored]] = {q.id: defaultdict(list) for q in draft.questions}
    for case in cases:
        relevant = [q for q in draft.questions if case.tool in tools_by_rule[q.rule_id]]
        labels = {q.id: question_label(case, q) for q in relevant}
        wire = {f"{q.id}::{i}": to_wire(q.as_question(0), w.instructions, w.criteria)
                for q in relevant if labels[q.id] is not None for i, w in enumerate(q.wordings)}
        if not wire:
            continue
        state = render_state(case.conversation, case.tool, case.args, case.context)
        answers = decider.ask(state, wire).answers
        for q in relevant:
            if labels[q.id] is None:
                continue
            for i in range(len(q.wordings)):
                answer = answers.get(f"{q.id}::{i}")
                if answer:
                    result[q.id][i].append((violation_probability(q.as_question(0), answer), labels[q.id], state))
    return result


def accuracy(scored: Scored) -> float:
    return sum((p >= 0.5) == label for p, label, _ in scored) / len(scored) if scored else 0.0


def brier(scored: Scored) -> float:
    return sum((p - float(label)) ** 2 for p, label, _ in scored) / len(scored) if scored else 1.0


def thresholds(scored: Scored) -> tuple[float, float]:
    hi = 0.95
    for t in HI_GRID:
        above = [label for p, label, _ in scored if p >= t]
        if above and sum(above) / len(above) >= VIOLATION_PRECISION:
            hi = t
            break
    lo = 0.05
    for t in reversed(LO_GRID):
        below = [label for p, label, _ in scored if p <= t]
        if below and sum(not lab for lab in below) / len(below) >= CLEAR_PRECISION:
            lo = t
            break
    return min(lo, hi), hi


def _best(scored: dict[int, Scored]) -> int:
    return min(scored, key=lambda i: (brier(scored[i]), -accuracy(scored[i]), i))


def _rewrite(qd: QuestionDraft, scored: Scored, wording: Wording, llm: JsonLLM, model_id: str) -> list[Wording]:
    wrong = [(p, label, state) for p, label, state in scored if (p >= 0.5) != label][:6]
    examples = NL2.join(f"Should be {'a breach' if label else 'clear'}, the classifier said p={p:.2f}:{NL}{state[-800:]}"
                        for p, label, state in wrong)
    prompt = (f"A yes/no-style classifier question for the rule `{qd.rule_id}` is not separating cases well.{NL}"
              f"Question type: {qd.type}. Violation means: {qd.violation.model_dump(exclude_none=True)}.{NL}"
              f"Current wording: {wording.model_dump_json()}{NL}"
              "Write 2 new wordings. Make each one a single, concrete judgement a reader could answer from "
              "the conversation, the employee profile and the proposed tool call. Describe both sides "
              f"precisely in criteria. Do not ask it to compare numbers.{NL2}CASES IT GOT WRONG{NL}{examples}")
    out, _ = llm.json(model_id, "You sharpen classifier questions.", prompt, RewriteOut, max_tokens=1500)
    return out.wordings[:2]


def tune(draft: Draft, cases: list[Case], decider, rounds: int = 2, llm: JsonLLM | None = None,
         model_id: str | None = None) -> tuple[list[Question], list[str]]:
    tools_by_rule = _tools_by_rule(draft)
    first = _score_all(draft, cases, decider)
    tuned: list[Question] = []
    warnings: list[str] = []
    for qd in draft.questions:
        wordings = list(qd.wordings)
        scored = dict(first[qd.id])
        if not any(scored.values()):
            warnings.append(f"{qd.id} has no labelled dev cases; kept its first wording and default thresholds")
            tuned.append(qd.as_question(0))
            continue
        best = _best(scored)
        for _ in range(rounds if llm is not None and model_id is not None else 0):
            if accuracy(scored[best]) >= WEAK_ACCURACY:
                break
            try:
                fresh = _rewrite(qd, scored[best], wordings[best], llm, model_id)
            except LLMOutputError as exc:
                warnings.append(f"{qd.id}: rewrite failed ({exc.error[:80]})")
                break
            start = len(wordings)
            wordings.extend(fresh)
            scored.update(_score(qd, list(enumerate(wordings))[start:], cases, decider, tools_by_rule))
            best = _best(scored)
        acc = accuracy(scored[best])
        if acc < WEAK_ACCURACY:
            warnings.append(f"{qd.id} stays weak (acc {acc:.2f})")
        lo, hi = thresholds(scored[best])
        w = wordings[best]
        tuned.append(Question(id=qd.id, rule_id=qd.rule_id, type=qd.type, instructions=w.instructions,
                              criteria=w.criteria, violation=qd.violation, lo=lo, hi=hi,
                              dev=QuestionMetrics(n=len(scored[best]), accuracy=round(acc, 4),
                                                  brier=round(brier(scored[best]), 4), candidates=len(wordings))))
    return tuned, warnings
