"""Write the README's results table from a benchmark summary, so the README never quotes a number
the benchmark didn't produce.

    uv run python -m scripts.bench_table bench/results/<stamp>/summary.json[::Title] [more ...]
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from scripts.bake_sleeping import system_name

START, END = "<!-- bench:start -->", "<!-- bench:end -->"


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def _ms(v) -> str:
    if v is None:
        return "–"
    return f"{v:.0f} ms" if v < 1000 else f"{v / 1000:.1f} s"


def table(s: dict) -> str:
    env = s.get("env", {})
    rows = ["| System | Right verdict (95% CI) | Let a breach through | Right on manipulation cases | "
            "Calibration error | p50 | p95 | $ per 1,000 | No answer |",
            "|---|---|---|---|---|---|---|---|---|"]
    manipulation_n = 0
    for name, r in s["systems"].items():
        lo, hi = r["accuracy_ci"]
        manipulation_n = r.get("manipulation_n", manipulation_n)
        held = _pct(r["manipulation_accuracy"]) if r.get("manipulation_n") else "–"
        rows.append(f"| {system_name(name)} | {_pct(r['accuracy'])} ({lo * 100:.1f}–{hi * 100:.1f}%) | "
                    f"{_pct(r['false_proceed'])} | {held} | {r['ece']:.3f} | {_ms(r['latency']['p50'])} | "
                    f"{_ms(r['latency']['p95'])} | ${r['usd_per_1k']:.3f} | {r['abstains']} |")
    device = env.get("decider", {}).get("device", "?")
    rows += ["", f"{s['n_cases']} benchmark cases ({manipulation_n} of them try to talk the agent past a rule), "
             f"pack `{s['pack_hash']}`. Decider on {device}, {env.get('instance', 'unknown machine')}. "
             "Full per-case rows are in the same results folder."]
    return "\n".join(rows)


def fill_readme(readme: str, *summaries: Path | tuple[Path, str]) -> str:
    """Each summary is a path, or a (path, title) pair; titled tables get a bold heading line."""
    blocks = []
    for item in summaries:
        path, title = item if isinstance(item, tuple) else (item, None)
        s = json.loads(Path(path).read_text(encoding="utf-8"))
        blocks.append((f"**{title}**\n\n" if title else "") + table(s))
    pattern = re.compile(re.escape(START) + r".*?" + re.escape(END), re.S)
    return pattern.sub(lambda _: f"{START}\n" + "\n\n".join(blocks) + f"\n{END}", readme)


def _arg(a: str) -> Path | tuple[Path, str]:
    """`path` or `path::Title`."""
    path, _, title = a.partition("::")
    return (Path(path), title) if title else Path(path)


if __name__ == "__main__":
    readme = Path("README.md")
    readme.write_text(fill_readme(readme.read_text(encoding="utf-8"), *map(_arg, sys.argv[1:])), encoding="utf-8")
