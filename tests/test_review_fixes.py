"""Regression tests for the whole-branch review: the gate fails closed on every error, never on a pass."""

import httpx
import pytest
from strands.interventions import Confirm, Deny, Guide

from bylaw import expr
from bylaw.args import normalize_args
from bylaw.decider import DeciderClient, DeciderUnavailable
from bylaw.engine import evaluate_call
from bylaw.gate import PolicyGate
from bylaw.pack import Check, Pack, Rule
from tests.fakes import FakeDecider
from tests.test_gate import CTX, event, make_pack

SCHEMAS = {
    "book_hotel": {"properties": {"nightly_rate": {"type": "number"}}},
    "submit_expense": {"properties": {"amount_usd": {"type": "number"}, "has_receipt": {"type": "boolean"}}},
}


# I1: the gate must read arguments the way the tool will.

def test_nan_is_not_a_number_a_check_can_clear():
    assert expr.evaluate("num(args.x) > 75", {"args": {"x": "NaN"}}) is None
    assert expr.evaluate("num(args.x) > 75", {"args": {"x": float("inf")}}) is None


def test_normalize_args_coerces_like_the_tool_and_drops_what_it_cannot_read():
    out = normalize_args({"amount_usd": "80", "has_receipt": "false"}, SCHEMAS["submit_expense"])
    assert out == {"amount_usd": 80.0, "has_receipt": False}
    assert normalize_args({"amount_usd": "NaN", "has_receipt": "maybe"}, SCHEMAS["submit_expense"]) == {}
    assert normalize_args({"note": "kept"}, None) == {"note": "kept"}


def test_gate_checks_the_coerced_arguments():
    gate = PolicyGate(make_pack(), FakeDecider.constant(0.0), context_provider=lambda: CTX, schemas=SCHEMAS)
    assert isinstance(gate.before_tool_call(event("book_hotel", {"nightly_rate": "300"})), Guide)
    assert isinstance(gate.before_tool_call(event("book_hotel", {"nightly_rate": "NaN"})), Confirm)


# I2: any error inside the gate becomes a sign-off, never a crash and never a pass.

def test_bad_function_arity_is_rejected_when_the_pack_loads():
    for bad in ("present()", "or_else(args.x)", "num()", "days_between(args.a)", "count_where(args.x)"):
        with pytest.raises(expr.ExprError):
            expr.validate(bad)
    pack = make_pack().model_dump()
    pack["checks"].append({"id": "c", "rule_id": "hotel_cap", "expr": "num()", "description": "d"})
    with pytest.raises(ValueError):
        Pack(**pack)


def test_sequence_repetition_and_deep_nesting_are_unknown_or_rejected():
    assert expr.evaluate("args.s * 100000000000 == 'x'", {"args": {"s": "ab"}}) is None
    with pytest.raises(expr.ExprError):
        expr.validate("not " * 3000 + "args.x")


def test_unexpected_error_in_evaluation_fails_closed():
    class Exploding:
        def ask(self, state, questions):
            raise RuntimeError("boom")

    gate = PolicyGate(make_pack(), Exploding(), context_provider=lambda: CTX)
    action = gate.before_tool_call(event("submit_expense", {"amount_usd": 40}))
    assert isinstance(action, Confirm)
    assert "boom" in gate.receipts[-1].error


def test_escalator_error_falls_back_to_a_person():
    class Throttled:
        def judge(self, state, tool):
            raise RuntimeError("ThrottlingException")

    receipt = evaluate_call(make_pack(), FakeDecider.constant(0.5), "submit_expense", {"amount_usd": 40},
                            CTX, [], Throttled())
    assert receipt.effective.action == "confirm"
    assert "ThrottlingException" in (receipt.error or "")


def test_non_json_200_from_decider_is_unavailable():
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text="<html>proxy</html>"))
    with pytest.raises(DeciderUnavailable):
        DeciderClient(transport=transport).ask("state", {"q": {"type": "noul"}})


# I5: when the Decider is down, what the code checks already found still decides.

def test_decider_down_keeps_a_code_breach():
    pack = make_pack()
    pack = Pack(**{**pack.model_dump(), "rules": [*pack.model_dump()["rules"],
                   Rule(id="limit", text="Claims over $1,000 are refused.", tools=["submit_expense"],
                        on_violation="deny", remedy="Split nothing; file it with finance.").model_dump()],
                   "checks": [*pack.model_dump()["checks"],
                              Check(id="big", rule_id="limit", expr="args.amount_usd > 1000",
                                    description="over $1,000").model_dump()]})
    gate = PolicyGate(pack, FakeDecider.down(), context_provider=lambda: CTX)
    action = gate.before_tool_call(event("submit_expense", {"amount_usd": 5000}))
    assert isinstance(action, Deny) and action.reason == "Split nothing; file it with finance."
    assert gate.receipts[-1].error


def test_decider_down_without_a_code_breach_still_asks_a_person():
    gate = PolicyGate(make_pack(), FakeDecider.down(), context_provider=lambda: CTX)
    action = gate.before_tool_call(event("submit_expense", {"amount_usd": 40}))
    assert isinstance(action, Confirm) and "policy check is unavailable" in action.prompt
