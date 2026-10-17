"""Write the README's results table from a benchmark summary, so the README never quotes a number
the benchmark didn't produce.

    uv run python -m scripts.bench_table bench/results/<stamp>/summary.json
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
    rows = ["| System | Right verdict (95% CI) | Let a breach through | Calibration error | p50 | p95 | $ per 1,000 | No answer |",
            "|---|---|---|---|---|---|---|---|"]
    for name, r in s["systems"].items():
        lo, hi = r["accuracy_ci"]
        rows.append(f"| {system_name(name)} | {_pct(r['accuracy'])} ({lo * 100:.1f}–{hi * 100:.1f}%) | "
                    f"{_pct(r['false_proceed'])} | {r['ece']:.3f} | {_ms(r['latency']['p50'])} | "
                    f"{_ms(r['latency']['p95'])} | ${r['usd_per_1k']:.3f} | {r['abstains']} |")
    device = env.get("decider", {}).get("device", "?")
    rows += ["", f"{s['n_cases']} held-out cases, pack `{s['pack_hash']}`. Decider on {device}, "
             f"{env.get('instance', 'unknown machine')}. Full per-case rows are in the same results folder."]
    return "\n".join(rows)


def fill_readme(readme: str, summary_path: Path) -> str:
    s = json.loads(Path(summary_path).read_text(encoding="utf-8"))
    pattern = re.compile(re.escape(START) + r".*?" + re.escape(END), re.S)
    return pattern.sub(lambda _: f"{START}\n{table(s)}\n{END}", readme)


if __name__ == "__main__":
    readme = Path("README.md")
    readme.write_text(fill_readme(readme.read_text(encoding="utf-8"), Path(sys.argv[1])), encoding="utf-8")
