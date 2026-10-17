from types import SimpleNamespace

from strands.interventions import Confirm, Deny, Guide, Proceed

from bylaw.decide import Verdict
from bylaw.engine import evaluate_call
from bylaw.gate import PolicyGate
from bylaw.pack import Check, Pack, Question, Rule, Violation, pack_hash
from tests.fakes import FakeDecider, noul

CTX = {"today": "2026-10-20", "employee": {"name": "Maya", "level": "IC3"}}


def make_pack() -> Pack:
    return Pack(
        policy_title="t", policy_sha256="s", compiled_at="now", models={},
        rules=[
            Rule(id="hotel_cap", text="Hotels under cap.", tools=["book_hotel"], on_violation="guide",
                 remedy="Pick a hotel under the cap."),
            Rule(id="alcohol", text="No alcohol.", tools=["submit_expense"], on_violation="deny",
                 remedy="Alcohol is not reimbursable."),
            Rule(id="purpose", text="Business purpose.", tools=["submit_expense"], on_violation="confirm",
                 remedy="Needs a manager."),
        ],
        checks=[Check(id="cap", rule_id="hotel_cap", expr="args.nightly_rate > 260", description="over cap")],
        questions=[
            Question(id="is_alcohol", rule_id="alcohol", type="noul", instructions="Alcohol?",
                     violation=Violation(when_true=True)),
            Question(id="no_purpose", rule_id="purpose", type="noul", instructions="No purpose?",
                     violation=Violation(when_true=True)),
            Question(id="personal", rule_id="purpose", type="noul", instructions="Personal?",
                     violation=Violation(when_true=True)),
        ],
    )


def event(name, args, messages=None):
    return SimpleNamespace(tool_use={"name": name, "input": args, "toolUseId": "t1"},
                           agent=SimpleNamespace(messages=messages or [{"role": "user", "content": [{"text": "hi"}]}]))


def gate_with(decider, escalator=None):
    return PolicyGate(make_pack(), decider, context_provider=lambda: CTX, escalator=escalator)


def test_one_decider_request_per_call():
    fake = FakeDecider.constant(0.05)
    receipt = evaluate_call(make_pack(), fake, "submit_expense", {"amount_usd": 40}, CTX, [("user", "lunch")])
    assert len(fake.calls) == 1
    assert set(fake.calls[0][1]) == {"is_alcohol", "no_purpose", "personal"}
    assert receipt.verdict.action == "proceed"


def test_ungated_tool_skips_decider():
    fake = FakeDecider.constant(0.9)
    action = gate_with(fake).before_tool_call(event("search_hotels", {"city": "Austin"}))
    assert isinstance(action, Proceed)
    assert fake.calls == []


def test_guide_then_deny_after_two():
    gate = gate_with(FakeDecider.constant(0.0))
    over_cap = event("book_hotel", {"nightly_rate": 300})
    first, second, third = (gate.before_tool_call(over_cap) for _ in range(3))
    assert isinstance(first, Guide) and first.feedback == "Pick a hotel under the cap."
    assert isinstance(second, Guide)
    assert isinstance(third, Deny) and "asked twice already" in third.reason


def test_decider_down_fails_closed():
    gate = gate_with(FakeDecider.down())
    action = gate.before_tool_call(event("submit_expense", {"amount_usd": 40}))
    assert isinstance(action, Confirm)
    assert "policy check is unavailable" in action.prompt
    assert gate.receipts[-1].error


def test_uncertain_escalates():
    class Escalator:
        def judge(self, state, tool):
            assert "PROPOSED TOOL CALL" in state
            return Verdict("deny", "alcohol", "Judge says no.", 0.9, False, ())

    fake = FakeDecider(lambda s, q: {k: noul(0.5) for k in q})
    gate = gate_with(fake, escalator=Escalator())
    action = gate.before_tool_call(event("submit_expense", {"amount_usd": 40}))
    assert isinstance(action, Deny) and action.reason == "Judge says no."
    assert gate.receipts[-1].escalated
    assert gate.receipts[-1].verdict.uncertain


def test_confirm_maps_to_confirm():
    fake = FakeDecider(lambda s, q: {"is_alcohol": noul(0.01), "no_purpose": noul(0.95), "personal": noul(0.01)})
    action = gate_with(fake).before_tool_call(event("submit_expense", {"amount_usd": 40}))
    assert isinstance(action, Confirm) and action.prompt == "Needs a manager."


def test_receipt_has_hash_and_latency():
    seen = []
    gate = PolicyGate(make_pack(), FakeDecider.constant(0.01, ), context_provider=lambda: CTX, on_receipt=seen.append)
    gate.before_tool_call(event("submit_expense", {"amount_usd": 40}))
    r = seen[0]
    assert r.pack_hash == pack_hash(make_pack())
    assert r.decider_ms == 5.0 and r.total_ms >= 0
    d = r.to_dict()
    assert d["verdict"]["action"] == "proceed" and d["tool"] == "submit_expense"


def test_gate_accepted_by_strands_agent():
    from strands import Agent
    from strands.models import BedrockModel

    Agent(model=BedrockModel(model_id="x", region_name="us-east-1"), interventions=[gate_with(FakeDecider.constant(0))],
          callback_handler=None)


def test_facts_reach_checks_and_state():
    p = make_pack()
    p.checks[0].expr = "ctx.facts.hotel.nightly_rate_usd > 260"
    fake = FakeDecider.constant(0.0)
    gate = PolicyGate(p, fake, context_provider=lambda: CTX,
                      facts_provider=lambda tool, args: {"hotel": {"nightly_rate_usd": 349}})
    action = gate.before_tool_call(event("book_hotel", {"hotel_id": "aus-shore"}))
    assert isinstance(action, Guide)
    assert gate.receipts[-1].verdict.rule_id == "hotel_cap"


def test_question_when_guard_skips_question():
    p = make_pack()
    p.questions[0].when = "args.category == 'meals'"
    fake = FakeDecider.constant(0.99)
    receipt = evaluate_call(p, fake, "submit_expense", {"category": "ground_transport"}, CTX, [])
    assert "is_alcohol" not in fake.calls[0][1]
    assert receipt.verdict.action == "confirm"  # the other two questions still fire at 0.99
    receipt = evaluate_call(p, FakeDecider.constant(0.99), "submit_expense", {"category": "meals"}, CTX, [])
    assert receipt.verdict.action == "deny"
