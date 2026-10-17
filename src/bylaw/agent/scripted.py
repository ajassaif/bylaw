"""A no-LLM stand-in for the travel desk, for previews when Bedrock isn't reachable.

It maps a handful of demo requests to fixed tool calls and runs each one through the real
PolicyGate and the real Decider, so the receipts are genuine; only the conversation is scripted.
The UI labels this mode as scripted.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

from strands.interventions import Confirm, Deny, Guide

from bylaw.agent.session import Session
from bylaw.agent.tools import make_tools
from bylaw.gate import PolicyGate
from bylaw.pack import Pack

SCENARIOS = [
    # (keywords that must all appear, first call, fallback call if the gate sends it back)
    (("south shore",), ("book_hotel", {"hotel_id": "aus-shore", "check_in": "2026-11-03", "nights": 2}),
     ("book_hotel", {"hotel_id": "aus-congress", "check_in": "2026-11-03", "nights": 2})),
    (("lamar",), ("book_hotel", {"hotel_id": "aus-lamar", "check_in": "2026-11-03", "nights": 2,
                                 "reason": "Summit hotels are sold out; Lamar House is the closest option"}), None),
    (("london", "business"), ("book_flight", {"flight_id": "NW480", "cabin": "business",
                                              "justification": "Customer moved the Felixstowe audit up to Oct 28"}),
     ("book_flight", {"flight_id": "NW480", "cabin": "premium_economy",
                      "justification": "Customer moved the Felixstowe audit up to Oct 28"})),
    (("wine",), ("submit_expense", {"category": "meals", "amount_usd": 140, "date": "2026-11-04",
                                    "description": "Team dinner, includes two bottles of wine",
                                    "attendees": "Priya Raman (Northwind), Jordan Wells (Northwind)",
                                    "has_receipt": True}), None),
    (("austin", "flight"), ("book_flight", {"flight_id": "NW212", "cabin": "economy"}), None),
]

HELP = ("This desk is scripted (no language model). It knows these requests: an Austin flight, South Shore "
        "Lofts in Austin, Lamar House in Austin, business class to London, and a team dinner with wine.")


def _result(text: str = "", interrupts: list | None = None) -> SimpleNamespace:
    return SimpleNamespace(stop_reason="interrupt" if interrupts else "end_turn", interrupts=interrupts or [],
                           text=text)


class ScriptedDesk:
    def __init__(self, pack: Pack, decider, session: Session, on_receipt, escalator=None) -> None:
        self.session = session
        self.gate = PolicyGate(pack, decider, context_provider=session.context, escalator=escalator,
                               on_receipt=on_receipt, facts_provider=session.facts_for)
        self.tools = {t.tool_name: t for t in make_tools(session)}
        self.messages: list[dict] = []
        self.pending: dict[str, tuple[str, dict]] = {}

    def _say(self, role: str, text: str) -> None:
        self.messages.append({"role": role, "content": [{"text": text}]})

    def _try(self, tool: str, args: dict) -> tuple[Any, str]:
        event = SimpleNamespace(tool_use={"name": tool, "input": args, "toolUseId": uuid.uuid4().hex},
                                agent=SimpleNamespace(messages=self.messages))
        action = self.gate.before_tool_call(event)
        if isinstance(action, Guide):
            return action, action.feedback
        if isinstance(action, Deny):
            return action, action.reason
        if isinstance(action, Confirm):
            return action, action.prompt
        return action, self.tools[tool](**args)

    def __call__(self, prompt: Any) -> SimpleNamespace:
        if isinstance(prompt, list):
            response = prompt[0]["interruptResponse"]
            tool, args = self.pending.pop(response["interruptId"])
            if response["response"] == "yes":
                return self._reply(f"Signed off. {self.tools[tool](**args)}")
            return self._reply("Not booked: the sign-off was declined.")

        self._say("user", prompt)
        text = prompt.lower()
        for keywords, first, fallback in SCENARIOS:
            if all(k in text for k in keywords):
                break
        else:
            return self._reply(HELP)

        action, said = self._try(*first)
        if isinstance(action, Confirm):
            interrupt_id = uuid.uuid4().hex
            self.pending[interrupt_id] = first
            return _result(interrupts=[SimpleNamespace(id=interrupt_id, name=self.gate.name, reason=said)])
        if isinstance(action, Guide) and fallback is not None:
            again, said2 = self._try(*fallback)
            if isinstance(again, Confirm):
                interrupt_id = uuid.uuid4().hex
                self.pending[interrupt_id] = fallback
                return _result(interrupts=[SimpleNamespace(id=interrupt_id, name=self.gate.name, reason=said2)])
            return self._reply(f"The policy check sent that back: {said} So I tried the nearest option. {said2}")
        if isinstance(action, Guide | Deny):
            return self._reply(f"I couldn't do that. {said}")
        return self._reply(said)

    def _reply(self, text: str) -> SimpleNamespace:
        self._say("assistant", text)
        return _result(text)
