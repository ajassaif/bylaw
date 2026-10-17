"""One repair round for code checks that the practice cases show are wrong or can't be evaluated.

The compiler measures every check on the dev cases. A check that misses breaches, raises false
alarms, or comes back unknown on more than a fifth of the cases it should cover is sent back to
the model with the cases it got wrong. The rewrite is kept only if it scores strictly better.
"""

from __future__ import annotations

import json

from pydantic import BaseModel

from bylaw import expr
from bylaw.cases import Case, question_label
from bylaw.llm import JsonLLM, LLMOutputError
from bylaw.pack import Check, Rule

LANGUAGE = ("names args, ctx, tables; dotted or [\"key\"] access; and/or/not; == != < <= > >= in, not in; "
            "+ - * /; lists; true/false/null; functions days_between(a, b), num(x), len(x), lower(s), "
            "present(x) (false when missing or empty), or_else(x, default), count_where(items, key, value). "
            "Optional arguments may be missing from a call: wrap them in present() or or_else().")


class ExprOut(BaseModel):
    expr: str


def _rows(check: Check, rule: Rule, cases: list[Case], tables: dict) -> list[tuple[Case, bool | None, bool]]:
    rows = []
    for c in cases:
        if c.tool not in rule.tools or (check.tools and c.tool not in check.tools):
            continue
        label = question_label(c, check)
        if label is None:
            continue
        rows.append((c, expr.evaluate(check.expr, {"args": c.args, "ctx": c.context, "tables": tables}), label))
    return rows


def _score(rows) -> tuple[int, int]:
    """(correct, unknown). Unknown never counts as correct."""
    return sum(got is not None and got == label for _, got, label in rows), sum(got is None for _, got, _ in rows)


def _needs_repair(rows) -> bool:
    correct, unknown = _score(rows)
    return bool(rows) and (correct < len(rows) or unknown > 0.2 * len(rows))


def repair_checks(checks: list[Check], rules: list[Rule], cases: list[Case], tables: dict, llm: JsonLLM,
                  model_id: str) -> tuple[list[Check], list[str]]:
    by_rule = {r.id: r for r in rules}
    out: list[Check] = []
    warnings: list[str] = []
    for check in checks:
        rule = by_rule[check.rule_id]
        rows = _rows(check, rule, cases, tables)
        if not _needs_repair(rows):
            out.append(check)
            continue
        wrong = [(c, got, label) for c, got, label in rows if got != label][:6]
        examples = "\n\n".join(
            f"Should be {'a breach' if label else 'clear'}, the check gave {got}:\n"
            f"args {json.dumps(c.args, sort_keys=True)}\nctx.facts {json.dumps(c.context.get('facts', {}))}\n"
            f"ctx.trip {json.dumps(c.context.get('trip', {}))}\nctx.employee.level {c.context['employee']['level']}"
            for c, got, label in wrong)
        prompt = (f"This check enforces: {rule.text}\nIt should be TRUE exactly when the rule is broken.\n"
                  f"Current expression: {check.expr}\nLanguage: {LANGUAGE}\nTables: {json.dumps(tables)}\n\n"
                  f"Cases it got wrong:\n{examples}\n\nWrite a corrected expression.")
        before = _score(rows)
        try:
            fixed, _ = llm.json(model_id, "You fix rule-checking expressions. Be exact.", prompt, ExprOut,
                                max_tokens=800)
            expr.validate(fixed.expr)
        except (LLMOutputError, expr.ExprError) as exc:
            warnings.append(f"{check.id}: rewrite failed ({str(exc)[:80]})")
            out.append(check)
            continue
        candidate = check.model_copy(update={"expr": fixed.expr})
        after = _score(_rows(candidate, rule, cases, tables))
        if after[0] > before[0]:
            warnings.append(f"{check.id}: rewritten ({before[0]}/{len(rows)} -> {after[0]}/{len(rows)} right "
                            f"on dev cases)")
            out.append(candidate)
        else:
            warnings.append(f"{check.id}: rewrite did not help ({before[0]}/{len(rows)} right either way)")
            out.append(check)
    return out, warnings
