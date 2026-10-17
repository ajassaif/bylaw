"""A small client for a running `strands-decider serve` process.

One state, many typed questions, one round trip: the server encodes the state once and shares
it across every question, so the gate always asks everything it needs in a single request.
The server handles one request at a time, so calls are serialized with a lock.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import httpx

from bylaw.pack import Question

MODEL_ID = "strands-decider-latest"  # sent for wire completeness; the server answers as its loaded checkpoint
SERVE_HINT = "strands-decider serve StrandsAgents/strands-decider-2B-qwen3.5-v1-2610 --port 8099"


class DeciderUnavailable(RuntimeError):
    """The Decider server did not answer, timed out, or returned an error."""


@dataclass
class AskResult:
    answers: dict[str, dict]
    latency_ms: float
    input_tokens: int


def to_wire(q: Question, instructions: str | None = None, criteria: Any = None) -> dict:
    """The `/v1/systemone` shape for one question. Overrides let the tuner try other wordings."""
    wire: dict[str, Any] = {"type": q.type, "instructions": instructions or q.instructions}
    chosen = criteria if criteria is not None else q.criteria
    if chosen is not None:
        wire["criteria"] = chosen
    return wire


class DeciderClient:
    def __init__(self, url: str = "http://127.0.0.1:8099", timeout: float = 30.0,
                 transport: httpx.BaseTransport | None = None) -> None:
        self.url = url.rstrip("/")
        self._http = httpx.Client(base_url=self.url, timeout=timeout, transport=transport)
        self._lock = threading.Lock()

    def _unavailable(self, exc: Exception | str) -> DeciderUnavailable:
        return DeciderUnavailable(f"no Decider answer from {self.url} ({exc}). Start one with: {SERVE_HINT}")

    def ask(self, state: str, questions: Mapping[str, dict]) -> AskResult:
        body = {"state": state, "model": MODEL_ID, "questions": dict(questions)}
        with self._lock:
            started = time.perf_counter()
            try:
                response = self._http.post("/v1/systemone", json=body)
            except httpx.HTTPError as exc:
                raise self._unavailable(exc) from exc
            wall_ms = (time.perf_counter() - started) * 1000
        if response.status_code != 200:
            raise self._unavailable(f"HTTP {response.status_code}: {response.text[:200]}")
        payload = response.json()
        return AskResult(
            answers=payload.get("answers", {}),
            latency_ms=float(payload.get("latency_ms") or wall_ms),
            input_tokens=int(payload.get("usage", {}).get("input_tokens", 0)),
        )

    def health(self) -> dict:
        try:
            response = self._http.get("/health", timeout=10)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise self._unavailable(exc) from exc
        return response.json()
