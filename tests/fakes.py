"""Test doubles for the Decider server and Bedrock."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from bylaw.decider import AskResult, DeciderUnavailable

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
