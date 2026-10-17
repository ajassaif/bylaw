"""Defaults, each overridable with a BYLAW_* environment variable.

Model IDs are the ones this AWS account (us-east-1) could call on 2026-10-17, checked with a
one-word Converse call each. The dev-case writer and the held-out writer are different model
families on purpose, and the held-out writer is neither a baseline family nor the family the
Decider's torso comes from (Qwen), so no system is graded on cases its own family wrote.
"""

from __future__ import annotations

import os

REGION_PREFIXES = {"us", "eu", "apac", "global", "jp", "au"}


def _env(name: str, default: str) -> str:
    return os.environ.get(f"BYLAW_{name}", default)


def family(model_id: str) -> str:
    """Provider family of a Bedrock model or inference-profile ID."""
    parts = model_id.split(".")
    return parts[1] if parts[0] in REGION_PREFIXES and len(parts) > 2 else parts[0]


REGION = _env("REGION", "us-east-1")
DECIDER_URL = _env("DECIDER_URL", "http://127.0.0.1:8099")
AGENT_MODEL = _env("AGENT_MODEL", "us.anthropic.claude-haiku-4-5-20251001-v1:0")
COMPILER_MODEL = _env("COMPILER_MODEL", "us.anthropic.claude-sonnet-4-6")
CASE_MODEL = _env("CASE_MODEL", COMPILER_MODEL)
HELDOUT_MODEL = _env("HELDOUT_MODEL", "mistral.mistral-large-3-675b-instruct")
HYBRID_MODEL = _env("HYBRID_MODEL", AGENT_MODEL)
BASELINES = _env("BASELINES", ",".join([
    "us.anthropic.claude-haiku-4-5-20251001-v1:0",
    "us.anthropic.claude-sonnet-4-6",
    "us.anthropic.claude-opus-4-6-v1",
    "us.amazon.nova-pro-v1:0",
    "us.amazon.nova-lite-v1:0",
])).split(",")
