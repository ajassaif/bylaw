from bylaw.state import conversation_from_messages, render_state

CTX = {"today": "2026-10-20", "employee": {"name": "Maya Lin", "level": "IC3"}}


def test_sections_in_order():
    out = render_state([("user", "Book me a hotel")], "book_hotel", {"hotel_id": "h1"}, CTX)
    a = out.index("--- EMPLOYEE AND TRIP ---")
    b = out.index("--- CONVERSATION ---")
    c = out.index("--- PROPOSED TOOL CALL ---")
    assert a < b < c
    assert "today: 2026-10-20" in out
    assert 'employee: {"level":"IC3","name":"Maya Lin"}' in out
    assert "user: Book me a hotel" in out
    assert "tool: book_hotel" in out


def test_skips_tool_blocks():
    messages = [
        {"role": "user", "content": [{"text": "Find flights to Austin"}]},
        {"role": "assistant", "content": [{"text": "Looking."}, {"toolUse": {"name": "search_flights", "input": {}}}]},
        {"role": "user", "content": [{"toolResult": {"content": [{"text": "F1, F2"}]}}]},
    ]
    assert conversation_from_messages(messages) == [("user", "Find flights to Austin"), ("assistant", "Looking.")]


def test_long_conversation_keeps_call_and_profile():
    turns = [("user" if i % 2 else "assistant", f"turn {i} " + "x" * 500) for i in range(200)]
    args = {"hotel_id": "h-austin-2", "nightly_rate": 289, "nights": 3}
    out = render_state(turns, "book_hotel", args, CTX)
    assert len(out) <= 6000
    assert 'employee: {"level":"IC3","name":"Maya Lin"}' in out
    assert 'arguments: {"hotel_id": "h-austin-2", "nightly_rate": 289, "nights": 3}' in out
    assert "turn 199" in out
    assert "turn 0 " not in out


def test_args_rendered_sorted():
    out = render_state([], "book_flight", {"z": 1, "a": 2}, {})
    assert 'arguments: {"a": 2, "z": 1}' in out
    assert "(no conversation yet)" in out
