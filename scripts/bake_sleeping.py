"""Fill deploy/sleeping/index.html from a benchmark summary, so the page shown while the GPU box is
off quotes the same numbers as the live bench page.

    uv run python -m scripts.bake_sleeping bench/results/<stamp>/summary.json \
        --next "Oct 27, 09:00 to 21:00 PT" --video https://... --repo https://... --out dist/sleeping/index.html
"""

from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path

NAMES = [(r"claude-(haiku|sonnet|opus)-(\d+)-(\d+)", lambda m: f"Claude {m[1].title()} {m[2]}.{m[3]}"),
         (r"nova-(pro|lite|micro|premier)", lambda m: f"Amazon Nova {m[1].title()}"),
         (r"mistral-large-(\d+)", lambda m: f"Mistral Large {m[1]}")]


def system_name(system: str) -> str:
    if system == "bylaw":
        return "Bylaw, Decider alone"
    if system == "bylaw+hybrid":
        return "Bylaw, Bedrock when unsure"
    model = system.removeprefix("llm:")
    for pattern, name in NAMES:
        if m := re.search(pattern, model):
            return f"{name(m)} alone"
    return f"{model} alone"


def _ms(v) -> str:
    if v is None:
        return "–"
    return f"{v:.0f} ms" if v < 1000 else f"{v / 1000:.1f} s"


def bake(template: str, summary_path: Path, next_window: str, video_url: str, repo_url: str) -> str:
    s = json.loads(Path(summary_path).read_text(encoding="utf-8"))
    rows = "".join(
        f"<tr><td>{html.escape(system_name(name))}</td><td>{r['accuracy'] * 100:.1f}%</td>"
        f"<td>{r['false_proceed'] * 100:.1f}%</td><td>{_ms(r['latency']['p50'])}</td>"
        f"<td>{'$' + format(r['usd_per_1k'], '.3f') if r['usd_per_1k'] else 'not priced'}</td></tr>"
        for name, r in s["systems"].items())
    table = (f"<p>On {s['n_cases']} held-out cases (pack {html.escape(s['pack_hash'])}):</p>"
             "<table><thead><tr><th>System</th><th>Right verdict</th><th>Let a breach through</th>"
             f"<th>Median time</th><th>$ per 1,000</th></tr></thead><tbody>{rows}</tbody></table>")
    return (template.replace("<!--RESULTS-->", table).replace("__NEXT_WINDOW__", html.escape(next_window))
            .replace("__VIDEO_URL__", html.escape(video_url)).replace("__REPO_URL__", html.escape(repo_url)))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("summary", type=Path)
    ap.add_argument("--next", required=True)
    ap.add_argument("--video", required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--out", type=Path, default=Path("dist/sleeping/index.html"))
    a = ap.parse_args()
    template = Path("deploy/sleeping/index.html").read_text(encoding="utf-8")
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(bake(template, a.summary, a.next, a.video, a.repo), encoding="utf-8")
    print(a.out)


if __name__ == "__main__":
    main()
