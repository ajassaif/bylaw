"""The whole compiler: extract, split, author, generate dev cases, tune, report."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime

from bylaw import expr
from bylaw.cases import Case, question_label
from bylaw.compiler.extract import Draft, extract_draft
from bylaw.compiler.generate import generate_cases
from bylaw.compiler.repair import _rows, _score, repair_checks
from bylaw.compiler.report import render_report
from bylaw.compiler.tune import tune
from bylaw.llm import JsonLLM
from bylaw.pack import Check, Pack, Question, Rule


@dataclass
class CompileConfig:
    model_id: str
    case_model_id: str
    region: str
    per_rule: int = 8
    rounds: int = 2


QUARANTINE_ACCURACY = 0.75
QUARANTINE_MIN_CASES = 5


def quarantine(checks: list[Check], questions: list[Question], rules: list[Rule], cases: list[Case],
               tables: dict) -> tuple[list[Check], list[Question], dict[str, str], list[str]]:
    """Pull any check or question that scored under 75% on at least five practice cases. A pack that
    enforces less but enforces it correctly beats one that refuses every booking."""
    by_rule = {r.id: r for r in rules}
    pulled: dict[str, list[str]] = {}
    warnings: list[str] = []
    kept_checks = []
    for c in checks:
        rows = _rows(c, by_rule[c.rule_id], cases, tables)
        correct, _ = _score(rows)
        if len(rows) >= QUARANTINE_MIN_CASES and correct / len(rows) < QUARANTINE_ACCURACY:
            why = f"check {c.id} was right on {correct} of {len(rows)} practice cases"
            pulled.setdefault(c.rule_id, []).append(why)
            warnings.append(f"quarantined {c.id}: {why}")
        else:
            kept_checks.append(c)
    kept_questions = []
    for q in questions:
        if q.dev and q.dev.n >= QUARANTINE_MIN_CASES and q.dev.accuracy < QUARANTINE_ACCURACY:
            why = f"question {q.id} was right on {q.dev.accuracy:.0%} of {q.dev.n} practice cases"
            pulled.setdefault(q.rule_id, []).append(why)
            warnings.append(f"quarantined {q.id}: {why}")
        else:
            kept_questions.append(q)
    return kept_checks, kept_questions, {k: "; ".join(v) for k, v in pulled.items()}, warnings


def assemble_pack(draft: Draft, questions: list[Question], policy_text: str, cfg: CompileConfig,
                  unenforced: dict[str, str] | None = None) -> Pack:
    return Pack(unenforced=unenforced or {}, policy_title=draft.title, policy_sha256=hashlib.sha256(policy_text.encode()).hexdigest(),
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
    def stage(msg: str) -> None:
        print(f"[compile {datetime.now(UTC):%H:%M:%S}] {msg}", flush=True)

    stage("reading the policy")
    draft = extract_draft(policy_text, llm, cfg.model_id, tools)
    stage(f"{len(draft.rules)} rules, {len(draft.checks)} checks, {len(draft.questions)} questions; writing cases")
    cases, case_warnings = generate_cases(draft, llm, cfg.case_model_id, cfg.per_rule)
    stage(f"{len(cases)} practice cases; tuning questions on the Decider")
    questions, tune_warnings = tune(draft, cases, decider, cfg.rounds, llm, cfg.model_id)
    stage("repairing checks")
    checks, repair_warnings = repair_checks(draft.checks, draft.rules, cases, draft.tables, llm, cfg.model_id)
    stage("quarantining anything that failed its practice cases")
    checks, questions, unenforced, quarantine_warnings = quarantine(checks, questions, draft.rules, cases, draft.tables)
    draft = draft.model_copy(update={"checks": checks})
    pack = assemble_pack(draft, questions, policy_text, cfg, unenforced)
    warnings = [*draft.warnings, *case_warnings, *tune_warnings, *repair_warnings, *quarantine_warnings,
                *check_warnings(pack, cases)]
    return pack, cases, render_report(pack, warnings)
