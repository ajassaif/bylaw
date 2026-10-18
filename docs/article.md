# Fifty attempts to talk an AI travel agent past its policy

*AWS Builder Center. Tags: #strands-decider-2b #policy*

An AI travel agent that can book flights will, sooner or later, book business class because
someone typed "my VP said it's fine". The policy that forbids it already exists. It's a PDF, it's
written for people, and the agent has no reliable way to be held to it.

The obvious fix is a second model call: give an LLM the policy and the proposed booking and ask
whether it's allowed. I tried that as a baseline. It works a lot of the time. It also costs a full
model call on every booking, takes seconds, and answers in prose that the agent, or a persistent
user, can argue with.

Bylaw takes a different route. It turns the policy into a gate the agent can't talk to: facts
are checked in code, judgements are typed questions for Strands Decider 2B, and the verdict is an
`if` statement over probabilities. On 197 cases it had never seen, 50 of them attempts to get
around a rule, that gate with a hand-written pack let no breach through and held 38 of the 50 attempts. Bedrock models
reading the same policy held 12 to 17.

## Facts go to code, judgements go to Decider

Strands Decider 2B is a 2-billion-parameter model with its text-generation head removed. You give
it a state and a typed question (yes/no, one of N options, or a score on a scale) and it returns a
probability for each answer in a single forward pass. It doesn't write anything. That makes it a
good fit for one half of a policy and a bad fit for the other.

Take clause 3.2 of the (made-up) Northwind policy: you may go up to 10% over the hotel cap if
nothing suitable is available, with your manager's approval. Two things are tangled together
there. Whether $205 is within 10% of $190 is arithmetic. Whether "the summit hotels are sold out"
is a real reason, rather than "I like the pool", is a judgement.

Bylaw's compiler drafts that split. It reads the policy with Mistral Large 3 on Bedrock and
sorts every clause. Arithmetic, dates, levels and categories become checks: short expressions like

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
and how each question did on practice cases, including the ones that didn't work. The report is
written for the person who owns the policy, because, as the results below show, a compiled pack
still needs one.

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

I tested two packs against Bedrock models given the whole policy and the same state. One pack is
the compiler's output, untouched. The other I wrote by hand before the compiler existed, using the
same format and the same gate. All five systems saw the same 197 cases.

| | Let a breach through | Held a manipulation attempt | Right verdict (95% CI) | $ per 1,000 |
|---|---|---|---|---|
| Bylaw, hand-written pack | **0 of 113** | **38 of 50** | 60.4% (53.8–67.0%) | $0.30 |
| Bylaw, compiled pack | 8 of 113 | 14 of 50 | 44.7% (37.6–51.8%) | $0.41 |
| Amazon Nova Pro alone | 9 of 113 | 16 of 50 | 53.8% (46.7–60.9%) | $1.52 |
| Amazon Nova Lite alone | 16 of 113 | 12 of 50 | 51.3% (44.7–58.4%) | $0.11 |
| Mistral Large 3 alone | 8 of 113 | 17 of 50 | 40.1% (33.0–47.2%) | $0.99 |

The hand-written pack is the result I'd build on. It let none of the 113 breaches through and held
three of four manipulation attempts, where the best model alone held one in three. It costs a fifth
of Nova Pro per decision, because only the Decider runs on every call.

Its cost is caution, and it's large. It sent 63 of the 84 clean bookings to a person for sign-off.
A Decider answer that lands between `lo` and `hi` goes to a person by design, and with untuned
default thresholds a lot of answers land there. Nothing was booked that shouldn't have been, but a
manager would be signing off three of every four routine trips. That's the dial the compiler's
tuning is meant to turn.

The compiled pack doesn't reach the hand-written one yet. It is right on 44.7% of cases, below Nova
Pro alone. Two compiler mistakes explain most of the gap, and both are visible in its report: it
marked two fixable rules as *refuse*, so 30 breaches the agent could have fixed were refused
outright, and it pulled the $3,000 trip check for flights after that check failed its practice
cases, which is where 6 of its 8 missed breaches come from. Sending its unsure answers to Nova Pro
lifts it to 58.4%, which ties Nova Pro alone.

So the honest summary is: the gate works, and the compiler is a fast first draft that a person
still has to correct. The report it writes points at exactly what to correct.

Speed: these runs were on a CPU instance, where the Decider took about 2.3 seconds per request and
Bedrock answered in under a second. Decider is built to answer in about 115 ms on a GPU; this
account had no GPU quota during the hackathon, so I can't show that number, and I'm not claiming
one.

The held-out cases were written by DeepSeek V3.2 from the policy text alone. It never saw either
pack, and it isn't the family that compiled the pack or any baseline. I checked every label by
hand, relabelled 55 and dropped 8 as ambiguous. Another 45 cases I wrote myself, 12 of them
attempts to get around a rule: verbal approvals that were never recorded, a team dinner relabelled
as client entertainment, an expense description that tells the reviewer to ignore the policy.

## What I'd tell someone trying this

- Keep each question to one judgement. Decider is strong on short, single decisions and weaker
  when a question hides two.
- Never let the classifier do arithmetic you can do in code.
- Read the calibration, not just the accuracy. A probability you can threshold is the reason to
  use a decision model at all.
- The practice cases are the weakest link. A model writes them, and the pack learns from them.
  Score on cases from somewhere else.
- Treat a compiled pack like generated code: read the report, fix what it flags, then ship it.

The compiler, the gate, the benchmark and every result file are in the repo: https://github.com/{{owner}}/bylaw.
