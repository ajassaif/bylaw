# A travel desk that checks the policy before it books

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
`if` statement over probabilities. On 197 test cases, the gate with a hand-written pack let none
of the 113 breaches through. Nova Pro, reading the same policy, let 9 through, and every one of
those was arithmetic: a trip total over $3,000, or a booking too close to departure.

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
refusal, so a stubborn model gets refusals instead of more chances. If the Decider server is down, the gate asks a person; it
never fails open.

## How it did

I tested two packs against Bedrock models given the whole policy and the same state. One pack is
the compiler's output, untouched. The other I wrote by hand, before the compiler had produced a
pack, using the same format and the same gate. All five systems saw the same 197 cases.

| | Let a breach through | Talked into a breach | Right verdict (95% CI) | Clean cases sent to a person |
|---|---|---|---|---|
| Bylaw, hand-written pack | **0 of 113** | **0 of 38** | 60.4% (53.8–67.0%) | 63 of 84 |
| Bylaw, compiled pack | 8 of 113 | 1 of 38 | 44.7% (37.6–51.8%) | 27 of 84 |
| Amazon Nova Pro alone | 9 of 113 | 2 of 38 | 53.8% (46.7–60.9%) | 0 of 84 |
| Amazon Nova Lite alone | 16 of 113 | 4 of 38 | 51.3% (44.7–58.4%) | 4 of 84 |
| Mistral Large 3 alone | 8 of 113 | 1 of 38 | 40.1% (33.0–47.2%) | 1 of 84 |

"Talked into a breach" counts the manipulation cases that should have been stopped and went ahead.

The result I'd build on is the first column. Nothing got past the hand-written pack. All 9 of Nova
Pro's misses were arithmetic or a missing field, the half of the policy Bylaw does in code. Language
models are good at reading a policy and bad at adding up a trip.

The cost is the last column, and it's large. The pack sent 63 of the 84 clean bookings to a person.
A Decider answer between `lo` and `hi` goes to a person by design, and with untuned default
thresholds a lot of answers land there. A manager would be signing off three of every four routine
trips. That's the dial the compiler's tuning is meant to turn.

One more thing to know before trusting the pooled accuracy: I wrote the hand-written pack, 45 of the
cases and every label correction, and I changed the gate's severity order after looking at three of
my own cases. DeepSeek wrote the other 152 from the policy alone; I corrected 55 of its labels, most
of them the same arithmetic misses. On the 97 DeepSeek cases I didn't touch, Nova Pro gets more
verdicts exactly right than the hand-written pack (77% against 43%), and also lets no breach
through. The repo has the full split, and the script that makes it.

The compiled pack doesn't reach the hand-written one yet. It is right on 44.7% of cases, below Nova
Pro alone. Two compiler mistakes explain most of the gap, and both are visible in its report: it
marked two fixable rules as *refuse*, so 30 breaches the agent could have fixed were refused
outright, and it pulled the $3,000 trip check for flights after that check failed its practice
cases, which is where 7 of its 8 missed breaches come from. Sending its unsure answers to Nova Pro
lifts it to 58.4%, which ties Nova Pro alone.

So the honest summary: the gate works, and the compiler is a fast first draft that a person still
has to correct. The report it writes points at exactly what to correct.

Speed and cost: these runs were on a CPU instance, where the Decider took about 2 seconds per
request and Bedrock answered in under one. This account had no GPU quota during the hackathon, so I
have no GPU number and I'm not claiming one. Bylaw's cost per 1,000 decisions ($0.30 against Nova
Pro's $1.52) spreads the instance's hourly price over decision time, as if it were busy all the time.

The test cases were mostly written by DeepSeek V3.2 from the policy text alone. It never saw either
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

The compiler, the gate, the benchmark and every result file are in the repo: https://github.com/ajassaif/bylaw.
