import json

import pytest

from bylaw.cases import Case, build_context, load_cases, question_label, save_cases
from bylaw.compiler.extract import Draft, QuestionDraft, Wording
from bylaw.compiler.pipeline import CompileConfig, compile_policy
from bylaw.compiler.report import render_report
from bylaw.compiler.tune import tune
from bylaw.pack import Check, Rule, Violation, load_pack, save_pack
from tests.fakes import FakeDecider, FakeLLM, noul

RULES = [Rule(id="alcohol", text="4.2 No alcohol.", tools=["submit_expense"], on_violation="deny",
              remedy="Alcohol is not reimbursable."),
         Rule(id="receipt", text="5.1 Receipts.", tools=["submit_expense"], on_violation="guide",
              remedy="Attach a receipt.")]
QD = QuestionDraft(id="is_alcohol", rule_id="alcohol", type="noul", violation=Violation(when_true=True),
                   wordings=[Wording(instructions="SHARP: alcohol?"), Wording(instructions="VAGUE: drinks?")])
DRAFT = Draft(title="T", rules=RULES, questions=[QD],
              checks=[Check(id="no_receipt", rule_id="receipt", expr="args.amount_usd > 25 and not args.has_receipt",
                            description="no receipt")])


def case(i, expected, rule_id, wine):
    return Case(id=f"c{i}", tool="submit_expense",
                args={"amount_usd": 20, "has_receipt": True, "description": "wine" if wine else "taxi"},
                context=build_context("maya", "submit_expense", {}), conversation=[("user", "file it")],
                expected=expected, rule_id=rule_id, tags=["t"], source="test")


CASES = [case(i, "deny", "alcohol", True) for i in range(5)] + [case(i + 5, "proceed", None, False) for i in range(5)]


def script(state, questions):
    wine = '"description": "wine"' in state
    out = {}
    for key in questions:
        sharp = questions[key]["instructions"].startswith("SHARP")
        p = (0.95 if wine else 0.03) if sharp else 0.5  # vague: says nothing either way
        out[key] = noul(p)
    return out


def test_question_label_rules():
    q = QD
    assert question_label(case(0, "deny", "alcohol", True), q) is True
    assert question_label(case(1, "proceed", None, False), q) is False
    assert question_label(case(2, "guide", "receipt", False), q) is None


def test_cases_round_trip(tmp_path):
    path = tmp_path / "c.jsonl"
    save_cases(CASES, path)
    assert load_cases(path) == CASES


def test_build_context_uses_fixtures_and_overrides():
    ctx = build_context("maya", "book_hotel", {"hotel_id": "aus-shore"}, trip={"total_usd": 3100})
    assert ctx["facts"]["hotel"]["nightly_rate_usd"] == 349
    assert ctx["trip"]["total_usd"] == 3100 and ctx["employee"]["level"] == "IC3"
    ctx2 = build_context("maya", "book_hotel", {"hotel_id": "chi-none"}, facts={"hotel": {"nightly_rate_usd": 230}})
    assert ctx2["facts"]["hotel"]["nightly_rate_usd"] == 230


def test_tune_picks_lower_brier_wording():
    questions, warnings = tune(DRAFT, CASES, FakeDecider(script))
    q = questions[0]
    assert q.instructions.startswith("SHARP")
    assert q.dev.accuracy == 1.0 and q.dev.candidates == 2 and q.dev.n == 10
    assert q.dev.brier == pytest.approx((0.05 ** 2 * 5 + 0.03 ** 2 * 5) / 10)


def test_tune_thresholds_from_grid():
    q = tune(DRAFT, CASES, FakeDecider(script))[0][0]
    assert q.hi == 0.5   # smallest grid t where everything >= t is a true violation
    assert q.lo == 0.5   # largest grid t where everything <= t is truly clear


def test_tune_one_request_per_case():
    fake = FakeDecider(script)
    tune(DRAFT, CASES, fake)
    assert len(fake.calls) == len(CASES)
    assert set(fake.calls[0][1]) == {"is_alcohol::0", "is_alcohol::1"}


def test_weak_question_rewritten_then_warned():
    weak = Draft(**{**DRAFT.model_dump(), "questions": [QuestionDraft(**{**QD.model_dump(),
                    "wordings": [{"instructions": "VAGUE: drinks?"}]})]})
    rewrite = json.dumps({"wordings": [{"instructions": "VAGUE: still drinks?"}]})
    llm = FakeLLM({"m": [rewrite, rewrite]})
    questions, warnings = tune(weak, CASES, FakeDecider(script), rounds=2, llm=llm, model_id="m")
    assert len(llm.prompts["m"]) == 2
    assert any("is_alcohol stays weak" in w for w in warnings)
    assert questions[0].dev.candidates == 3


def test_pipeline_end_to_end_with_fakes(tmp_path):
    draft_out = json.dumps({k: v for k, v in json.loads(DRAFT.model_dump_json()).items() if k != "warnings"})
    cases_out = json.dumps({"cases": [
        {"employee_id": "maya", "tool": "submit_expense", "args": {"category": "meals", "amount_usd": 20, "date": "2026-11-04",
         "has_receipt": True, "description": "wine"}, "conversation": [["user", "wine with the team"]], "expected": "deny",
         "rule_id": "alcohol", "tags": ["violating"]},
        {"employee_id": "maya", "tool": "submit_expense", "args": {"category": "meals", "amount_usd": 20, "date": "2026-11-04",
         "has_receipt": True, "description": "taxi"}, "conversation": [["user", "taxi to the airport"]], "expected": "proceed",
         "rule_id": None, "tags": ["compliant"]},
    ]})
    llm = FakeLLM({"compiler": [draft_out], "cases": [cases_out, cases_out]})
    cfg = CompileConfig(model_id="compiler", case_model_id="cases", region="us-east-1", per_rule=2)
    pack, dev_cases, report = compile_policy("POLICY TEXT", llm, FakeDecider(script), cfg, {"submit_expense": "x"})
    assert len(dev_cases) == 4 and dev_cases[0].source == "cases"
    path = tmp_path / "p.json"
    save_pack(pack, path)
    assert load_pack(path) == pack
    assert pack.models == {"compiler": "compiler", "cases": "cases"}
    for rid in ("alcohol", "receipt"):
        assert rid in report


def test_report_mentions_thresholds_and_warnings():
    questions, _ = tune(DRAFT, CASES, FakeDecider(script))
    from bylaw.compiler.pipeline import assemble_pack

    pack = assemble_pack(DRAFT, questions, "POLICY", CompileConfig("a", "b", "r"))
    md = render_report(pack, ["is_alcohol stays weak (acc 0.71)"])
    assert "4.2 No alcohol." in md and "is_alcohol" in md and "stays weak" in md
    assert "args.amount_usd > 25" in md


def test_rewrite_prompt_shows_misclassified_cases():
    weak = Draft(**{**DRAFT.model_dump(), "questions": [QuestionDraft(**{**QD.model_dump(),
                    "wordings": [{"instructions": "VAGUE: drinks?"}]})]})
    llm = FakeLLM({"m": [json.dumps({"wordings": [{"instructions": "SHARP: alcohol?"}]})]})
    questions, warnings = tune(weak, CASES, FakeDecider(script), rounds=2, llm=llm, model_id="m")
    prompt = llm.prompts["m"][0][0]["content"][0]["text"]
    assert "CASES IT GOT WRONG" in prompt and "Should be clear" in prompt and '"description": "taxi"' in prompt
    assert questions[0].instructions.startswith("SHARP") and not warnings


def test_inverted_noul_question_is_flipped():
    inverted = Draft(**{**DRAFT.model_dump(), "questions": [QuestionDraft(**{**QD.model_dump(),
                       "violation": {"when_true": False}, "wordings": [{"instructions": "SHARP: alcohol?"}]})]})
    questions, warnings = tune(inverted, CASES, FakeDecider(script))
    q = questions[0]
    assert q.violation.when_true is True
    assert q.dev.accuracy == 1.0
    assert any("is_alcohol: flipped" in w for w in warnings)


def test_check_repair_round_keeps_a_better_expression():
    from bylaw.compiler.repair import repair_checks
    from bylaw.pack import Check

    broken = Check(id="no_receipt", rule_id="receipt", expr="args.amount > 25 and not args.has_receipt",
                   description="no receipt")
    cases = [case(i, "guide", "receipt", False) for i in range(3)] + [case(9, "proceed", None, False)]
    for c in cases[:3]:
        c.args.update({"amount_usd": 40, "has_receipt": False})
    fixed = '{"expr": "num(args.amount_usd) > 25 and not or_else(args.has_receipt, false)"}'
    llm = FakeLLM({"m": [fixed]})
    checks, warnings = repair_checks([broken], RULES, cases, {}, llm, "m")
    assert checks[0].expr.startswith("num(args.amount_usd)")
    assert any("no_receipt: rewritten" in w for w in warnings)
    prompt = llm.prompts["m"][0][0]["content"][0]["text"]
    assert "args.amount > 25" in prompt and "Should be a breach" in prompt


def test_check_repair_keeps_original_when_rewrite_is_worse():
    from bylaw.compiler.repair import repair_checks
    from bylaw.pack import Check

    good = Check(id="c", rule_id="receipt", expr="args.missing_field > 1", description="d")
    cases = [case(i, "guide", "receipt", False) for i in range(2)]
    llm = FakeLLM({"m": ['{"expr": "args.other_missing > 1"}']})
    checks, warnings = repair_checks([good], RULES, cases, {}, llm, "m")
    assert checks[0].expr == "args.missing_field > 1"
    assert any("c: rewrite did not help" in w for w in warnings)


def test_generated_cases_must_fit_tool_schemas():
    from bylaw.compiler.generate import case_rules, generate_cases

    out = json.dumps({"cases": [
        {"employee_id": "maya", "tool": "submit_expense", "args": {"amount": 20, "category": "meals"},
         "conversation": [["user", "x"]], "expected": "proceed", "tags": ["compliant"]},
        {"employee_id": "maya", "tool": "submit_expense", "args": {"category": "meals", "amount_usd": 20,
         "date": "2026-11-04", "description": "lunch"}, "conversation": [["user", "x"]], "expected": "proceed",
         "tags": ["compliant"]},
    ]})
    llm = FakeLLM({"m": [out, out]})
    cases, warnings = generate_cases(DRAFT, llm, "m", per_rule=2)
    assert len(cases) == 2  # one good case per rule survives
    assert any("unknown argument amount" in w for w in warnings)
    assert "submit_expense(category: string, amount_usd: number" in case_rules()


def test_quarantine_pulls_checks_and_questions_that_fail_practice_cases():
    from bylaw.compiler.pipeline import quarantine
    from bylaw.pack import Check, Question, QuestionMetrics

    always = Check(id="always", rule_id="receipt", expr="true", description="fires on everything")
    good = Check(id="good", rule_id="receipt", expr="num(args.amount_usd) > 25 and not or_else(args.has_receipt, false)",
                 description="d")
    weak_q = Question(id="weak", rule_id="alcohol", type="noul", instructions="?", violation=Violation(when_true=True),
                      dev=QuestionMetrics(n=10, accuracy=0.6, brier=0.3, candidates=2))
    untested = Question(id="untested", rule_id="alcohol", type="noul", instructions="?",
                        violation=Violation(when_true=True))
    clean = [case(i, "proceed", None, False) for i in range(6)]
    checks, questions, unenforced, warnings = quarantine([always, good], [weak_q, untested], RULES, clean, {})
    assert [c.id for c in checks] == ["good"]
    assert [q.id for q in questions] == ["untested"]
    assert unenforced == {"receipt": "check always was right on 0 of 6 practice cases",
                          "alcohol": "question weak was right on 60% of 10 practice cases"}
    assert any("quarantined always" in w for w in warnings)


def test_pack_carries_unenforced_rules(tmp_path):
    from bylaw.compiler.pipeline import assemble_pack

    pack = assemble_pack(DRAFT, [], "POLICY", CompileConfig("a", "b", "r"), unenforced={"alcohol": "why"})
    path = tmp_path / "p.json"
    save_pack(pack, path)
    assert load_pack(path).unenforced == {"alcohol": "why"}
    assert "Not enforced automatically" in render_report(pack, [])
