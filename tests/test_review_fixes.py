"""Regression tests for the whole-branch review: the gate fails closed on every error, never on a pass."""
from types import SimpleNamespace


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
from tests.test_api import paths  # noqa: F401 - fixture
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


# I3: the proposed call survives however long the profile and arguments get.

def test_state_stays_inside_the_window_and_keeps_the_call():
    from bylaw.state import CALL, render_state
    ledger = [{"id": f"b{i}", "kind": "hotel", "usd": 120, "note": "x" * 80} for i in range(40)]
    context = {"employee": {"name": "Maya"}, "trip": {"bookings": ledger, "total_usd": 4800}}
    state = render_state([("user", "hi"), ("assistant", "hello")], "submit_expense",
                         {"description": "d" * 9000, "amount_usd": 80}, context)
    assert len(state) <= 6000
    assert CALL in state and "submit_expense" in state and '"amount_usd": 80' in state


def test_dropped_turns_are_marked_not_hidden():
    from bylaw.state import render_state
    turns = [("user", "t" * 900)] * 20
    state = render_state(turns, "book_hotel", {"hotel_id": "h"}, {"employee": {"name": "Maya"}})
    assert "(earlier conversation omitted)" in state
    assert "(no conversation yet)" not in state


# I4: a turn that is still running blocks the next one, and turns never share events.

def test_chat_refuses_a_second_turn_while_one_runs(paths):
    import threading

    from bylaw.api.app import create_app
    from fastapi.testclient import TestClient
    release = threading.Event()

    class SlowAgent:
        def __init__(self, session, on_receipt):
            pass

        def __call__(self, prompt):
            release.wait(5)
            return SimpleNamespace(stop_reason="end_turn", interrupts=[], text=f"done {prompt}")

    pack, policy, results = paths
    c = TestClient(create_app(pack, policy, results, FakeDecider.constant(0.1), SlowAgent, passcode="p",
                              text_of=lambda r: r.text))
    h = {"x-demo-pass": "p"}
    sid = c.post("/api/sessions", json={"employee_id": "maya"}, headers=h).json()["session_id"]
    first = threading.Thread(target=lambda: c.post("/api/chat", json={"session_id": sid, "message": "one"}, headers=h))
    first.start()
    import time
    time.sleep(0.3)
    assert c.post("/api/chat", json={"session_id": sid, "message": "two"}, headers=h).status_code == 409
    release.set()
    first.join(5)
    second = c.post("/api/chat", json={"session_id": sid, "message": "three"}, headers=h)
    assert "done three" in second.text and "done one" not in second.text


# C1: the bench page shows the runs the README cites, not whichever folder sorts last.

def test_bench_serves_the_runs_named_in_current_json(paths):
    import json as _json

    from tests.test_api import client
    _, _, results = paths
    for name, n, systems in (("a-compiled", 197, {"bylaw": {}, "llm:nova": {}}),
                             ("b-handwritten", 197, {"bylaw": {}}), ("z-laptop", 45, {"bylaw": {}})):
        (results / name).mkdir()
        (results / name / "summary.json").write_text(_json.dumps({"n_cases": n, "systems": systems, "env": {}}))
    (results / "current.json").write_text(_json.dumps(
        {"runs": [{"dir": "a-compiled"}, {"dir": "b-handwritten", "rename": {"bylaw": "bylaw:handwritten"}}]}))
    (results / "split.json").write_text(_json.dumps({"groups": []}))
    body = client(paths).get("/api/bench", headers={"x-demo-pass": "letmein"}).json()
    assert body["n_cases"] == 197
    assert set(body["systems"]) == {"bylaw", "llm:nova", "bylaw:handwritten"}
    assert body["split"] == {"groups": []}
