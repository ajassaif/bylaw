import pytest
from pydantic import BaseModel

from bylaw.judge import LLMJudge
from bylaw.llm import BedrockLLM, LLMOutputError, parse_json_object
from tests.fakes import FakeLLM


class Out(BaseModel):
    answer: str
    n: int


def test_parse_json_fenced_and_bare():
    assert parse_json_object('Sure.\n```json\n{"a": 1}\n```\nDone') == {"a": 1}
    assert parse_json_object('Here: {"a": {"b": "}"}} trailing') == {"a": {"b": "}"}}
    with pytest.raises(ValueError):
        parse_json_object("no json here")


def test_repair_once_then_succeeds():
    llm = FakeLLM({"m": ['{"answer": "x"}', '{"answer": "x", "n": 2}']})
    out, usage = llm.json("m", "sys", "prompt", Out)
    assert out == Out(answer="x", n=2)
    assert usage.input_tokens == 20 and usage.output_tokens == 20
    assert "could not be used" in llm.prompts["m"][-1][-1]["content"][0]["text"]


def test_repair_fails_raises():
    llm = FakeLLM({"m": ["nope", "still nope"]})
    with pytest.raises(LLMOutputError):
        llm.json("m", "sys", "prompt", Out)


def test_judge_abstains_on_garbage():
    judge = LLMJudge(FakeLLM({"j": ["garbage", "garbage"]}), "j", "POLICY TEXT")
    out, usage, error = judge.decide_case("state", "book_hotel")
    assert out is None and error and usage.input_tokens > 0


def test_judge_verdict():
    raw = '{"action": "deny", "rule_id": "alcohol", "confidence": 0.8, "reason": "Wine."}'
    llm = FakeLLM({"j": [raw]})
    judge = LLMJudge(llm, "j", "POLICY TEXT")
    v = judge.judge("state", "submit_expense")
    assert (v.action, v.rule_id, v.confidence, v.uncertain) == ("deny", "alcohol", 0.8, False)
    system, messages = llm.systems["j"][0], llm.prompts["j"][0]
    assert "POLICY TEXT" in system and "state" in messages[0]["content"][0]["text"]


def test_bedrock_request_shape():
    captured = {}

    class Stub:
        def converse(self, **kwargs):
            captured.update(kwargs)
            return {"output": {"message": {"content": [{"text": '{"answer": "y", "n": 1}'}]}},
                    "usage": {"inputTokens": 11, "outputTokens": 3}, "metrics": {"latencyMs": 420}}

    out, usage = BedrockLLM(region="us-east-1", client=Stub()).json("model-x", "sys", "the case", Out)
    assert out.n == 1 and usage.input_tokens == 11 and usage.latency_ms == 420
    assert captured["modelId"] == "model-x"
    assert "the case" in captured["messages"][0]["content"][0]["text"]
    assert captured["inferenceConfig"]["temperature"] == 0
    assert captured["system"] == [{"text": "sys"}]
