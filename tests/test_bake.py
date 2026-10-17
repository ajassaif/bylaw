import json

from scripts.bake_sleeping import bake


def test_bake_fills_table_from_summary(tmp_path):
    summary = {"n_cases": 120, "pack_hash": "abc123", "systems": {
        "bylaw": {"accuracy": 0.875, "false_proceed": 0.0, "latency": {"p50": 140.2}, "usd_per_1k": 0.031},
        "llm:us.anthropic.claude-haiku-4-5-20251001-v1:0": {"accuracy": 0.8, "false_proceed": 0.12,
                                                             "latency": {"p50": 2310.0}, "usd_per_1k": 1.9}}}
    path = tmp_path / "summary.json"
    path.write_text(json.dumps(summary))
    html = bake("<p>__NEXT_WINDOW__</p><!--RESULTS-->", path, next_window="Oct 27, 09:00 to 21:00 PT",
                video_url="https://v", repo_url="https://r")
    assert "Oct 27, 09:00 to 21:00 PT" in html and "<!--RESULTS-->" not in html
    assert "120 held-out cases" in html
    assert "<td>Bylaw, Decider alone</td><td>87.5%</td><td>0.0%</td><td>140 ms</td><td>$0.031</td>" in html
    assert "Claude Haiku 4.5 alone" in html
