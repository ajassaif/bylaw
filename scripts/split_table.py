"""Split benchmark results by where each case's label came from.

The held-out set mixes DeepSeek cases whose labels were kept, DeepSeek cases whose labels were
changed on review, and cases written by the same person who wrote the hand-written pack. This
prints every system's results on each part, so nobody has to trust the pooled number.

    python -m scripts.split_table bench/results/2026-10-17-c7i bench/results/2026-10-17-c7i-handwritten-pack
    python -m scripts.split_table --json bench/results/split.json bench/results/2026-10-17-c7i ...

"Talked into a breach" counts the manipulation cases that should have been stopped and went ahead.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

REVIEWED = Path("data/heldout/reviewed.jsonl")
GROUPS = ("DeepSeek, label kept", "DeepSeek, relabelled", "Written by the pack's author", "All DeepSeek cases")


def origin(case: dict) -> str:
    if not case["id"].startswith("heldout-"):
        return GROUPS[2]
    return GROUPS[0] if case.get("review") == "kept" else GROUPS[1]


def system_name(run: Path, system: str) -> str:
    if system == "bylaw":
        return "Bylaw, hand-written pack" if "handwritten" in run.name else "Bylaw, compiled pack"
    if system == "bylaw+hybrid":
        return "Bylaw, compiled pack, Bedrock when unsure"
    return system.removeprefix("llm:") + " alone"


def tally(runs: list[Path]) -> dict[tuple[str, str], dict[str, int]]:
    origins = {c["id"]: origin(c) for c in map(json.loads, REVIEWED.read_text(encoding="utf-8").splitlines())}
    out: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for run in runs:
        for row in map(json.loads, (run / "cases.jsonl").read_text(encoding="utf-8").splitlines()):
            group = origins[row["case_id"]]
            groups = [group, GROUPS[3]] if group != GROUPS[2] else [group]
            for g in groups:
                t = out[(g, system_name(run, row["system"]))]
                t["n"] += 1
                t["right"] += bool(row["correct"])
                if row["expected"] != "proceed":
                    t["breaches"] += 1
                    t["through"] += row["predicted"] == "proceed"
                else:
                    t["clean"] += 1
                    t["clean_to_person"] += row["predicted"] == "confirm"
                if "manipulation" in (row.get("tags") or []) and row["expected"] != "proceed":
                    t["manip"] += 1
                    t["talked_past"] += row["predicted"] == "proceed"
    return out


def table(runs: list[Path]) -> str:
    data = tally(runs)
    lines = []
    for group in GROUPS:
        rows = sorted((s, t) for (g, s), t in data.items() if g == group)
        if not rows:
            continue
        n = rows[0][1]["n"]
        lines += [f"**{group}** ({n} cases)", "",
                  "| System | Right verdict | Let a breach through | Talked into a breach | Clean cases sent to a person |",
                  "|---|---|---|---|---|"]
        for system, t in rows:
            lines.append(f"| {system} | {t['right'] / t['n']:.0%} | {t['through']} of {t['breaches']} | "
                         f"{t['talked_past']} of {t['manip']} | {t['clean_to_person']} of {t['clean']} |")
        lines.append("")
    return "\n".join(lines)


def as_json(runs: list[Path]) -> dict:
    data = tally(runs)
    return {"groups": [{"name": g, "systems": {s: dict(t) for (gg, s), t in sorted(data.items()) if gg == g}}
                       for g in GROUPS if any(gg == g for gg, _ in data)]}


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "--json":
        out, runs = Path(args[1]), [Path(a) for a in args[2:]]
        out.write_text(json.dumps(as_json(runs), indent=2), encoding="utf-8")
    else:
        print(table([Path(a) for a in args]))
