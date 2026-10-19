# Bylaw: the policy check your AI agent can't argue with

*AWS Agent Experience Hackathon: Strands Decider. Decision pattern: policy. Tags: #strands-decider-2b #policy*

Demo (1:53, recorded on the live app on AWS): https://youtu.be/SmfgShc2p2c
Code: https://github.com/ajassaif/bylaw

An AI travel agent that can book flights will, sooner or later, book business class because
someone typed "my VP said it's fine". The policy that forbids it already exists. It's a document
written for people, and the agent has no reliable way to be held to it.

The usual fix is a second model call: hand an LLM the policy and the proposed booking and ask
whether it's allowed. I built that as a baseline and measured it. Amazon Nova Pro, given the whole
policy, got 54% of verdicts right on 197 test cases and let 9 of 113 breaches through. Every one of
those 9 was arithmetic: a trip that passed $3,000 without a recorded approval, or a flight booked
inside the 14-day window with no reason. Language models are good at reading a policy and bad at
adding up a trip.

Bylaw splits the job three ways, cheapest first:

1. **Code checks the facts.** Rates against caps, dates against windows, cabin against flight
   length, trip totals against the approval limit. Exact, instant, and free.
2. **Strands Decider 2B answers the judgement calls.** Is "the summit hotels are sold out" a real
   reason? Was anyone from outside the company at that dinner? Decider returns a probability, not a
   paragraph.
3. **Amazon Bedrock is asked only when Decider is unsure.** A probability inside the question's
   uncertain band goes to Nova Pro with the whole policy, instead of to a person.

On the same 197 cases that got **88.8% of verdicts right (95% CI 84.3–93.4%) and let none of the 113
breaches through**, at about half Nova Pro's cost per decision.

## Why Decider fits half a policy

Strands Decider 2B is a 2-billion-parameter model with its text-generation head removed. You give it
a state and a typed question (yes/no, one of N options, or a score) and it returns a probability for
each answer in one forward pass. It doesn't write anything, which is exactly what you want from a
gate: nothing for the agent to negotiate with.

Take clause 3.2 of the (made-up) Northwind policy: you may go up to 10% over the hotel cap if
nothing suitable is available, with your manager's approval. Whether $205 is within 10% of $190 is
arithmetic, so it's code. Whether "the summit hotels are sold out" is a real reason, rather than "I
like the pool", is a judgement, so it's a Decider question with named options and a description of
each side.

## The gate

A policy becomes a pack: one JSON file of rules, code checks and typed questions. At run time the
pack loads into a Strands `InterventionHandler`. Before any booking or expense tool runs, it renders
one state (who's asking, what's booked, the conversation, the proposed call), runs the checks, asks
every relevant Decider question in a single request, and maps the result onto Strands' own actions:

- `Proceed` when everything is clear,
- `Guide` with the clause's remedy when the agent can fix it (pick a cheaper hotel),
- `Confirm` when a person has to sign off, which pauses the agent until they do,
- `Deny` when the policy forbids it.

The decision is a plain table over those results, an `if` statement over probabilities. A few rules
turned out to matter. A breach the agent can fix outranks a sign-off, so nobody approves a booking
that's about to change. The same rule sent back twice becomes a refusal. If Decider is down, the
code checks still decide what they can and a person signs off the rest; the gate never fails open.
Check expressions are parsed against a whitelist, never run as Python, and they read facts from the
inventory rather than numbers the agent typed.

## Writing the pack: a compiler, and an honest first draft

Writing questions by hand doesn't scale, so Bylaw has a compiler. It reads the policy with Mistral
Large 3 on Bedrock and sorts every clause into checks and questions. Then it tests its own questions:
it writes practice cases per rule, sends every wording of every question to Decider in one request
per case, keeps the best-calibrated wording and sets each question's thresholds from what it
measured. Questions that stay weak get rewritten.

It isn't as good as a careful person yet. The compiled pack is right on 44.7% of cases. Two mistakes
explain most of the gap, and both are visible in the report it writes: it marked two fixable rules as
*refuse*, and it pulled the $3,000 trip check for flights after that check failed its practice cases.
Treat a compiled pack like generated code: read the report, fix what it flags, ship it.

## How it did

197 test cases, 50 of them attempts to talk the agent past a rule: verbal approvals that were never
recorded, a team dinner relabelled as client entertainment, an expense description that tells the
reviewer to ignore the policy. Every system saw the same rendered state.

| | Right verdict (95% CI) | Breaches let through | Talked into a breach | Clean trips sent to a person | $ per 1,000 |
|---|---|---|---|---|---|
| Bylaw: code + Decider + Bedrock when unsure | **88.8% (84.3–93.4%)** | **0 of 113** | **0 of 38** | 0 of 84 | $0.83 |
| Bylaw: code + Decider, a person when unsure | 60.4% (53.8–67.0%) | 0 of 113 | 0 of 38 | 63 of 84 | $0.26 |
| Amazon Nova Pro alone | 53.8% (46.7–60.9%) | 9 of 113 | 2 of 38 | 0 of 84 | $1.52 |
| Amazon Nova Lite alone | 51.3% (44.7–58.4%) | 16 of 113 | 4 of 38 | 4 of 84 | $0.11 |
| Mistral Large 3 alone | 40.1% (33.0–47.2%) | 8 of 113 | 1 of 38 | 1 of 84 | $0.99 |
| Compiled pack, Bedrock when unsure | 58.4% (51.8–65.5%) | 8 of 113 | 1 of 38 | 0 of 84 | $0.66 |

Decider settled 62% of cases on its own and passed 75 to Nova Pro. Without Bedrock the gate is just
as safe but cautious: it asked a person about 63 of 84 clean trips. I traced every one of those to a
Decider answer inside the uncertain band, never to a code check, and mostly to three questions
(dishonest descriptions, split claims, personal nights). Retuning the bands on the compiler's
practice cases, with the test cases kept out, took that from 63 to 46 and accuracy from 60% to 66%.
Bedrock-when-unsure did far more.

**One thing to know before you trust the pooled numbers.** I wrote the hand-written pack, 45 of the
cases and every label correction. DeepSeek V3.2 wrote the other 152 from the policy text alone; I
corrected 55 of its labels, mostly the same arithmetic misses the baselines make. Corrections still
favour the pack, so the repo splits every result by where the label came from. On the 97 DeepSeek
cases nobody touched, Bylaw with Bedrock when unsure gets **90% right against Nova Pro's 77%**, and
neither lets a breach through there.

**Speed.** This account had no GPU quota during the hackathon, so Decider ran on a CPU instance
(c7i.4xlarge) at 1–2 s per request, slower than Bedrock. I have no GPU number and I'm not claiming
one. The cost figure spreads the instance's hourly price over decision time as if it were always
busy, plus Bedrock tokens for the calls it passed on.

## The reusable pattern

A compiled policy gate: a Strands `InterventionHandler` that, before a gated tool call runs,
evaluates the pack's code checks, asks every applicable Decider question in one request, maps the
result onto `Proceed`, `Guide`, `Confirm` or `Deny` with a plain decision table, and escalates only
the unsure remainder. A question ships as JSON: typed (yes/no, choice or score), with named options,
which options count as a breach, and the `lo`/`hi` band where it's unsure. `docs/pattern.md` has a
full question, the wiring in a dozen lines, and how to point it at your own policy and tools.

## What I'd tell someone trying this

- Never let a language model do arithmetic you can do in code. That's where the LLM judges failed.
- Keep each Decider question to one judgement. It's strong on short, single decisions.
- Use the probability. A calibrated "unsure" is the reason to use a decision model at all: it tells
  you which 38% of calls deserve a bigger model.
- Model-written test cases need a human pass, and the human pass needs disclosing. Split your results
  by who wrote the label.

The compiler, the gate, the benchmark, every result file and the script that splits them are in the
repo: https://github.com/ajassaif/bylaw.
