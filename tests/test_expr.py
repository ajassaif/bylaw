import pytest

from bylaw.expr import ExprError, evaluate, validate

CAP = {"hotel_cap": {"A": 250}}


def env(args=None, ctx=None, tables=None):
    return {"args": args or {}, "ctx": ctx or {}, "tables": tables or {}}


def test_numeric_check():
    e = env(args={"nightly_rate": 260, "city_tier": "A"}, tables=CAP)
    assert evaluate("args.nightly_rate > tables.hotel_cap[args.city_tier]", e) is True
    e = env(args={"nightly_rate": 240, "city_tier": "A"}, tables=CAP)
    assert evaluate("args.nightly_rate > tables.hotel_cap[args.city_tier]", e) is False


def test_days_between():
    e = env(args={"depart_date": "2026-10-28"}, ctx={"today": "2026-10-20"})
    assert evaluate("days_between(ctx.today, args.depart_date) < 14", e) is True
    e = env(args={"depart_date": "2026-11-20"}, ctx={"today": "2026-10-20"})
    assert evaluate("days_between(ctx.today, args.depart_date) < 14", e) is False


def test_missing_field_is_unknown():
    e = env(args={"city_tier": "A"}, tables=CAP)
    assert evaluate("args.nightly_rate > tables.hotel_cap[args.city_tier]", e) is None


def test_wrong_type_is_unknown():
    e = env(args={"nightly_rate": "$240", "city_tier": "A"}, tables=CAP)
    assert evaluate("args.nightly_rate > tables.hotel_cap[args.city_tier]", e) is None
    assert evaluate("num(args.nightly_rate) > 100", e) is None
    assert evaluate("num(args.x) > 100", env(args={"x": "240"})) is True


@pytest.mark.parametrize("expr", [
    "__import__('os')",
    "args.__class__",
    "(lambda: 1)()",
    "open('x')",
    "[x for x in args]",
    "args.get('x')",
    "args._private",
    "x := 1",
])
def test_rejects_dangerous(expr):
    with pytest.raises(ExprError):
        validate(expr)
    with pytest.raises(ExprError):
        evaluate(expr, env())


def test_boolean_logic():
    expr = "args.cabin == 'business' and not ctx.employee.level in ['VP', 'SVP']"
    assert evaluate(expr, env(args={"cabin": "business"}, ctx={"employee": {"level": "IC3"}})) is True
    assert evaluate(expr, env(args={"cabin": "business"}, ctx={"employee": {"level": "VP"}})) is False
    assert evaluate("lower(args.c) == 'first' or len(args.l) > 2", env(args={"c": "FIRST", "l": []})) is True


def test_three_valued_logic():
    e = env(args={"cabin": "economy"})
    assert evaluate("args.cabin == 'business' and args.missing > 3", e) is False
    assert evaluate("args.cabin == 'economy' or args.missing > 3", e) is True
    assert evaluate("args.cabin == 'economy' and args.missing > 3", e) is None


def test_present_or_else_count_where():
    e = env(args={"justification": "", "reason": "sold out"},
            ctx={"trip": {"approvals_requested": [{"status": "pending"}, {"status": "approved"}]}})
    assert evaluate("present(args.reason)", e) is True
    assert evaluate("present(args.justification)", e) is False
    assert evaluate("present(args.missing)", e) is False
    assert evaluate("or_else(args.missing, 0) + 5 == 5", e) is True
    assert evaluate("count_where(ctx.trip.approvals_requested, 'status', 'approved') == 1", e) is True
    assert evaluate("count_where(args.reason, 'status', 'approved') == 0", e) is None
