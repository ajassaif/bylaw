import json

from bylaw.cases import load_cases, save_cases
from scripts.review import merge, show
from tests.test_tune import CASES


def test_merge_applies_relabels_drops_and_appends_handwritten(tmp_path):
    gen, hand = CASES[:3], CASES[5:6]
    review = {"c0": {"expected": "guide", "rule_id": "receipt", "why": "the receipt is the real issue"},
              "c1": "drop: label depends on a fact the case doesn't state"}
    out = merge(gen, hand, review)
    ids = [c.id for c in out]
    assert ids == ["c0", "c2", "c5"]
    c0 = out[0]
    assert (c0.expected, c0.rule_id) == ("guide", "receipt")
    assert c0.review == "relabelled from deny/alcohol: the receipt is the real issue"
    assert out[1].review == "kept"


def test_show_is_compact(tmp_path):
    path = tmp_path / "g.jsonl"
    save_cases(CASES[:1], path)
    text = show(load_cases(path))
    assert text.startswith("c0 | maya | submit_expense")
    assert "-> deny (alcohol)" in text and '"description": "wine"' in text
    assert json.loads(json.dumps(text))  # plain text, no objects


def test_merge_tags_by_prefix():
    gen = [c.model_copy(update={"id": f"heldout-2-6-{i}", "tags": ["x"]}) for i, c in enumerate(CASES[:2])]
    out = merge(gen, [], {"_tags": {"heldout-2-6-": "manipulation"}})
    assert all("manipulation" in c.tags for c in out)
