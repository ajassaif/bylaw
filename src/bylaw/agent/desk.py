"""Build the Northwind travel desk: a Strands agent on Bedrock whose booking tools are gated."""

from __future__ import annotations

from collections.abc import Callable

from strands import Agent
from strands.models import BedrockModel

from bylaw import config
from bylaw.agent.session import Session
from bylaw.agent.tools import TOOL_SCHEMAS, make_tools
from bylaw.engine import Escalator, Receipt
from bylaw.gate import PolicyGate
from bylaw.pack import Pack

SYSTEM_PROMPT = """You are the travel desk for Northwind Supply Co. You help {name} ({title}) book \
flights and hotels and file expenses.

Book what they ask for. Search before you book, and use the ids the search returns. Keep replies \
short and concrete: what you booked, what it cost, what is still open.

Some actions go through a policy check before they run. If one comes back blocked or sent back, say \
plainly which rule it hit and offer the nearest option that fits. Never claim an approval exists \
unless request_approval returned one, and never work around a check by splitting or relabelling an \
expense. Today is {today}."""


def build_desk(pack: Pack, decider, session: Session, model_id: str = config.AGENT_MODEL,
               escalator: Escalator | None = None, on_receipt: Callable[[Receipt], None] | None = None,
               region: str = config.REGION) -> Agent:
    gate = PolicyGate(pack, decider, context_provider=session.context, escalator=escalator,
                      on_receipt=on_receipt, facts_provider=session.facts_for,
                      schemas=TOOL_SCHEMAS)
    prompt = SYSTEM_PROMPT.format(name=session.employee["name"], title=session.employee["title"],
                                  today=session.today)
    return Agent(model=BedrockModel(model_id=model_id, region_name=region, temperature=0.2),
                 tools=make_tools(session), interventions=[gate], system_prompt=prompt, callback_handler=None)
