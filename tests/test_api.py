import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from bylaw.api.app import create_app
from bylaw.decide import Verdict
from bylaw.engine import Receipt
from bylaw.pack import save_pack
from tests.fakes import FakeDecider
from tests.test_gate import make_pack


class StubAgent:
    def __init__(self, session, on_receipt):
        self.session, self.on_receipt = session, on_receipt

    def __call__(self, prompt):
        if isinstance(prompt, list):
            answer = prompt[0]["interruptResponse"]["response"]
            return SimpleNamespace(stop_reason="end_turn", interrupts=[], __str__=None, text=f"resumed {answer}")
        self.on_receipt(Receipt(tool="book_hotel", args={"hotel_id": "aus-lamar"},
                                verdict=Verdict("confirm", "hotel_cap", "Needs a manager.", 0.9, False, ()),
                                decider_ms=120.0, total_ms=125.0, input_tokens=300, pack_hash="abc"))
        if "approve" in prompt:
            return SimpleNamespace(stop_reason="interrupt", text="",
                                   interrupts=[SimpleNamespace(id="int-1", name="bylaw-policy-gate",
                                                               reason="Needs a manager.")])
        return SimpleNamespace(stop_reason="end_turn", interrupts=[], text="Booked.")


def events(response):
    out = []
    for block in response.text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        out.append((lines["event"], json.loads(lines["data"])))
    return out


@pytest.fixture
def paths(tmp_path):
    pack = tmp_path / "pack.json"
    save_pack(make_pack(), pack)
    policy = tmp_path / "policy.md"
    policy.write_text("# Northwind\n\n1.1 Book through the desk.", encoding="utf-8")
    results = tmp_path / "results"
    results.mkdir()
    return pack, policy, results


def client(paths, passcode="letmein", decider=None, rate=30):
    pack, policy, results = paths
    app = create_app(pack, policy, results, decider or FakeDecider.constant(0.1), StubAgent, passcode=passcode,
                     rate_per_minute=rate, text_of=lambda r: r.text)
    return TestClient(app)


H = {"x-demo-pass": "letmein"}


def test_health_without_pass(paths):
    r = client(paths).get("/api/health")
    assert r.status_code == 200
    assert r.json()["decider"]["status"] == "ok" and len(r.json()["pack_hash"]) == 12
    down = client(paths, decider=FakeDecider.down()).get("/api/health")
    assert down.json()["decider"] == {"status": "down"}


def test_requires_pass(paths):
    c = client(paths)
    assert c.get("/api/policy").status_code == 401
    assert c.get("/api/policy", headers={"x-demo-pass": "wrong"}).status_code == 401
    r = c.get("/api/policy", headers=H)
    assert r.status_code == 200 and r.json()["title"] == "Northwind"
    assert c.get("/api/pack", headers=H).json()["hash"]


def test_rate_limit_429(paths):
    c = client(paths, rate=2)
    sid = c.post("/api/sessions", json={"employee_id": "maya"}, headers=H).json()["session_id"]
    codes = [c.post("/api/chat", json={"session_id": sid, "message": "hi"}, headers=H).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_chat_streams_receipt_then_reply_then_done(paths):
    c = client(paths)
    sid = c.post("/api/sessions", json={"employee_id": "maya"}, headers=H).json()["session_id"]
    r = c.post("/api/chat", json={"session_id": sid, "message": "book Lamar House"}, headers=H)
    assert r.headers["content-type"].startswith("text/event-stream")
    evs = events(r)
    assert [e for e, _ in evs] == ["receipt", "reply", "done"]
    assert evs[0][1]["verdict"]["action"] == "confirm" and evs[0][1]["decider_ms"] == 120.0
    assert evs[1][1]["text"] == "Booked."


def test_approval_round_trip(paths):
    c = client(paths)
    sid = c.post("/api/sessions", json={"employee_id": "maya"}, headers=H).json()["session_id"]
    evs = events(c.post("/api/chat", json={"session_id": sid, "message": "please approve"}, headers=H))
    assert [e for e, _ in evs] == ["receipt", "approval", "done"]
    assert evs[1][1] == {"interrupt_id": "int-1", "prompt": "Needs a manager."}
    evs = events(c.post("/api/approve", json={"session_id": sid, "interrupt_id": "int-1", "approved": True},
                        headers=H))
    assert evs[0] == ("reply", {"text": "resumed yes"})


def test_unknown_session_and_employee(paths):
    c = client(paths)
    assert c.post("/api/sessions", json={"employee_id": "nobody"}, headers=H).status_code == 404
    assert c.post("/api/chat", json={"session_id": "nope", "message": "x"}, headers=H).status_code == 404


def test_bench_404_then_200(paths):
    c = client(paths)
    assert c.get("/api/bench", headers=H).status_code == 404
    _, _, results = paths
    (results / "2026-10-21T0900").mkdir()
    (results / "2026-10-21T0900" / "summary.json").write_text('{"n_cases": 3}')
    (results / "2026-10-22T0900").mkdir()
    (results / "2026-10-22T0900" / "summary.json").write_text('{"n_cases": 9}')
    assert c.get("/api/bench", headers=H).json()["n_cases"] == 9
