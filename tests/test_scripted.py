from bylaw.agent.scripted import ScriptedDesk
from bylaw.agent.session import Session
from bylaw.pack import load_pack
from tests.fakes import FakeDecider, noul

PACK = load_pack("packs/northwind.handwritten.pack.json")
QUESTIONS = {q.id: q for q in PACK.questions}


def all_clear(state, questions):
    """Every question answered the way that means 'no breach'."""
    out = {}
    for key in questions:
        q = QUESTIONS[key]
        if q.type == "choice":
            names = list(q.criteria)
            out[key] = {"type": "choice", "choice": names[0], "confidence": 0.95,
                        "probabilities": {n: (0.97 if i == 0 else 0.03 / (len(names) - 1)) for i, n in enumerate(names)}}
        else:
            out[key] = noul(0.02 if q.violation.when_true else 0.98)
    return out


def desk():
    receipts = []
    d = ScriptedDesk(PACK, FakeDecider(all_clear), Session("maya"), receipts.append)
    return d, receipts


def test_hotel_over_cap_sent_back_then_cheaper_one_cleared():
    d, receipts = desk()
    result = d("Book South Shore Lofts in Austin, two nights from Nov 3")
    assert [r.verdict.action for r in receipts] == ["guide", "proceed"]
    assert "Congress Avenue Suites" in result.text
    assert d.session.ledger[0]["ref"] == "aus-congress"


def test_within_ten_percent_needs_signoff_then_resumes():
    d, receipts = desk()
    result = d("Lamar House please, the summit hotels are sold out")
    assert result.stop_reason == "interrupt" and receipts[-1].verdict.action == "confirm"
    resumed = d([{"interruptResponse": {"interruptId": result.interrupts[0].id, "response": "yes"}}])
    assert "Booked Lamar House" in resumed.text


def test_unknown_request_lists_scenarios():
    d, receipts = desk()
    result = d("hello")
    assert receipts == [] and "scripted" in result.text.lower()
