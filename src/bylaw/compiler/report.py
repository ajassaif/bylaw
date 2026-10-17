"""Stage 6: a plain-language report of what the pack enforces and how well it did on dev cases."""

from __future__ import annotations

from bylaw.pack import Pack, pack_hash

ACTION_WORDS = {"guide": "sends the agent back to fix it", "confirm": "asks a person to sign off",
                "deny": "refuses the action"}


def render_report(pack: Pack, warnings: list[str]) -> str:
    lines = [f"# {pack.policy_title}: compiled policy pack", "",
             f"Pack `{pack_hash(pack)}`, compiled {pack.compiled_at} with "
             + ", ".join(f"{role} `{model}`" for role, model in pack.models.items()) + ".", "",
             f"{len(pack.rules)} rules, {len(pack.checks)} code checks, {len(pack.questions)} Decider questions.", ""]
    for rule in pack.rules:
        lines += [f"## {rule.id}", "", f"> {rule.text}", "",
                  f"Applies to {', '.join(f'`{t}`' for t in rule.tools)}. A breach {ACTION_WORDS[rule.on_violation]}: "
                  f"\"{rule.remedy}\"", ""]
        for c in (c for c in pack.checks if c.rule_id == rule.id):
            lines += [f"- Code check `{c.id}`: {c.description}. Breached when `{c.expr}`."]
        for q in (q for q in pack.questions if q.rule_id == rule.id):
            options = ""
            if isinstance(q.criteria, dict):
                options = "; ".join(f"{k}: {v}" if v else k for k, v in q.criteria.items())
            elif isinstance(q.criteria, list):
                options = " < ".join(q.criteria)
            lines += [f"- Decider question `{q.id}` ({q.type}): {q.instructions}"
                      + (f" Options: {options}." if options else "")]
            lines += [f"  Breach at p ≥ {q.hi:.2f}, clear at p ≤ {q.lo:.2f}, a person decides in between."]
            if q.dev:
                lines += [f"  Dev cases: {q.dev.n}, accuracy {q.dev.accuracy:.2f}, Brier {q.dev.brier:.3f}, "
                          f"best of {q.dev.candidates} wordings."]
        lines.append("")
    lines += ["## Warnings", ""] + ([f"- {w}" for w in warnings] or ["None."]) + [""]
    lines += ["Dev-case numbers tune the pack; they are not the benchmark. See bench/ for held-out results.", ""]
    return "\n".join(lines)
