# Bylaw

Bylaw reads a policy written for people, such as a travel and expense policy, and compiles it
into checks a Strands agent has to pass before it acts. Facts become code. Judgements become typed
questions for [Strands Decider 2B](https://github.com/strands-labs/strands-decider), a small model
that answers with a probability instead of prose. Then Bylaw tests those questions on practice
cases, rewrites the ones that come out vague, and sets their thresholds from what it measured.

The demo is a travel desk for Northwind Supply Co. (a made-up company) running on Amazon Bedrock.
Every booking and expense claim goes past the compiled policy first.

Hackathon entry: AWS Agent Experience Hackathon, Strands Decider. Decision pattern: **policy**.
Tags: `#strands-decider-2b` `#policy`. Demo: https://youtu.be/SmfgShc2p2c

**In one line:** code checks the facts, Strands Decider 2B answers the judgement calls, and Amazon
Bedrock is asked only when Decider is unsure. On 197 test cases that got 88.8% of verdicts right
(95% CI 84.3–93.4%) and let none of 113 breaches through. Amazon Nova Pro reading the same policy got
53.8% and let 9 through, at about twice the cost per decision.

![The Bylaw workbench: clause 3.1 highlighted with its code check marked breached, and the travel desk sending South Shore Lofts back](docs/img/workbench.jpg)

## What happens to one booking

Maya asks the desk for South Shore Lofts in Austin. Before `book_hotel` runs, the gate:

1. renders one state: who Maya is, what's booked so far, the conversation, the proposed call;
2. looks up the hotel's real rate ($349) and checks it against the tier-B cap ($190) in code;
3. asks Decider every question that applies to hotel bookings, in one request;
4. turns the answers into a verdict: here, *sent back*, because the rate is more than 10% over.

The agent gets the remedy and the clause that decided it lights up in the margin of the document.
It then tries Congress Avenue Suites at $179, which is under the cap. With the compiled pack that
retry still goes to a person: the Decider put the chance that both nights are work nights at
50%, inside the band where the pack asks someone rather than guessing.

## Results

<!-- bench:start -->
**Hand-written pack: Decider alone, and with Bedrock (Nova Pro) deciding only the calls Decider is unsure of**

| System | Right verdict (95% CI) | Let a breach through | Right on manipulation cases | Calibration error | p50 | p95 | $ per 1,000 | No answer |
|---|---|---|---|---|---|---|---|---|
| Bylaw, Decider alone | 60.4% (53.8–67.0%) | 0.0% | 76.0% | 0.098 | 1.1 s | 2.3 s | $0.261 | 0 |
| Bylaw, Bedrock when unsure | 88.8% (84.3–93.4%) | 0.0% | 86.0% | 0.088 | 1.7 s | 3.4 s | $0.827 | 0 |

197 benchmark cases (50 of them try to talk the agent past a rule), pack `7cfa2e9b1cd0`. Decider on cpu, c7i.4xlarge. Full per-case rows are in the same results folder.

**Hand-written pack with thresholds retuned on the compiler's practice cases**

| System | Right verdict (95% CI) | Let a breach through | Right on manipulation cases | Calibration error | p50 | p95 | $ per 1,000 | No answer |
|---|---|---|---|---|---|---|---|---|
| Bylaw, Decider alone | 66.0% (59.4–72.6%) | 0.0% | 76.0% | 0.090 | 1.1 s | 2.3 s | $0.262 | 0 |
| Bylaw, Bedrock when unsure | 86.3% (81.2–90.9%) | 0.0% | 88.0% | 0.088 | 1.3 s | 3.4 s | $0.689 | 0 |

197 benchmark cases (50 of them try to talk the agent past a rule), pack `de454c87d702`. Decider on cpu, c7i.4xlarge. Full per-case rows are in the same results folder.

**Compiled pack (bc0fbcc69588), and Bedrock models deciding alone**

| System | Right verdict (95% CI) | Let a breach through | Right on manipulation cases | Calibration error | p50 | p95 | $ per 1,000 | No answer |
|---|---|---|---|---|---|---|---|---|
| Bylaw, Decider alone | 44.7% (37.6–51.8%) | 7.1% | 28.0% | 0.273 | 1.9 s | 2.9 s | $0.414 | 0 |
| Bylaw, Bedrock when unsure | 58.4% (51.8–65.5%) | 7.1% | 36.0% | 0.256 | 2.0 s | 3.7 s | $0.655 | 0 |
| Amazon Nova Pro alone | 53.8% (46.7–60.9%) | 8.0% | 32.0% | 0.408 | 772 ms | 1.3 s | $1.524 | 0 |
| Amazon Nova Lite alone | 51.3% (44.7–58.4%) | 14.2% | 24.0% | 0.421 | 637 ms | 940 ms | $0.114 | 3 |
| Mistral Large 3 alone | 40.1% (33.0–47.2%) | 7.1% | 34.0% | 0.592 | 822 ms | 2.7 s | $0.994 | 0 |

197 benchmark cases (50 of them try to talk the agent past a rule), pack `bc0fbcc69588`. Decider on cpu, c7i.4xlarge (CPU). Full per-case rows are in the same results folder.
<!-- bench:end -->

Every number above is produced by `bylaw bench` and nothing else. How the cases were made:

- **Held-out cases** were written by DeepSeek V3.2 from the policy text alone. It never saw the
  compiled pack. It is a different family from Mistral Large 3, which compiled the pack and wrote
  its practice cases, and from every baseline. I reviewed every label by hand against the policy.
- **Hand-written cases**: 45 more, including 12 that try to talk the agent past a rule (fake
  verbal approvals, a team dinner relabelled as client entertainment, instructions hidden in an
  expense description).
- **Baselines** are Bedrock models given the whole policy and the same rendered state, asked for a
  verdict and a confidence as JSON. A model that never produced usable JSON is counted as wrong.

### What the numbers say

**Three layers, cheapest first.** Facts (rates, caps, dates, cabin rules, trip totals) are checked in
code. Judgements (is this reason real, who was at that dinner) go to Decider, which answers with a
probability. A probability between a question's `lo` and `hi` is "unsure". The original design sent
every unsure call to a person; Bedrock-when-unsure sends it to Nova Pro instead, with the whole
policy and the same state, and keeps everything code and Decider were sure about.

**What that buys.** With the hand-written pack:

| | Right verdict (95% CI) | Breaches let through | Talked into a breach | Clean trips sent to a person | $ per 1,000 |
|---|---|---|---|---|---|
| Decider alone | 60.4% (53.8–67.0%) | 0 of 113 | 0 of 38 | 63 of 84 | $0.26 |
| Decider, Bedrock when unsure | **88.8% (84.3–93.4%)** | **0 of 113** | **0 of 38** | 0 of 84 | $0.83 |
| Nova Pro alone | 53.8% (46.7–60.9%) | 9 of 113 | 2 of 38 | 0 of 84 | $1.52 |

Decider settled 62% of cases on its own and passed 75 of 197 to Nova Pro. All 9 of Nova Pro's misses
on its own were arithmetic or a missing field: a trip passing $3,000 without a recorded approval, or a
booking inside 14 days without a reason. In the layered design that half never reaches the model.

**Why Decider alone asked a person so often.** `scripts/explain_confirms.py` shows every one of the
63 came from a Decider answer inside the unsure band, never from a code check that couldn't decide.
Three questions account for most of it: whether a description is dishonest (22), whether one cost is
split across claims (20), and whether a stay includes personal nights (19).

**Retuning helps a little.** `bylaw retune` set each question's band from the compiler's 128 practice
cases (rule ids mapped to this pack in `data/dev/rule-map.handwritten.json`; the test cases were not
used). Decider alone went from 60.4% to 66.0% and from 63 to 46 clean trips sent to a person. With
Bedrock when unsure it scored 86.3%, a little below the untuned pack, but sent 56 calls to Nova Pro
instead of 75. Practice cases written by a model are a thin basis for thresholds; this is the honest
size of the gain.

**Read the split before the pooled accuracy.** I wrote the hand-written pack, 45 of the cases and every
one of the 55 label corrections, and I changed the gate's severity order after looking at three of my
own cases (hw-07, hw-10, hw-44). Most corrections are DeepSeek missing the same arithmetic the
baselines miss, but they still favour the pack. On the 97 DeepSeek cases whose labels I didn't touch,
the hand-written pack with Bedrock when unsure gets 90% right against Nova Pro's 77%, with no breach
through either. Decider alone gets 43% there, because it asks a person about most clean trips.
Generated with `python -m scripts.split_table bench/results/2026-10-17-c7i
bench/results/2026-10-19-c7i.4xlarge-handwritten-hybrid bench/results/2026-10-19-c7i.4xlarge-handwritten-tuned`:

**DeepSeek, label kept** (97 cases)

| System | Right verdict | Let a breach through | Talked into a breach | Clean cases sent to a person |
|---|---|---|---|---|
| Amazon Nova Lite alone | 77% | 0 of 34 | 0 of 10 | 3 of 63 |
| Amazon Nova Pro alone | 77% | 0 of 34 | 0 of 10 | 0 of 63 |
| Bylaw, compiled pack | 43% | 2 of 34 | 1 of 10 | 21 of 63 |
| Bylaw, compiled pack, Bedrock when unsure | 66% | 2 of 34 | 1 of 10 | 0 of 63 |
| Bylaw, hand-written pack | 43% | 0 of 34 | 0 of 10 | 47 of 63 |
| Bylaw, hand-written pack, Bedrock when unsure | 90% | 0 of 34 | 0 of 10 | 0 of 63 |
| Bylaw, hand-written pack, retuned | 52% | 0 of 34 | 0 of 10 | 34 of 63 |
| Bylaw, retuned, Bedrock when unsure | 85% | 0 of 34 | 0 of 10 | 0 of 63 |
| Mistral Large 3 alone | 59% | 1 of 34 | 0 of 10 | 1 of 63 |

**DeepSeek, relabelled** (55 cases)

| System | Right verdict | Let a breach through | Talked into a breach | Clean cases sent to a person |
|---|---|---|---|---|
| Amazon Nova Lite alone | 7% | 10 of 50 | 2 of 19 | 1 of 5 |
| Amazon Nova Pro alone | 15% | 8 of 50 | 2 of 19 | 0 of 5 |
| Bylaw, compiled pack | 40% | 4 of 50 | 0 of 19 | 2 of 5 |
| Bylaw, compiled pack, Bedrock when unsure | 42% | 4 of 50 | 0 of 19 | 0 of 5 |
| Bylaw, hand-written pack | 89% | 0 of 50 | 0 of 19 | 4 of 5 |
| Bylaw, hand-written pack, Bedrock when unsure | 89% | 0 of 50 | 0 of 19 | 0 of 5 |
| Bylaw, hand-written pack, retuned | 87% | 0 of 50 | 0 of 19 | 4 of 5 |
| Bylaw, retuned, Bedrock when unsure | 89% | 0 of 50 | 0 of 19 | 0 of 5 |
| Mistral Large 3 alone | 5% | 6 of 50 | 1 of 19 | 0 of 5 |

**Written by the pack's author** (45 cases)

| System | Right verdict | Let a breach through | Talked into a breach | Clean cases sent to a person |
|---|---|---|---|---|
| Amazon Nova Lite alone | 49% | 6 of 29 | 2 of 9 | 0 of 16 |
| Amazon Nova Pro alone | 51% | 1 of 29 | 0 of 9 | 0 of 16 |
| Bylaw, compiled pack | 53% | 2 of 29 | 0 of 9 | 4 of 16 |
| Bylaw, compiled pack, Bedrock when unsure | 62% | 2 of 29 | 0 of 9 | 0 of 16 |
| Bylaw, hand-written pack | 62% | 0 of 29 | 0 of 9 | 12 of 16 |
| Bylaw, hand-written pack, Bedrock when unsure | 87% | 0 of 29 | 0 of 9 | 0 of 16 |
| Bylaw, hand-written pack, retuned | 71% | 0 of 29 | 0 of 9 | 8 of 16 |
| Bylaw, retuned, Bedrock when unsure | 87% | 0 of 29 | 0 of 9 | 0 of 16 |
| Mistral Large 3 alone | 42% | 1 of 29 | 0 of 9 | 0 of 16 |

**All DeepSeek cases** (152 cases)

| System | Right verdict | Let a breach through | Talked into a breach | Clean cases sent to a person |
|---|---|---|---|---|
| Amazon Nova Lite alone | 52% | 10 of 84 | 2 of 29 | 4 of 68 |
| Amazon Nova Pro alone | 55% | 8 of 84 | 2 of 29 | 0 of 68 |
| Bylaw, compiled pack | 42% | 6 of 84 | 1 of 29 | 23 of 68 |
| Bylaw, compiled pack, Bedrock when unsure | 57% | 6 of 84 | 1 of 29 | 0 of 68 |
| Bylaw, hand-written pack | 60% | 0 of 84 | 0 of 29 | 51 of 68 |
| Bylaw, hand-written pack, Bedrock when unsure | 89% | 0 of 84 | 0 of 29 | 0 of 68 |
| Bylaw, hand-written pack, retuned | 64% | 0 of 84 | 0 of 29 | 38 of 68 |
| Bylaw, retuned, Bedrock when unsure | 86% | 0 of 84 | 0 of 29 | 0 of 68 |
| Mistral Large 3 alone | 39% | 7 of 84 | 1 of 29 | 1 of 68 |

**The compiled pack is a first draft.** Alone it is right on 44.7% of cases, below Nova Pro. Most of
the gap is two compiler mistakes, both visible in `packs/northwind.pack.md`: it marked the cabin rule
and the recorded-approval rule as *refuse* instead of *send back*, so 30 of the 78 fixable breaches
were refused outright; and it pulled the $3,000 trip check for flights after that check failed its
practice cases, so 7 of the 8 breaches it let through are large flight bookings with no recorded
approval. The pack report points at both; a person fixing them is the intended workflow.

**Speed and cost.** These runs used a CPU instance (c7i.4xlarge), where a Decider request took 1–2 s
and Bedrock answered in under 1 s; this run says nothing in Decider's favour on speed. Bylaw's $ per
1,000 spreads the instance's hourly price over measured decision time, as if the instance were busy
all the time, plus Bedrock tokens for the escalated calls.

## Run it

```bash
uv sync --extra decider
uv run --extra decider strands-decider serve StrandsAgents/strands-decider-2B-qwen3.5-v1-2610 --port 8099
uv run --extra decider bylaw serve --pack packs/northwind.handwritten.pack.json --decider-timeout 120   # needs Bedrock credentials
cd web && npm install && npm run dev                                     # http://localhost:5173
```

The first Decider start downloads about 4.5 GB. On a laptop CPU one gate check takes 20–30 s,
hence the long timeout; on a GPU it is far quicker.

No Bedrock? `bylaw serve --scripted` swaps the language model for a fixed set of demo requests.
The gate and the Decider are still real. See [docs/dev.md](docs/dev.md).

Compile your own policy: [docs/pattern.md](docs/pattern.md). Deploy on AWS:
[deploy/README.md](deploy/README.md).

## How it's built

| Piece | Where |
|---|---|
| Pack format, restricted expression language | `src/bylaw/pack.py`, `src/bylaw/expr.py` |
| Decision table and gate (`InterventionHandler`) | `src/bylaw/decide.py`, `src/bylaw/gate.py` |
| Compiler: extract, generate practice cases, tune, report | `src/bylaw/compiler/` |
| Travel desk agent and fixtures | `src/bylaw/agent/` |
| Benchmark and metrics | `src/bylaw/bench/`, `src/bylaw/metrics.py` |
| Workbench UI | `web/` |

Model-written checks are never run as Python. They are parsed and evaluated against a whitelist,
and a missing field makes a check *unknown*, which sends the call to a person rather than letting
it through.

## Limits

- One policy, made up for the demo, and cases written by models and by me. It shows the method
  works on this policy; it doesn't prove it on yours. Run the benchmark on your own cases.
- Decider 2B is an experimental model. It is strong on short single judgements and weaker on
  multi-step reasoning, so the compiler keeps each question to one judgement.
- The Decider server has no authentication and handles one request at a time. Bylaw keeps it on
  localhost and serializes calls.

Apache-2.0.
