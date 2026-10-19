"""Retuning an existing pack's thresholds on practice cases: never on the test cases."""

from bylaw.cases import Case, build_context
from bylaw.compiler.retune import retune
from bylaw.pack import Pack, Question, Rule, Violation
from tests.fakes import FakeDecider, noul

RULES = [Rule(id="alcohol", text="4.2 No alcohol.", tools=["submit_expense"], on_violation="deny",
              remedy="Alcohol is not reimbursable.")]
Q = Question(id="alcohol_q", rule_id="alcohol", type="noul", instructions="Alcohol?",
             violation=Violation(when_true=True))
PACK = Pack(policy_title="t", policy_sha256="s", compiled_at="now", models={"author": "hand-written"},
            rules=RULES, checks=[], questions=[Q])


def case(i, expected, rule_id, wine):
    return Case(id=f"c{i}", tool="submit_expense",
                args={"amount_usd": 20, "description": "wine" if wine else "taxi"},
                context=build_context("maya", "submit_expense", {}), conversation=[("user", "file it")],
                expected=expected, rule_id=rule_id, source="test")


CASES = ([case(i, "deny", "alcohol_not_reimbursed", True) for i in range(5)]
         + [case(i + 5, "proceed", None, False) for i in range(8)]
         + [case(99, "deny", "something_else", False)])  # says nothing about alcohol: not used
RULE_MAP = {"alcohol_not_reimbursed": ["alcohol"]}


def script(state, questions):
    wine = '"description": "wine"' in state
    return {k: noul(0.62 if wine else 0.31) for k in questions}


def test_thresholds_move_to_fit_the_practice_cases():
    tuned, report = retune(PACK, CASES, FakeDecider(script), RULE_MAP)
    q = tuned.questions[0]
    assert q.hi <= 0.62 and q.lo >= 0.31          # both answers now land outside the "ask a person" band
    assert q.dev is not None and q.dev.n == 13     # 5 breaches + 8 clean; the unrelated breach is skipped
    assert report["alcohol_q"]["changed"] is True


def test_too_few_examples_keep_the_defaults():
    tuned, report = retune(PACK, CASES[:2] + CASES[5:7], FakeDecider(script), RULE_MAP)
    assert (tuned.questions[0].lo, tuned.questions[0].hi) == (0.2, 0.8)
    assert report["alcohol_q"]["changed"] is False


def test_one_decider_request_per_case_and_the_pack_records_how_it_was_tuned():
    fake = FakeDecider(script)
    tuned, _ = retune(PACK, CASES, fake, RULE_MAP)
    assert len(fake.calls) == len(CASES)
    assert tuned.models["thresholds"].startswith("retuned on 14 practice cases")
