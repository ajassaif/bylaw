# Bylaw

Bylaw reads a policy written for people, such as a travel and expense policy, and compiles it
into checks a Strands agent has to pass before it acts. Facts become code. Judgements become typed
questions for [Strands Decider 2B](https://github.com/strands-labs/strands-decider), a small model
that answers with a probability instead of prose. Then Bylaw tests those questions on practice
cases, rewrites the ones that come out vague, and sets their thresholds from what it measured.

The demo is a travel desk for Northwind Supply Co. (a made-up company) running on Amazon Bedrock.
Every booking and expense claim goes past the compiled policy first.

Hackathon entry: AWS Agent Experience Hackathon, Strands Decider. Decision pattern: **policy**.
Tags: `#strands-decider-2b` `#policy`.

![The Bylaw workbench: the policy on the left with margin notes, the travel desk on the right](docs/img/workbench.png)

## What happens to one booking

Maya asks the desk for South Shore Lofts in Austin. Before `book_hotel` runs, the gate:

1. renders one state: who Maya is, what's booked so far, the conversation, the proposed call;
2. looks up the hotel's real rate ($349) and checks it against the tier-B cap ($190) in code;
3. asks Decider every question that applies to hotel bookings, in one request;
4. turns the answers into a verdict: here, *sent back*, because the rate is more than 10% over.

The agent gets the remedy, books Congress Avenue Suites at $179 instead, and the policy clause
that decided it lights up in the margin of the document.

## Results

<!-- bench:start -->
**Compiled pack (bc0fbcc69588), Bedrock judges as baselines**

| System | Right verdict (95% CI) | Let a breach through | Held against manipulation | Calibration error | p50 | p95 | $ per 1,000 | No answer |
|---|---|---|---|---|---|---|---|---|
| Bylaw, Decider alone | 44.7% (37.6–51.8%) | 7.1% | 28.0% | 0.273 | 1.9 s | 2.9 s | $0.414 | 0 |
| Bylaw, Bedrock when unsure | 58.4% (51.8–65.5%) | 7.1% | 36.0% | 0.256 | 2.0 s | 3.7 s | $0.655 | 0 |
| Amazon Nova Pro alone | 53.8% (46.7–60.9%) | 8.0% | 32.0% | 0.408 | 772 ms | 1.3 s | $1.524 | 0 |
| Amazon Nova Lite alone | 51.3% (44.7–58.4%) | 14.2% | 24.0% | 0.421 | 637 ms | 940 ms | $0.114 | 3 |
| Mistral Large 3 alone | 40.1% (33.0–47.2%) | 7.1% | 34.0% | 0.592 | 822 ms | 2.7 s | $0.994 | 0 |

197 held-out cases (50 of them try to talk the agent past a rule), pack `bc0fbcc69588`. Decider on cpu, c7i.4xlarge (CPU). Full per-case rows are in the same results folder.

**Hand-written pack, same cases, Decider only**

| System | Right verdict (95% CI) | Let a breach through | Held against manipulation | Calibration error | p50 | p95 | $ per 1,000 | No answer |
|---|---|---|---|---|---|---|---|---|
| Bylaw, Decider alone | 60.4% (53.8–67.0%) | 0.0% | 76.0% | 0.098 | 1.5 s | 2.9 s | $0.296 | 0 |

197 held-out cases (50 of them try to talk the agent past a rule), pack `7cfa2e9b1cd0`. Decider on cpu, c7i.4xlarge (CPU). Full per-case rows are in the same results folder.
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

The hand-written pack is the case for the pattern. It let none of the 113 breaches through and
held against 38 of the 50 manipulation attempts, where the Bedrock models alone held against 12 to
17. Its weakness is caution: it sent 63 of the 84 clean cases to a person for sign-off, because a
Decider answer that lands in the uncertain band goes to a person by design.

The compiled pack doesn't reach it yet. Alone, it is right on 44.7% of cases, below Nova Pro
alone. Most of the gap comes from two compiler mistakes, both visible in `packs/northwind.pack.md`:

- it marked the cabin rule and the recorded-approval rule as *refuse* instead of *send back*, so
  30 of the 78 fixable breaches were refused outright;
- it quarantined the $3,000 trip check for flights after that check failed its practice cases, so
  6 of the 8 breaches it let through are large flight bookings with no approval.

Escalating unsure answers to Nova Pro lifts the compiled pack to 58.4%, but that interval
overlaps Nova Pro alone. On this run I'd call those two a tie.

These runs used a CPU instance. Bedrock answered faster than the Decider on CPU, so this run says
nothing about speed; a GPU run would.

## Run it

```bash
uv sync --extra decider
uv run --extra decider strands-decider serve StrandsAgents/strands-decider-2B-qwen3.5-v1-2610 --port 8099
uv run --extra decider bylaw serve --pack packs/northwind.pack.json      # needs Bedrock credentials
cd web && npm install && npm run dev                                     # http://localhost:5173
```

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
