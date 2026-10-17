"""Needs a running Decider server:  strands-decider serve StrandsAgents/strands-decider-2B-qwen3.5-v1-2610 --port 8099

    uv run --extra decider pytest -m live tests/test_live_decider.py -v
"""

import pytest

from bylaw import config
from bylaw.cases import load_cases
from bylaw.decider import DeciderClient
from bylaw.engine import evaluate_call
from bylaw.pack import load_pack

pytestmark = pytest.mark.live


def test_real_decider_answers_the_handwritten_pack():
    decider = DeciderClient(config.DECIDER_URL, timeout=300)
    health = decider.health()
    assert health["checkpoint"]
    pack = load_pack("packs/northwind.handwritten.pack.json")
    cases = {c.id: c for c in load_cases("data/heldout/handwritten.jsonl")}
    for case_id in ("hw-25", "hw-27"):  # team dinner with wine (deny) vs client dinner with wine (proceed)
        c = cases[case_id]
        receipt = evaluate_call(pack, decider, c.tool, c.args, c.context, c.conversation)
        answer = receipt.answers["alcohol_context"]
        assert 0.0 <= answer["confidence"] <= 1.0 and set(answer["probabilities"]) == {
            "no_alcohol", "with_external_guests", "northwind_only"}
        assert receipt.decider_ms and receipt.decider_ms > 0
        print(case_id, c.expected, receipt.verdict.action, answer["choice"], round(receipt.decider_ms), "ms")
