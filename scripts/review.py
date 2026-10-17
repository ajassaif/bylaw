"""Hand review of generated held-out cases.

    python -m scripts.review show data/heldout/generated.jsonl > review.txt
    # write data/heldout/review.json: {"case-id": {"expected": ..., "rule_id": ..., "why": ...} | "drop: reason"}
    python -m scripts.review merge data/heldout/generated.jsonl data/heldout/handwritten.jsonl \
        data/heldout/review.json data/heldout/reviewed.jsonl

Cases not named in review.json are kept as labelled (marked "kept"). Every change records why.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from bylaw.cases import Case, load_cases, save_cases


def show(cases: list[Case]) -> str:
    blocks = []
    for c in cases:
        who = c.context.get("employee", {}).get("id", "?")
        trip = c.context.get("trip", {})
        facts = c.context.get("facts", {})
        lines = [f"{c.id} | {who} | {c.tool} {json.dumps(c.args, sort_keys=True)} -> {c.expected} ({c.rule_id}) "
                 f"[{','.join(c.tags)}]",
                 f"   trip total ${trip.get('total_usd', 0)}, approvals {trip.get('approvals_requested', [])}",
                 f"   facts {json.dumps(facts, sort_keys=True)}"]
        lines += [f"   {role}: {text}" for role, text in c.conversation]
        blocks.append("\n".join(lines))
    return "\n".join(blocks)


def merge(generated: list[Case], handwritten: list[Case], review: dict) -> list[Case]:
    out: list[Case] = []
    for c in generated:
        decision = review.get(c.id)
        if isinstance(decision, str) and decision.startswith("drop"):
            continue
        if isinstance(decision, dict):
            before = f"{c.expected}/{c.rule_id}"
            c = c.model_copy(update={"expected": decision["expected"], "rule_id": decision.get("rule_id"),
                                     "review": f"relabelled from {before}: {decision['why']}"})
        else:
            c = c.model_copy(update={"review": "kept"})
        out.append(c)
    return out + list(handwritten)


def main(argv: list[str]) -> None:
    if argv[0] == "show":
        print(show(load_cases(argv[1])))
    elif argv[0] == "merge":
        generated, handwritten, review_path, out = argv[1:5]
        review = json.loads(Path(review_path).read_text(encoding="utf-8"))
        merged = merge(load_cases(generated), load_cases(handwritten), review)
        save_cases(merged, out)
        dropped = sum(1 for v in review.values() if isinstance(v, str))
        print(f"{len(merged)} cases ({len(review) - dropped} relabelled, {dropped} dropped)")


if __name__ == "__main__":
    main(sys.argv[1:])
