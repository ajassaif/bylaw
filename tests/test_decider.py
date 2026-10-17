import json
import threading
import time

import httpx
import pytest

from bylaw.decider import DeciderClient, DeciderUnavailable, to_wire
from bylaw.pack import Question, Violation


def q(type_, criteria, violation):
    return Question(id="q", rule_id="r", type=type_, instructions="Ask?", criteria=criteria, violation=violation)


def test_wire_shapes():
    noul = q("noul", {"true": "yes", "false": "no"}, Violation(when_true=True))
    assert to_wire(noul) == {"type": "noul", "instructions": "Ask?", "criteria": {"true": "yes", "false": "no"}}
    bare = q("noul", None, Violation(when_true=True))
    assert to_wire(bare) == {"type": "noul", "instructions": "Ask?"}
    choice = q("choice", {"a": "A", "b": None}, Violation(options=["a"]))
    assert to_wire(choice)["criteria"] == {"a": "A", "b": None}
    score = q("score", ["low", "mid", "high"], Violation(at_or_above=2))
    assert to_wire(score) == {"type": "score", "instructions": "Ask?", "criteria": ["low", "mid", "high"]}
    assert to_wire(noul, instructions="Other?", criteria={"true": "t"})["instructions"] == "Other?"


def answering_transport(requests: list):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append((request.url.path, body))
        answers = {k: {"type": "noul", "noul": 0.9} for k in body["questions"]}
        return httpx.Response(200, json={"model": "m", "answers": answers,
                                         "usage": {"input_tokens": 321, "output_tokens": 0}, "latency_ms": 118.5})
    return httpx.MockTransport(handler)


def test_ask_posts_one_request():
    seen: list = []
    client = DeciderClient(transport=answering_transport(seen))
    questions = {"a": {"type": "noul", "instructions": "A?"}, "b": {"type": "noul", "instructions": "B?"}}
    result = client.ask("the state", questions)
    assert len(seen) == 1
    path, body = seen[0]
    assert path == "/v1/systemone"
    assert body["state"] == "the state" and set(body["questions"]) == {"a", "b"} and "model" in body
    assert result.answers["a"]["noul"] == 0.9
    assert result.latency_ms == 118.5
    assert result.input_tokens == 321


@pytest.mark.parametrize("failure", ["connect", "timeout", "500"])
def test_timeout_and_refused_raise_unavailable(failure):
    def handler(request):
        if failure == "connect":
            raise httpx.ConnectError("refused", request=request)
        if failure == "timeout":
            raise httpx.ReadTimeout("slow", request=request)
        return httpx.Response(500, text="boom")

    client = DeciderClient(transport=httpx.MockTransport(handler))
    with pytest.raises(DeciderUnavailable):
        client.ask("s", {"a": {"type": "noul", "instructions": "A?"}})


def test_lock_serializes():
    active = 0
    overlap = []
    guard = threading.Lock()

    def handler(request):
        nonlocal active
        with guard:
            active += 1
            overlap.append(active)
        time.sleep(0.05)
        with guard:
            active -= 1
        return httpx.Response(200, json={"answers": {}, "usage": {}})

    client = DeciderClient(transport=httpx.MockTransport(handler))
    threads = [threading.Thread(target=client.ask, args=("s", {})) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert max(overlap) == 1
