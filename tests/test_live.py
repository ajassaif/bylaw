"""Live checks: need Bedrock credentials (and, for the Decider test, a running server).

    uv run pytest -m live tests/test_live.py -v
"""

import pytest

from bylaw import config
from bylaw.agent.desk import build_desk
from bylaw.agent.session import Session
from tests.fakes import FakeDecider
from tests.test_gate import make_pack

pytestmark = pytest.mark.live


def test_confirm_interrupts_then_resumes_on_bedrock():
    """A Confirm verdict pauses the Strands agent; an interruptResponse resumes it (strands 1.61.1 shape)."""
    middling = FakeDecider(lambda s, q: {k: {"type": "noul", "noul": 0.95 if k == "no_purpose" else 0.01} for k in q})
    agent = build_desk(make_pack(), middling, Session("maya"), config.AGENT_MODEL)
    result = agent("File a $40 'other' expense dated 2026-10-21 for 'stuff', receipt attached. Do it now.")
    assert result.stop_reason == "interrupt"
    interrupt = result.interrupts[0]
    resumed = agent([{"interruptResponse": {"interruptId": interrupt.id, "response": "yes"}}])
    assert resumed.stop_reason != "interrupt"
