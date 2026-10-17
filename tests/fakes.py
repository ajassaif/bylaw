"""Test doubles for the Decider server and Bedrock."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from bylaw.decider import AskResult, DeciderUnavailable
from bylaw.llm import JsonLLM, Usage

Script = Callable[[str, Mapping[str, dict]], dict[str, dict]]


def noul(p: float) -> dict:
    return {"type": "noul", "noul": p}


class FakeDecider:
    """Same surface as DeciderClient. `script(state, questions)` returns the answers dict."""

    def __init__(self, script: Script, latency_ms: float = 5.0) -> None:
        self.script = script
        self.latency_ms = latency_ms
        self.calls: list[tuple[str, dict]] = []
        self.is_down = False

    @classmethod
    def down(cls) -> FakeDecider:
        fake = cls(lambda s, q: {})
        fake.is_down = True
        return fake

    @classmethod
    def constant(cls, p: float) -> FakeDecider:
        return cls(lambda state, questions: {k: noul(p) for k in questions})

    def ask(self, state: str, questions: Mapping[str, dict]) -> AskResult:
        if self.is_down:
            raise DeciderUnavailable("fake decider is down")
        self.calls.append((state, dict(questions)))
        return AskResult(answers=self.script(state, questions), latency_ms=self.latency_ms,
                         input_tokens=len(state) // 4)

    def health(self) -> dict:
        if self.is_down:
            raise DeciderUnavailable("fake decider is down")
        return {"status": "ok", "checkpoint": "fake", "base_model": "fake", "device": "cpu", "max_length": 4096}


class FakeLLM(JsonLLM):
    """Queued raw replies per model id, sent through the real parse-and-repair path."""

    def __init__(self, responses: dict[str, list[str]]) -> None:
        self.responses = {k: list(v) for k, v in responses.items()}
        self.prompts: dict[str, list[list[dict]]] = {}
        self.systems: dict[str, list[str]] = {}

    def _complete(self, model_id, system, messages, max_tokens, temperature):
        self.prompts.setdefault(model_id, []).append([dict(m) for m in messages])
        self.systems.setdefault(model_id, []).append(system)
        queue = self.responses.get(model_id) or []
        if not queue:
            raise AssertionError(f"FakeLLM has no reply queued for {model_id}")
        return queue.pop(0), Usage(10, 10, 50.0)
