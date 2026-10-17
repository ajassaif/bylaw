# The pattern: a compiled policy gate

Declared decision pattern: **policy**. Tags: `#strands-decider-2b` `#policy`.

A policy gate checks a proposed tool call against a written policy before the call runs. Bylaw
splits that check in two:

- **Facts go to code.** Anything that is a comparison of numbers, dates, levels or categories is a
  check: a short expression over the tool's arguments and looked-up facts. A hotel's nightly rate
  against the city cap is arithmetic, and arithmetic shouldn't be guessed.
- **Judgements go to Decider 2B.** Whether a dinner had alcohol on it with only colleagues present,
  whether "my VP said it's fine" is an approval, whether a late booking has a real reason. These
  are typed questions with named options, and Decider answers each with a probability.

A plain decision table then turns the results into one of Strands' four intervention actions.

## One question, as it ships

From `packs/northwind.handwritten.pack.json` (rule 4.2, alcohol):

```json
{
  "id": "alcohol_context",
  "rule_id": "alcohol",
  "type": "choice",
  "instructions": "Does this expense include alcohol, and who was there?",
  "criteria": {
    "no_alcohol": "no wine, beer, spirits or bar tab on the claim",
    "with_external_guests": "alcohol, with a customer or supplier from outside Northwind present",
    "northwind_only": "alcohol, with only Northwind people present or nobody named"
  },
  "violation": {"options": ["northwind_only"]},
  "lo": 0.2,
  "hi": 0.8
}
```

The probability that the rule is broken is the probability mass on the violating options. At or
above `hi` the rule is breached; at or below `lo` it is clear; in between a person decides (or a
Bedrock model, in hybrid mode). The compiler tunes `lo`, `hi` and the wording itself on practice
cases; the hand-written pack uses the defaults.

A question can carry a `when` guard so it is only asked when it applies:

```json
{"id": "late_reason_real", "when": "ctx.facts.days_before_departure < tables.advance_days and present(args.justification)"}
```

## The wiring

```python
from strands import Agent
from bylaw.decider import DeciderClient
from bylaw.gate import PolicyGate
from bylaw.pack import load_pack

gate = PolicyGate(
    load_pack("packs/northwind.pack.json"),
    DeciderClient("http://127.0.0.1:8099"),        # strands-decider serve ... --port 8099
    context_provider=session.context,               # who is asking, what's booked so far
    facts_provider=session.facts_for,               # prices and durations looked up, not taken from the model
)
agent = Agent(model=..., tools=[...], interventions=[gate])
```

`PolicyGate.before_tool_call` does four things for a gated tool:

1. renders one state: employee and trip, the conversation, the proposed call;
2. evaluates the pack's code checks for that tool;
3. asks every Decider question for that tool in **one** request (the state is encoded once and
   shared, so ten questions cost about the same as one);
4. maps the decision table's verdict onto Strands:

| Verdict | Strands action | What the agent sees |
|---|---|---|
| proceed | `Proceed` | the tool runs |
| guide | `Guide(feedback=remedy)` | the call is cancelled with the remedy, and the model takes another turn |
| confirm | `Confirm(prompt=...)` | the agent pauses until a person answers |
| deny | `Deny(reason=remedy)` | the call is cancelled |

Severity is deny > guide > confirm: a breach the agent can fix comes before a sign-off, so nobody
is asked to approve a booking that has to change anyway. The same rule sent back twice in one
session becomes a `Deny`, so a stubborn model can't loop. If the Decider server is down, the gate
returns `Confirm`; it never fails open.

Every call produces a receipt: the verdict, each check and question with its probability, the
Decider's latency, and the pack's hash.

## Using it for your own policy

```bash
uv sync --extra decider
strands-decider serve StrandsAgents/strands-decider-2B-qwen3.5-v1-2610 --port 8099
bylaw compile your-policy.md --out packs/yours.pack.json --dev-out data/dev/yours.jsonl
```

The compiler needs Bedrock access (it reads the policy with Mistral Large 3 and writes practice
cases). Tell it about your tools by editing `TOOL_DESCRIPTIONS` in `src/bylaw/agent/tools.py`,
including which looked-up facts a check may read. Read `packs/yours.pack.md` before you trust the
pack: it lists every rule, how it is enforced, how each question did on practice cases, and what
the compiler dropped or could not make work.

## Limits

- Decider 2B answers well on short, single judgements. It is weaker on anything that needs
  several reasoning steps; split those into separate questions or leave them to a person.
- Practice cases are written by a model. The pack is only as good as those cases, which is why
  the benchmark uses held-out cases from a different model family plus hand-written ones.
- The server is single-request and unauthenticated by design. Keep it on localhost.
