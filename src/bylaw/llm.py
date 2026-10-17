"""Structured JSON calls to Bedrock models through the Converse API.

Every model is asked for one JSON object matching a pydantic schema. A reply that does not parse
or validate gets exactly one repair attempt with the error quoted back; a second failure raises
LLMOutputError, which the compiler reports and the benchmark counts as an abstain.
"""

from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0

    def __add__(self, other: Usage) -> Usage:
        return Usage(self.input_tokens + other.input_tokens, self.output_tokens + other.output_tokens,
                     self.latency_ms + other.latency_ms)


class LLMOutputError(RuntimeError):
    def __init__(self, model_id: str, raw_text: str, error: str, usage: Usage | None = None) -> None:
        super().__init__(f"{model_id} gave unusable JSON twice: {error}")
        self.model_id, self.raw_text, self.error = model_id, raw_text, error
        self.usage = usage or Usage()


def parse_json_object(text: str) -> dict:
    """The first ```json fenced block, else the first balanced {...} in the text."""
    if "```" in text:
        for chunk in text.split("```")[1::2]:
            body = chunk.removeprefix("json").strip()
            if body.startswith("{"):
                return json.loads(body)
    start = text.find("{")
    while start != -1:
        depth, in_str, escape = 0, False, False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                escape = ch == "\\" and not escape
                if ch == '"' and not escape:
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        break
        start = text.find("{", start + 1)
    raise ValueError("no JSON object in the reply")


def _user(text: str) -> dict:
    return {"role": "user", "content": [{"text": text}]}


class JsonLLM(ABC):
    """Shared parse-and-repair logic. Subclasses only make the raw call."""

    @abstractmethod
    def _complete(self, model_id: str, system: str, messages: list[dict], max_tokens: int,
                  temperature: float) -> tuple[str, Usage]: ...

    def json(self, model_id: str, system: str, prompt: str, schema: type[T], max_tokens: int = 4000,
             temperature: float = 0.0) -> tuple[T, Usage]:
        ask = (f"{prompt}\n\nReply with one JSON object that matches this JSON schema, and nothing else:\n"
               f"{json.dumps(schema.model_json_schema())}")
        messages = [_user(ask)]
        raw, usage = self._complete(model_id, system, messages, max_tokens, temperature)
        try:
            return schema.model_validate(parse_json_object(raw)), usage
        except (ValueError, ValidationError) as exc:
            error = str(exc)[:800]
        messages = [*messages, {"role": "assistant", "content": [{"text": raw or "(empty)"}]},
                    _user(f"That reply could not be used: {error}\nReply again with only the corrected JSON object.")]
        raw2, usage2 = self._complete(model_id, system, messages, max_tokens, temperature)
        usage = usage + usage2
        try:
            return schema.model_validate(parse_json_object(raw2)), usage
        except (ValueError, ValidationError) as exc:
            raise LLMOutputError(model_id, raw2, str(exc)[:800], usage) from exc


class BedrockLLM(JsonLLM):
    def __init__(self, region: str, client: Any = None) -> None:
        if client is None:
            import boto3
            from botocore.config import Config

            client = boto3.client("bedrock-runtime", region_name=region,
                                  config=Config(read_timeout=180, retries={"max_attempts": 4, "mode": "adaptive"}))
        self.client = client

    def _complete(self, model_id, system, messages, max_tokens, temperature):
        started = time.perf_counter()
        response = self.client.converse(
            modelId=model_id,
            system=[{"text": system}],
            messages=messages,
            inferenceConfig={"maxTokens": max_tokens, "temperature": temperature},
        )
        wall_ms = (time.perf_counter() - started) * 1000
        text = "".join(block.get("text", "") for block in response["output"]["message"]["content"])
        u = response.get("usage", {})
        latency = float(response.get("metrics", {}).get("latencyMs") or wall_ms)
        return text, Usage(int(u.get("inputTokens", 0)), int(u.get("outputTokens", 0)), latency)
