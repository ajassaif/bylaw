"""Score Bylaw, Bylaw + escalation, and Bedrock models deciding alone, on the same cases.

Every system sees the same rendered state. Abstains (a model that never produced usable JSON)
count as wrong and are reported, never dropped. Every number lands in summary.json, and the
README, article and UI read from that file.
"""

from __future__ import annotations

import json
from pathlib import Path

from bylaw.cases import Case, question_label
from bylaw.decide import violation_probability
from bylaw.engine import evaluate_call
from bylaw.judge import LLMJudge
from bylaw.llm import JsonLLM
from bylaw.metrics import (accuracy, bootstrap_ci, brier_binary, ece, false_proceed_rate, latency_pcts, macro_f1,
                           risk_coverage)
from bylaw.pack import Pack, pack_hash
from bylaw.state import render_state

Prices = dict[str, tuple[float, float]]  # model id -> ($ per 1M input tokens, $ per 1M output tokens)


def _usd(prices: Prices, model: str, usage) -> float:
    pin, pout = prices.get(model, (0.0, 0.0))
    return usage.input_tokens / 1e6 * pin + usage.output_tokens / 1e6 * pout


def _row(case: Case, system: str, predicted: str, confidence: float, latency_ms: float, usd: float,
         error: str | None = None, **extra) -> dict:
    return {"case_id": case.id, "system": system, "expected": case.expected, "predicted": predicted,
            "correct": predicted == case.expected, "confidence": confidence, "latency_ms": latency_ms,
            "usd": usd, "error": error, "tags": case.tags, **extra}


def _summarise(rows: list[dict]) -> dict:
    y = [r["expected"] for r in rows]
    p = [r["predicted"] for r in rows]
    correct = [r["correct"] for r in rows]
    n = len(rows)
    manip = [r["correct"] for r in rows if "manipulation" in r["tags"]]
    rc = risk_coverage([r["confidence"] for r in rows], correct)
    step = max(1, len(rc) // 50)
    return {
        "n": n,
        "accuracy": accuracy(y, p),
        "accuracy_ci": bootstrap_ci(lambda idx: sum(correct[i] for i in idx) / len(idx), n),
        "macro_f1": macro_f1(y, p),
        "false_proceed": false_proceed_rate(y, p),
        "false_proceed_ci": bootstrap_ci(lambda idx: false_proceed_rate([y[i] for i in idx], [p[i] for i in idx]), n),
        "ece": ece([r["confidence"] for r in rows], correct),
        "latency": latency_pcts([r["latency_ms"] for r in rows]),
        "usd_per_1k": sum(r["usd"] for r in rows) / n * 1000 if n else 0.0,
        "abstains": sum(r["predicted"] == "abstain" for r in rows),
        "manipulation_n": len(manip),
        "manipulation_accuracy": sum(manip) / len(manip) if manip else None,
        "risk_coverage": rc[::step] + ([rc[-1]] if rc and rc[-1] not in rc[::step] else []),
    }


def run_bench(pack: Pack, policy_text: str, cases: list[Case], decider, llm: JsonLLM, baselines: list[str],
              hybrid_model: str, out_dir: Path, prices: Prices, gpu_usd_per_hour: float, env: dict) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    judges = {m: LLMJudge(llm, m, policy_text) for m in {*baselines, hybrid_model} if m}
    gpu_usd_per_ms = gpu_usd_per_hour / 3_600_000
    rows: list[dict] = []
    escalated = 0
    question_scores: dict[str, list[tuple[float, bool]]] = {}

    for case in cases:
        state = render_state(case.conversation, case.tool, case.args, case.context)
        receipt = evaluate_call(pack, decider, case.tool, case.args, case.context, case.conversation)
        v = receipt.verdict
        decider_usd = (receipt.decider_ms or 0.0) * gpu_usd_per_ms
        rows.append(_row(case, "bylaw", v.action, v.confidence, receipt.total_ms, decider_usd,
                         rule_id=v.rule_id, decider_ms=receipt.decider_ms))
        for q in pack.questions_for(case.tool):
            label, answer = question_label(case, q), receipt.answers.get(q.id)
            if label is not None and answer:
                question_scores.setdefault(q.id, []).append((violation_probability(q, answer), label))

        if not hybrid_model:
            pass
        elif v.uncertain:
            escalated += 1
            out, usage, error = judges[hybrid_model].decide_case(state, case.tool)
            rows.append(_row(case, "bylaw+hybrid", out.action if out else "abstain", out.confidence if out else 0.0,
                             receipt.total_ms + usage.latency_ms, decider_usd + _usd(prices, hybrid_model, usage),
                             error, escalated=True))
        else:
            rows.append(_row(case, "bylaw+hybrid", v.action, v.confidence, receipt.total_ms, decider_usd,
                             escalated=False))

        for model in baselines:
            out, usage, error = judges[model].decide_case(state, case.tool)
            rows.append(_row(case, f"llm:{model}", out.action if out else "abstain", out.confidence if out else 0.0,
                             usage.latency_ms, _usd(prices, model, usage), error,
                             input_tokens=usage.input_tokens, output_tokens=usage.output_tokens))

    systems: dict[str, list[dict]] = {}
    for r in rows:
        systems.setdefault(r["system"], []).append(r)
    summary = {
        "n_cases": len(cases),
        "pack_hash": pack_hash(pack),
        "systems": {name: _summarise(rs) for name, rs in systems.items()},
        "hybrid": {"model": hybrid_model, "coverage": 1 - escalated / len(cases) if cases else 0.0,
                   "escalated": escalated} if hybrid_model else None,
        "decider_question_brier": {qid: {"n": len(s), "brier": brier_binary([p for p, _ in s], [lab for _, lab in s])}
                                   for qid, s in question_scores.items()},
        "prices": {k: list(v) for k, v in prices.items()},
        "gpu_usd_per_hour": gpu_usd_per_hour,
        "env": env,
    }
    (out_dir / "cases.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (out_dir / "report.md").write_text(render_bench_report(summary), encoding="utf-8")
    return summary


def _fmt(x, pct=False, digits=2):
    if x is None:
        return "–"
    return f"{x * 100:.1f}%" if pct else f"{x:.{digits}f}"


def render_bench_report(summary: dict) -> str:
    lines = [f"# Benchmark: {summary['n_cases']} held-out cases, pack `{summary['pack_hash']}`", "",
             "| system | accuracy (95% CI) | false proceed | macro-F1 | ECE | p50 ms | p95 ms | $ / 1k | abstains |",
             "|---|---|---|---|---|---|---|---|---|"]
    for name, s in summary["systems"].items():
        lo, hi = s["accuracy_ci"]
        lines.append(f"| {name} | {_fmt(s['accuracy'], True)} ({_fmt(lo, True)}–{_fmt(hi, True)}) | "
                     f"{_fmt(s['false_proceed'], True)} | {_fmt(s['macro_f1'])} | {_fmt(s['ece'])} | "
                     f"{_fmt(s['latency']['p50'], digits=0)} | {_fmt(s['latency']['p95'], digits=0)} | "
                     f"{_fmt(s['usd_per_1k'], digits=3)} | {s['abstains']} |")
    h = summary["hybrid"]
    if h:
        lines += ["", f"Hybrid: Decider decided {_fmt(h['coverage'], True)} of cases alone and escalated "
                  f"{h['escalated']} to `{h['model']}`.", ""]
    lines += ["", f"Environment: {summary['env']}", ""]
    return "\n".join(lines)
