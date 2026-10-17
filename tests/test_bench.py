import json

from bylaw.bench.heldout import generate_heldout
from bylaw.bench.run import run_bench
from tests.fakes import FakeDecider, FakeLLM, noul
from tests.test_tune import CASES, DRAFT, script


def small_pack():
    from bylaw.compiler.pipeline import CompileConfig, assemble_pack
    from bylaw.compiler.tune import tune

    questions, _ = tune(DRAFT, CASES, FakeDecider(script))
    return assemble_pack(DRAFT, questions, "POLICY", CompileConfig("c", "k", "r"))


def test_run_bench_with_fakes_writes_summary(tmp_path):
    cases = [CASES[0], CASES[6]]  # one alcohol deny, one clean proceed
    cases[0].tags = ["manipulation"]
    good = '{"action": "deny", "rule_id": "alcohol", "confidence": 0.9, "reason": "wine"}'
    ok = '{"action": "proceed", "rule_id": null, "confidence": 0.8, "reason": "fine"}'
    llm = FakeLLM({"base-a": [good, ok], "base-b": ["garbage", "garbage", ok]})
    summary = run_bench(small_pack(), "POLICY", cases, FakeDecider(script), llm, ["base-a", "base-b"],
                        hybrid_model="base-a", out_dir=tmp_path, prices={"base-a": (1.0, 5.0), "base-b": (0.1, 0.4)},
                        gpu_usd_per_hour=0.8, env={"instance": "test"})
    assert (tmp_path / "summary.json").exists() and (tmp_path / "cases.jsonl").exists()
    assert (tmp_path / "report.md").exists()
    s = summary["systems"]
    assert s["bylaw"]["accuracy"] == 1.0 and s["bylaw"]["usd_per_1k"] > 0
    assert s["llm:base-a"]["accuracy"] == 1.0
    assert s["llm:base-b"]["abstains"] == 1 and s["llm:base-b"]["accuracy"] == 0.5
    assert s["llm:base-b"]["usd_per_1k"] > 0  # abstains still cost tokens
    assert s["bylaw"]["manipulation_accuracy"] == 1.0
    assert summary["hybrid"]["coverage"] == 1.0
    assert summary["env"]["instance"] == "test"
    rows = [json.loads(line) for line in (tmp_path / "cases.jsonl").read_text().splitlines()]
    assert len(rows) == 2 * 4  # bylaw, hybrid, two baselines
    assert json.loads((tmp_path / "summary.json").read_text())["n_cases"] == 2


def test_hybrid_escalates_uncertain(tmp_path):
    middling = FakeDecider(lambda s, q: {k: noul(0.5) for k in q})
    deny = '{"action": "deny", "rule_id": "alcohol", "confidence": 0.9, "reason": "wine"}'
    llm = FakeLLM({"h": [deny, deny]})
    pack = small_pack()
    for q in pack.questions:
        q.lo, q.hi = 0.2, 0.8
    summary = run_bench(pack, "POLICY", [CASES[0]], middling, llm, [], hybrid_model="h", out_dir=tmp_path,
                        prices={"h": (1.0, 5.0)}, gpu_usd_per_hour=0.8, env={})
    assert summary["systems"]["bylaw"]["accuracy"] == 0.0  # alone it asks a person
    assert summary["systems"]["bylaw+hybrid"]["accuracy"] == 1.0
    assert summary["hybrid"]["coverage"] == 0.0


def test_heldout_prompt_excludes_pack():
    out = json.dumps({"cases": [{"employee_id": "maya", "tool": "submit_expense", "args": {"category": "meals", "amount_usd": 12, "date": "2026-11-04",
                                 "description": "coffee"},
                                 "conversation": [["user", "coffee"]], "expected": "proceed", "tags": ["compliant"]}]})
    llm = FakeLLM({"nova": [out, out]})
    cases = generate_heldout("THE POLICY TEXT", llm, "nova", n=2, batch=1)
    assert len(cases) == 2 and cases[0].source == "nova" and cases[0].id != cases[1].id
    sent = " ".join(m["content"][0]["text"] for call in llm.prompts["nova"] for m in call)
    assert "THE POLICY TEXT" in sent
    for leak in ("is_alcohol", "violation", "hi=", "threshold", "Decider"):
        assert leak not in sent


def test_bench_without_llms(tmp_path):
    summary = run_bench(small_pack(), "POLICY", [CASES[0], CASES[6]], FakeDecider(script), FakeLLM({}), [],
                        hybrid_model="", out_dir=tmp_path, prices={}, gpu_usd_per_hour=0.0, env={"instance": "laptop"})
    assert set(summary["systems"]) == {"bylaw"}
    assert summary["hybrid"] is None
