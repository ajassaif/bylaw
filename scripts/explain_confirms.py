"""Why did the gate ask a person? For every case a pack sends to sign-off, list what was unsure:
a code check that couldn't be decided (a missing field) or a Decider answer inside the lo/hi band.

    python -m scripts.explain_confirms --pack packs/x.pack.json --cases data/heldout/reviewed.jsonl --out explain.jsonl
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from bylaw.cases import load_cases
from bylaw.decider import DeciderClient
from bylaw.engine import evaluate_call
from bylaw.pack import load_pack


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pack", required=True)
    ap.add_argument("--cases", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--decider-url", default="http://127.0.0.1:8099")
    a = ap.parse_args()
    pack, decider = load_pack(a.pack), DeciderClient(a.decider_url, timeout=120)
    rows, why = [], Counter()
    for case in load_cases(a.cases):
        r = evaluate_call(pack, decider, case.tool, case.args, case.context, case.conversation)
        unsure = [{"item": f.item_id, "source": f.source, "p": f.p_violation}
                  for f in r.verdict.findings if f.status == "uncertain"]
        rows.append({"case_id": case.id, "expected": case.expected, "predicted": r.verdict.action, "unsure": unsure})
        if case.expected == "proceed" and r.verdict.action == "confirm":
            why.update(f"{u['source']}:{u['item']}" for u in unsure)
    Path(a.out).write_text("".join(json.dumps(x) + "\n" for x in rows), encoding="utf-8")
    print("clean cases sent to a person, by unsure item:")
    for item, n in why.most_common():
        print(f"  {n:3d}  {item}")


if __name__ == "__main__":
    main()
