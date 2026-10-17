import json

from bylaw.compiler.extract import extract_draft
from tests.fakes import FakeLLM

TOOLS = {"book_hotel": "book_hotel(hotel_id, ...)", "submit_expense": "submit_expense(...)"}


def draft_json(check_expr="ctx.facts.hotel.nightly_rate_usd > tables.hotel_cap[ctx.facts.hotel.city_tier]",
               tools=("book_hotel",), question_type="noul", violation=None):
    return json.dumps({
        "title": "Northwind Travel",
        "rules": [
            {"id": "hotel_cap", "text": "3.1 Nightly caps.", "tools": list(tools), "on_violation": "guide",
             "remedy": "Pick a hotel under the cap."},
            {"id": "alcohol", "text": "4.2 No alcohol.", "tools": ["submit_expense"], "on_violation": "deny",
             "remedy": "Alcohol is not reimbursable."},
        ],
        "checks": [{"id": "hotel_over_cap", "rule_id": "hotel_cap", "expr": check_expr, "description": "over cap"}],
        "questions": [{
            "id": "is_alcohol", "rule_id": "alcohol", "type": question_type,
            "violation": violation or {"when_true": True},
            "wordings": [{"instructions": "Does the expense include alcohol?",
                          "criteria": {"true": "beer, wine, spirits", "false": "no alcohol"}}],
        }],
        "tables": {"hotel_cap": {"A": 260, "B": 190, "C": 140}},
    })


def test_valid_draft_passes_through():
    llm = FakeLLM({"m": [draft_json()]})
    draft = extract_draft("POLICY", llm, "m", TOOLS)
    assert [r.id for r in draft.rules] == ["hotel_cap", "alcohol"]
    assert draft.checks[0].id == "hotel_over_cap"
    assert draft.questions[0].wordings[0].instructions.startswith("Does")
    assert draft.tables["hotel_cap"]["B"] == 190
    assert draft.warnings == []
    assert len(llm.prompts["m"]) == 1
    sent = llm.prompts["m"][0][0]["content"][0]["text"]
    assert "POLICY" in sent and "book_hotel(hotel_id" in sent and "--- PROPOSED TOOL CALL ---" in sent


def test_invalid_expr_repaired():
    llm = FakeLLM({"m": [draft_json(check_expr="__import__('os')"), draft_json()]})
    draft = extract_draft("POLICY", llm, "m", TOOLS)
    assert draft.checks[0].expr.startswith("ctx.facts")
    repair = llm.prompts["m"][1][0]["content"][0]["text"]
    assert "hotel_over_cap" in repair
    assert draft.warnings == []


def test_still_invalid_dropped_with_warning():
    bad = draft_json(check_expr="open('x')")
    llm = FakeLLM({"m": [bad, bad]})
    draft = extract_draft("POLICY", llm, "m", TOOLS)
    assert draft.checks == []
    assert any("hotel_over_cap" in w for w in draft.warnings)
    assert [r.id for r in draft.rules] == ["hotel_cap", "alcohol"]


def test_unknown_tool_rejected():
    bad = draft_json(tools=("teleport",))
    llm = FakeLLM({"m": [bad, bad]})
    draft = extract_draft("POLICY", llm, "m", TOOLS)
    assert "hotel_cap" not in [r.id for r in draft.rules]
    assert draft.checks == []  # its check goes with it
    assert any("teleport" in w for w in draft.warnings)


def test_question_violation_mismatch_dropped():
    bad = draft_json(violation={"options": ["x"]})
    llm = FakeLLM({"m": [bad, bad]})
    draft = extract_draft("POLICY", llm, "m", TOOLS)
    assert draft.questions == []
    assert any("is_alcohol" in w for w in draft.warnings)


def test_rule_with_no_tools_dropped():
    bad = draft_json(tools=())
    llm = FakeLLM({"m": [bad, bad]})
    draft = extract_draft("POLICY", llm, "m", TOOLS)
    assert "hotel_cap" not in [r.id for r in draft.rules]
    assert any("names no tools" in w for w in draft.warnings)
