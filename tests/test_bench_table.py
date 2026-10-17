import json

from scripts.bench_table import fill_readme, table


def summary():
    return {"n_cases": 2, "pack_hash": "abc", "env": {"instance": "c7i.4xlarge", "decider": {"device": "cpu"}},
            "systems": {
                "bylaw": {"accuracy": 0.9, "accuracy_ci": [0.8, 0.97], "false_proceed": 0.0, "ece": 0.05,
                          "latency": {"p50": 900.0, "p95": 2100.0}, "usd_per_1k": 0.2, "abstains": 0},
                "llm:us.anthropic.claude-opus-4-6-v1": {"accuracy": 0.85, "accuracy_ci": [0.7, 0.93],
                                                        "false_proceed": 0.1, "ece": 0.12,
                                                        "latency": {"p50": 4100.0, "p95": 9800.0},
                                                        "usd_per_1k": 21.5, "abstains": 1}}}


def test_table_rows_come_from_summary():
    md = table(summary())
    assert "| Bylaw, Decider alone | 90.0% (80.0–97.0%) | 0.0% | 0.050 | 900 ms | 2.1 s | $0.200 | 0 |" in md
    assert "| Claude Opus 4.6 alone | 85.0% (70.0–93.0%) | 10.0% | 0.120 | 4.1 s | 9.8 s | $21.500 | 1 |" in md
    assert "c7i.4xlarge" in md and "cpu" in md


def test_fill_readme_replaces_between_markers(tmp_path):
    p = tmp_path / "summary.json"
    p.write_text(json.dumps(summary()))
    readme = "intro\n<!-- bench:start -->\nold\n<!-- bench:end -->\noutro\n"
    out = fill_readme(readme, p)
    assert "\nold\n" not in out and out.startswith("intro\n<!-- bench:start -->\n") and out.endswith("<!-- bench:end -->\noutro\n")
