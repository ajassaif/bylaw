"""The whole compiler: extract, split, author, generate dev cases, tune, report."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime

from bylaw import expr
from bylaw.cases import Case, question_label
from bylaw.compiler.extract import Draft, extract_draft
from bylaw.compiler.generate import generate_cases
from bylaw.compiler.report import render_report
from bylaw.compiler.tune import tune
from bylaw.llm import JsonLLM
from bylaw.pack import Pack, Question


@dataclass
class CompileConfig:
    model_id: str
    case_model_id: str
    region: str
    per_rule: int = 8
    rounds: int = 2


def assemble_pack(draft: Draft, questions: list[Question], policy_text: str, cfg: CompileConfig) -> Pack:
    return Pack(policy_title=draft.title, policy_sha256=hashlib.sha256(policy_text.encode()).hexdigest(),
                compiled_at=datetime.now(UTC).isoformat(timespec="seconds"),
                models={"compiler": cfg.model_id, "cases": cfg.case_model_id},
                rules=draft.rules, checks=draft.checks, questions=questions, tables=draft.tables)


def check_warnings(pack: Pack, cases: list[Case]) -> list[str]:
    """Code checks get measured on the dev cases too: a check that is often unknown or wrong is reported."""
    warnings = []
    for c in pack.checks:
        rule = pack.rule(c.rule_id)
        rows = [(expr.evaluate(c.expr, {"args": k.args, "ctx": k.context, "tables": pack.tables}),
                 question_label(k, c)) for k in cases if k.tool in rule.tools]
        rows = [(got, want) for got, want in rows if want is not None]
        if not rows:
            continue
        unknown = sum(got is None for got, _ in rows)
        # a check only has to catch its own breaches; another rule may still catch a case it clears
        missed = sum(got is False and want for got, want in rows)
        false_alarms = sum(got is True and not want for got, want in rows)
        if unknown > len(rows) * 0.2:
            warnings.append(f"check {c.id} could not be evaluated on {unknown} of {len(rows)} dev cases")
        if missed or false_alarms:
            warnings.append(f"check {c.id}: {missed} missed breaches, {false_alarms} false alarms on dev cases")
    return warnings


def compile_policy(policy_text: str, llm: JsonLLM, decider, cfg: CompileConfig,
                   tools: dict[str, str]) -> tuple[Pack, list[Case], str]:
    draft = extract_draft(policy_text, llm, cfg.model_id, tools)
    cases, case_warnings = generate_cases(draft, llm, cfg.case_model_id, cfg.per_rule)
    questions, tune_warnings = tune(draft, cases, decider, cfg.rounds, llm, cfg.model_id)
    pack = assemble_pack(draft, questions, policy_text, cfg)
    warnings = [*draft.warnings, *case_warnings, *tune_warnings, *check_warnings(pack, cases)]
    return pack, cases, render_report(pack, warnings)
