"""PolicyGate: a Strands InterventionHandler that runs a compiled pack before every gated tool call.

    gate = PolicyGate(load_pack("packs/northwind.pack.json"), DeciderClient(), context_provider=session.context)
    agent = Agent(model=..., tools=[...], interventions=[gate])

Verdicts map onto Strands' typed actions: proceed -> Proceed, guide -> Guide (the model gets the
remedy and another turn), confirm -> Confirm (a person signs off), deny -> Deny.
"""

from __future__ import annotations

import time
from collections import Counter
from collections.abc import Callable
from typing import Any

from strands.interventions import Confirm, Deny, Guide, InterventionHandler, Proceed

from bylaw.decide import Verdict
from bylaw.decider import DeciderUnavailable
from bylaw.engine import Escalator, Receipt, evaluate_call
from bylaw.pack import Pack, pack_hash
from bylaw.state import conversation_from_messages

UNAVAILABLE = "The policy check is unavailable right now, so a person needs to approve this booking."


class PolicyGate(InterventionHandler):
    name = "bylaw-policy-gate"

    def __init__(self, pack: Pack, decider, context_provider: Callable[[], dict],
                 escalator: Escalator | None = None, on_receipt: Callable[[Receipt], None] | None = None,
                 max_guides_per_rule: int = 2,
                 facts_provider: Callable[[str, dict], dict] | None = None) -> None:
        self.pack = pack
        self.decider = decider
        self.context_provider = context_provider
        self.escalator = escalator
        self.on_receipt = on_receipt
        self.max_guides_per_rule = max_guides_per_rule
        self.facts_provider = facts_provider
        self.receipts: list[Receipt] = []
        self._guides: Counter[str] = Counter()
        self._gated = pack.gated_tools()

    def _record(self, receipt: Receipt) -> None:
        self.receipts.append(receipt)
        if self.on_receipt is not None:
            self.on_receipt(receipt)

    def before_tool_call(self, event: Any, **kwargs: Any):
        tool = event.tool_use["name"]
        if tool not in self._gated:
            return Proceed(reason="not covered by the policy pack")
        args = event.tool_use.get("input") or {}
        conversation = conversation_from_messages(event.agent.messages)
        started = time.perf_counter()
        try:
            context = dict(self.context_provider())
            if self.facts_provider is not None:
                context["facts"] = self.facts_provider(tool, args)
            receipt = evaluate_call(self.pack, self.decider, tool, args, context, conversation, self.escalator)
        except DeciderUnavailable as exc:
            verdict = Verdict("confirm", None, UNAVAILABLE, 0.0, True, ())
            self._record(Receipt(tool=tool, args=args, verdict=verdict, decider_ms=None,
                                 total_ms=(time.perf_counter() - started) * 1000, input_tokens=0,
                                 pack_hash=pack_hash(self.pack), error=str(exc)))
            return Confirm(prompt=UNAVAILABLE)
        self._record(receipt)
        return self._action(receipt.effective)

    def _action(self, verdict: Verdict):
        if verdict.action == "proceed":
            return Proceed(reason=f"cleared at confidence {verdict.confidence:.2f}")
        if verdict.action == "guide":
            key = verdict.rule_id or "?"
            self._guides[key] += 1
            if self._guides[key] > self.max_guides_per_rule:
                return Deny(reason=f"{verdict.message} (asked twice already)")
            return Guide(feedback=verdict.message)
        if verdict.action == "confirm":
            return Confirm(prompt=verdict.message)
        return Deny(reason=verdict.message)
