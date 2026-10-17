import pytest
from pydantic import ValidationError

from bylaw.pack import Check, Pack, Question, Rule, Violation, load_pack, pack_hash, save_pack


def make_pack(**overrides) -> Pack:
    fields = dict(
        policy_title="Northwind Travel",
        policy_sha256="abc",
        compiled_at="2026-10-17T00:00:00Z",
        models={"compiler": "m"},
        rules=[
            Rule(id="r1", text="Hotels under the cap.", tools=["book_hotel"], on_violation="guide",
                 remedy="Pick a cheaper hotel."),
            Rule(id="r2", text="No alcohol.", tools=["submit_expense"], on_violation="deny", remedy="Remove it."),
        ],
        checks=[Check(id="c1", rule_id="r1", expr="args.nightly_rate > 260", description="over cap")],
        questions=[
            Question(id="q1", rule_id="r2", type="noul", instructions="Is this alcohol?",
                     criteria={"true": "alcohol", "false": "not alcohol"}, violation=Violation(when_true=True)),
        ],
        tables={"hotel_cap": {"A": 260}},
    )
    fields.update(overrides)
    return Pack(**fields)


def test_round_trip(tmp_path):
    pack = make_pack()
    path = tmp_path / "p.json"
    save_pack(pack, path)
    assert load_pack(path) == pack


def test_pack_hash_stable_and_sensitive():
    a, b = make_pack(), make_pack()
    assert pack_hash(a) == pack_hash(b)
    assert len(pack_hash(a)) == 12
    changed = make_pack()
    changed.questions[0].hi = 0.9
    assert pack_hash(changed) != pack_hash(a)


def test_selectors():
    pack = make_pack()
    assert [c.id for c in pack.checks_for("book_hotel")] == ["c1"]
    assert pack.questions_for("book_hotel") == []
    assert [q.id for q in pack.questions_for("submit_expense")] == ["q1"]
    assert pack.questions_for("search_hotels") == []
    assert pack.gated_tools() == {"book_hotel", "submit_expense"}
    assert pack.rule("r2").on_violation == "deny"


def test_violation_must_match_type():
    with pytest.raises(ValidationError):
        Question(id="q", rule_id="r1", type="noul", instructions="x", criteria=None,
                 violation=Violation(options=["x"]))
    with pytest.raises(ValidationError):
        Question(id="q", rule_id="r1", type="choice", instructions="x", criteria={"a": None, "b": None},
                 violation=Violation(at_or_above=1))


def test_question_rule_must_exist():
    with pytest.raises(ValidationError):
        make_pack(questions=[
            Question(id="q9", rule_id="r9", type="noul", instructions="x", criteria=None,
                     violation=Violation(when_true=True)),
        ])


def test_check_tools_narrow_a_multi_tool_rule():
    rule = Rule(id="trip", text="6.1", tools=["book_flight", "book_hotel"], on_violation="confirm", remedy="r")
    pack = make_pack(rules=[rule], questions=[], checks=[
        Check(id="f", rule_id="trip", expr="x", description="d", tools=["book_flight"]),
        Check(id="h", rule_id="trip", expr="x", description="d", tools=["book_hotel"]),
        Check(id="both", rule_id="trip", expr="x", description="d"),
    ])
    assert [c.id for c in pack.checks_for("book_flight")] == ["f", "both"]
    assert [c.id for c in pack.checks_for("book_hotel")] == ["h", "both"]
    with pytest.raises(ValidationError):
        make_pack(rules=[rule], questions=[], checks=[
            Check(id="bad", rule_id="trip", expr="x", description="d", tools=["submit_expense"])])
