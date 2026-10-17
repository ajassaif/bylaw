from bylaw.agent.fixtures import EMPLOYEES, TODAY
from bylaw.agent.session import Session
from bylaw.agent.tools import make_tools


def tools_for(session):
    return {t.tool_name: t for t in make_tools(session)}


def test_book_unknown_flight_returns_error():
    s = Session("maya")
    out = tools_for(s)["book_flight"](flight_id="NOPE", cabin="economy")
    assert out.startswith("Error:")
    assert s.ledger == []


def test_booking_updates_ledger_and_context():
    s = Session("maya")
    t = tools_for(s)
    found = t["search_flights"](origin="SEA", dest="AUS", date="2026-11-04")
    assert "NW" in found
    flight_id = found.split("id=")[1].split()[0]
    out = t["book_flight"](flight_id=flight_id, cabin="economy")
    assert out.startswith("Booked")
    assert len(s.ledger) == 1
    ctx = s.context()
    assert ctx["trip"]["bookings"][0]["kind"] == "flight"
    assert ctx["trip"]["total_usd"] == s.ledger[0]["amount_usd"]


def test_fare_mismatch_is_an_error():
    s = Session("maya")
    t = tools_for(s)
    found = t["search_flights"](origin="SEA", dest="AUS", date="2026-11-04")
    flight_id = found.split("id=")[1].split()[0]
    assert t["book_flight"](flight_id=flight_id, cabin="economy", fare_usd=1.0).startswith("Error:")


def test_context_has_today_and_profile():
    ctx = Session("priya").context()
    assert ctx["today"] == TODAY
    assert ctx["employee"]["level"] == EMPLOYEES["priya"]["level"]
    assert ctx["trip"] == {"bookings": [], "total_usd": 0, "approvals_requested": []}


def test_request_approval_is_pending_not_granted():
    s = Session("maya")
    out = tools_for(s)["request_approval"](approver="priya", reason="Business class to Singapore")
    assert "pending" in out.lower()
    assert s.context()["trip"]["approvals_requested"][0]["status"] == "pending"


def test_build_desk_wires_gate_and_tools():
    from bylaw.agent.desk import build_desk
    from tests.fakes import FakeDecider
    from tests.test_gate import make_pack

    agent = build_desk(make_pack(), FakeDecider.constant(0.0), Session("maya"), model_id="x")
    assert set(agent.tool_names) >= {"book_flight", "book_hotel", "submit_expense"}
    assert "Maya Lindgren" in agent.system_prompt


def test_tool_signatures_and_arg_checks():
    from bylaw.agent.tools import TOOL_SCHEMAS, args_problem, signatures

    assert set(TOOL_SCHEMAS["book_hotel"]["required"]) == {"hotel_id", "check_in", "nights"}
    assert args_problem("book_hotel", {"hotel_id": "x", "check_in": "2026-11-03", "nights": 2}) is None
    assert "missing nights" in args_problem("book_hotel", {"hotel_id": "x", "check_in": "2026-11-03"})
    assert "unknown argument price" in args_problem("book_hotel", {"hotel_id": "x", "check_in": "d", "nights": 1,
                                                                   "price": 3})
    assert "unknown tool" in args_problem("teleport", {})
    assert "book_hotel(hotel_id: string, check_in: string, nights: integer, reason?: string)" in signatures()
