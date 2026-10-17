"""Defaults, each overridable with a BYLAW_* environment variable.

Model IDs other than the agent's are placeholders until the AWS account's enabled models are
recorded (plan Task 16). The dev-case generator and the held-out generator must be different
model families, so the benchmark never grades a generator's own cases.
"""

from __future__ import annotations

import os


def _env(name: str, default: str) -> str:
    return os.environ.get(f"BYLAW_{name}", default)


REGION = _env("REGION", "us-east-1")
DECIDER_URL = _env("DECIDER_URL", "http://127.0.0.1:8099")
AGENT_MODEL = _env("AGENT_MODEL", "us.anthropic.claude-haiku-4-5-20251001-v1:0")
COMPILER_MODEL = _env("COMPILER_MODEL", "us.anthropic.claude-sonnet-4-5-20250929-v1:0")
CASE_MODEL = _env("CASE_MODEL", COMPILER_MODEL)  # Claude family
HELDOUT_MODEL = _env("HELDOUT_MODEL", "us.amazon.nova-pro-v1:0")  # a different family on purpose
HYBRID_MODEL = _env("HYBRID_MODEL", AGENT_MODEL)
BASELINES = _env("BASELINES", ",".join([AGENT_MODEL, COMPILER_MODEL, "us.amazon.nova-pro-v1:0",
                                         "us.amazon.nova-lite-v1:0"])).split(",")
