# Compiling a travel policy into questions for Strands Decider 2B

*Draft for AWS Builder Center. Numbers in `{{braces}}` are filled from `bench/results` before
publishing. Tags: #strands-decider-2b #policy*

An AI travel agent that can book flights will, sooner or later, book business class because
someone typed "my VP said it's fine". The policy that forbids it already exists. It's a PDF, it's
written for people, and the agent has no reliable way to be held to it.

The obvious fix is a second model call: give an LLM the policy and the proposed booking and ask
whether it's allowed. I tried that as a baseline. It works a lot of the time. It also costs a full
model call on every booking, takes seconds, and answers in prose that the agent, or a persistent
user, can argue with.

Bylaw takes a different route. It treats the policy as source code and compiles it.

## Facts go to code, judgements go to Decider

Strands Decider 2B is a 2-billion-parameter model with its text-generation head removed. You give
it a state and a typed question (yes/no, one of N options, or a score on a scale) and it returns a
probability for each answer in a single forward pass. It doesn't write anything. That makes it a
good fit for one half of a policy and a bad fit for the other.

Take clause 3.2 of the (made-up) Northwind policy: you may go up to 10% over the hotel cap if
nothing suitable is available, with your manager's approval. Two things are tangled together
there. Whether $205 is within 10% of $190 is arithmetic. Whether "the summit hotels are sold out"
is a real reason, rather than "I like the pool", is a judgement.

Bylaw's compiler reads the policy with Mistral Large 3 on Bedrock and splits every clause that
way. Arithmetic, dates, levels and categories become checks: short expressions like

```
ctx.facts.hotel.nightly_rate_usd > tables.hotel_cap[ctx.facts.hotel.city_tier]
```

that are parsed and evaluated against a whitelist, never run as Python. The rate comes from the
hotel inventory, not from whatever number the agent typed. Judgements become typed questions with
named options and a description of each side, which is the part Decider is good at.

## Then it tests its own questions

A typed question is a program, and wording is most of its behaviour. So the compiler doesn't
stop at writing questions. It asks Mistral for practice cases per rule: compliant ones, clear
breaches, borderline ones, and people trying to talk their way past the rule. It sends every
wording of every question to Decider in one request per case (the state is encoded once and
shared, so trying three wordings costs about the same as one), keeps the wording with the lowest
Brier score, and sets two thresholds per question from the measured results: above `hi` the rule
is breached, below `lo` it's clear, and in between a person decides. Questions that stay weak get
rewritten, using the cases they got wrong.

What comes out is a pack: one JSON file and a readable report saying how each clause is enforced
and how each question did on practice cases, including the ones that didn't work.

## The gate

At run time the pack loads into a Strands `InterventionHandler`. Before any booking or expense
tool runs, it renders one state (who's asking, what's booked, the conversation, the proposed
call), runs the checks, asks every relevant Decider question in a single request, and maps the
result onto Strands' own actions:

- `Proceed` when everything is clear at high confidence,
- `Guide` with the clause's remedy when the agent can fix it (pick a cheaper hotel),
- `Confirm` when a person has to sign off, which pauses the agent until they do,
- `Deny` when the policy forbids it.

The agent never sees a paragraph it can push back on. It sees a cancelled call and a reason, and
the decision itself was an `if` statement over probabilities.

A few small rules turned out to matter. A breach the agent can fix outranks a sign-off, so nobody
is asked to approve a booking that's about to change. The same rule sent back twice becomes a
refusal, so a stubborn model can't loop. If the Decider server is down, the gate asks a person; it
never fails open.

## How it did

{{results paragraph: Bylaw vs the hand-written pack vs Bedrock models deciding alone. Lead with the
number that matters most to someone running this: breaches let through. Then accuracy with its
interval, then latency and cost per 1,000 decisions. Say plainly where a baseline won.}}

| | Right verdict | Let a breach through | Median time | $ per 1,000 |
|---|---|---|---|---|
| {{rows from summary.json}} | | | | |

The held-out cases were written by DeepSeek V3.2 from the policy text alone. It never saw the
pack, and it isn't the family that compiled the pack or any baseline. I checked every label by
hand. Another 45 cases I wrote myself, 12 of them attempts to get around a rule: verbal approvals
that were never recorded, a team dinner relabelled as client entertainment, an expense
description that tells the reviewer to ignore the policy.

Before the compiler existed, I wrote a pack by hand. On my laptop's CPU it scored 62% on the
hand-written cases and let none of the breaches through. That sounds safe, but most of its
mistakes were clean bookings sent to a manager for no reason, because untuned questions sat in
the uncertain band. {{one sentence on what tuning changed, from the hand-written-pack row}}

## What I'd tell someone trying this

- Keep each question to one judgement. Decider is strong on short, single decisions and weaker
  when a question hides two.
- Never let the classifier do arithmetic you can do in code.
- Read the calibration, not just the accuracy. A probability you can threshold is the reason to
  use a decision model at all.
- The practice cases are the weakest link. A model writes them, and the pack learns from them.
  Score on cases from somewhere else.

The compiler, the gate, the benchmark and every result file are in the repo: {{repo url}}.
