import pytest

from bylaw.decide import decide, violation_probability
from bylaw.pack import Check, Pack, Question, Rule, Violation

TOOL = "book_hotel"


def rule(rid, on_violation="guide", text=None):
    return Rule(id=rid, text=text or f"Rule {rid}.", tools=[TOOL], on_violation=on_violation, remedy=f"Fix {rid}.")


def noul_q(qid, rid, lo=0.2, hi=0.8, when_true=True):
    return Question(id=qid, rule_id=rid, type="noul", instructions="?", violation=Violation(when_true=when_true),
                    lo=lo, hi=hi)


def pack(rules, questions=(), checks=()):
    return Pack(policy_title="t", policy_sha256="s", compiled_at="now", models={}, rules=list(rules),
                checks=list(checks), questions=list(questions))


def test_violation_probability_each_type():
    assert violation_probability(noul_q("q", "r"), {"noul": 0.7}) == pytest.approx(0.7)
    assert violation_probability(noul_q("q", "r", when_true=False), {"noul": 0.7}) == pytest.approx(0.3)
    choice = Question(id="q", rule_id="r", type="choice", instructions="?", criteria={"a": None, "b": None, "c": None},
                      violation=Violation(options=["b", "c"]))
    assert violation_probability(choice, {"probabilities": {"a": 0.5, "b": 0.3, "c": 0.2}}) == pytest.approx(0.5)
    score = Question(id="q", rule_id="r", type="score", instructions="?", criteria=["lo", "mid", "hi"],
                     violation=Violation(at_or_above=1))
    assert violation_probability(score, {"probabilities": {"0": 0.1, "1": 0.6, "2": 0.3}}) == pytest.approx(0.9)


def test_check_violation_beats_clear_questions():
    p = pack([rule("r1"), rule("r2")], [noul_q("q2", "r2")], [Check(id="c1", rule_id="r1", expr="x", description="d")])
    v = decide(p, TOOL, {"c1": True}, {"q2": {"noul": 0.05}})
    assert (v.action, v.rule_id, v.confidence, v.uncertain) == ("guide", "r1", 1.0, False)
    assert v.message == "Fix r1."


def test_severity_order():
    p = pack([rule("r1", "guide"), rule("r2", "deny")], [noul_q("q1", "r1"), noul_q("q2", "r2")])
    v = decide(p, TOOL, {}, {"q1": {"noul": 0.99}, "q2": {"noul": 0.85}})
    assert (v.action, v.rule_id) == ("deny", "r2")
    assert v.confidence == pytest.approx(0.85)


def test_uncertain_band_goes_to_confirm():
    p = pack([rule("r1", "deny", text="No first class.")], [noul_q("q1", "r1")])
    v = decide(p, TOOL, {}, {"q1": {"noul": 0.5}})
    assert (v.action, v.uncertain, v.rule_id) == ("confirm", True, "r1")
    assert v.message == "Needs a human look: No first class."
    assert v.confidence == pytest.approx(0.0)


def test_unknown_check_is_uncertain():
    p = pack([rule("r1")], checks=[Check(id="c1", rule_id="r1", expr="x", description="d")])
    v = decide(p, TOOL, {"c1": None}, {})
    assert (v.action, v.uncertain) == ("confirm", True)
    assert v.findings[0].status == "uncertain"


def test_all_clear_proceeds_with_min_confidence():
    p = pack([rule("r1"), rule("r2")], [noul_q("q1", "r1"), noul_q("q2", "r2")],
             [Check(id="c1", rule_id="r1", expr="x", description="d")])
    v = decide(p, TOOL, {"c1": False}, {"q1": {"noul": 0.1}, "q2": {"noul": 0.02}})
    assert (v.action, v.rule_id, v.message, v.uncertain) == ("proceed", None, "", False)
    assert v.confidence == pytest.approx(0.9)
    assert pack([rule("r1")]) and decide(pack([rule("r1")]), TOOL, {}, {}).confidence == 1.0


def test_missing_answer_is_uncertain():
    p = pack([rule("r1")], [noul_q("q1", "r1")])
    v = decide(p, TOOL, {}, {})
    assert (v.action, v.uncertain) == ("confirm", True)
