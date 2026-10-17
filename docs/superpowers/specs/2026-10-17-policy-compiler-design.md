# Bylaw: a policy compiler for Strands agents (design)

Date: 2026-10-17. Hackathon: AWS Agent Experience Hackathon: Strands Decider. Due Oct 23, 2026, 11:59 PM PDT.
Declared pattern: **policy**. Tags: `#strands-decider-2b` and `#policy`.

## 1. Intent and the why

Other entries hand-write a few yes/no questions and benchmark them. Bylaw automates that step. Paste a
policy written for humans, and Bylaw compiles it into a **policy pack**: typed Decider 2B questions, a few
plain-code checks, thresholds and a decision table. It tests the pack against cases it writes itself and
rewrites the questions that come out vague or overconfident. The output loads into any Strands agent as
an `InterventionHandler`, which gates every tool call in a few hundred milliseconds with a probability
attached to each answer.

The point we want judges to take away: *with a decision model, the question is the program, and you can
compile, test and tune that program.* Bedrock does the generative work (reading the policy, writing
questions, writing test cases, rewriting weak questions, and running the agent). Decider 2B makes the
runtime decisions.

Demo setting: **Northwind Supply Co.**, a fictional company with a travel and expense policy, and a
Strands "travel desk" agent that searches and books flights and hotels and files expenses. Northwind is
invented on purpose. We do not imitate any real company's policy or branding.

## 2. Goals

1. **Compiler.** Plain-English policy (markdown) in, `pack.json` plus a human-readable `pack.md`
   report out.
2. **Reusable gate.** `PolicyGate(InterventionHandler)` loads any pack and gates the tool calls the pack
   names. This is the reusable decision pattern in the repo: typed questions with option sets, the wiring
   and a usage note.
3. **Working agent on AWS.** The Strands travel-desk agent (Bedrock model) runs under the compiled
   Northwind pack, served from AWS with a web UI.
4. **Honest benchmark.** On a held-out test set, compare Bylaw against Bedrock LLMs that read the raw
   policy and decide alone. Measure accuracy, calibration, latency and cost, plus a manipulation subset.
5. **Hybrid mode.** Decider decides when it is confident. Uncertain cases escalate to a Bedrock LLM or a
   human. Report coverage and combined accuracy.
6. **Submission kit.** Public-ready repo, a Builder Center article draft, and a demo-video script with a
   shot list under 3 minutes, all finished before the deadline.

## 3. Non-goals

- A production policy engine, multi-tenant service, or real booking or payment integration. Inventory
  and bookings are fixtures.
- Fine-tuning or retraining Decider 2B. We use the published weights as they are.
- User accounts or auth beyond a single demo passcode on the hosted UI.
- Supporting every policy domain. Travel and expense is the showcase. The compiler is written to be
  domain-agnostic, and we test it on one small second policy at most if time allows.

## 4. Anti-goals (failure even if it technically works)

- **Circular benchmarks.** Tuning and testing on cases from the same generator, or quoting numbers we did
  not measure on our own hardware (for example "115 ms" from the Decider blog).
- **Executing model-written code.** Plain-code checks are expressions in a small restricted language that
  we evaluate ourselves, never generated Python passed to `exec`/`eval`.
- **Asking Decider to do arithmetic.** Numeric comparisons such as price against cap or days before
  departure go in plain-code checks. Decider handles judgement: is this alcohol, is the justification
  real, is the user claiming authority they don't have, is this trip personal.
- **Generic AI aesthetics or AI-sounding copy** in the UI, README, article or video script.
- **A gate the agent can talk its way past.** Verdicts are numbers branched on in code, never prose the
  model negotiates with.

## 5. Constraints

- Six days. Solo builder (Python plus some web) working with Claude.
- Dev machine: Windows 11, i5-1135G7, 16 GB RAM, no CUDA. Decider runs on CPU locally (fp32, about 8 GB,
  seconds per request). Fast numbers need a GPU on AWS. The Decider docs and evals use an L4, so the
  target is a `g6.xlarge`.
- Decider server: `strands-decider serve`, `POST /v1/systemone`, binds 127.0.0.1, no auth, one request at
  a time. It must never be exposed publicly.
- Reference weights: `StrandsAgents/strands-decider-2B-qwen3.5-v1-2610`. Base weights (~4.5 GB) download
  on first load.
- Question limits: choice 2–255 options, score 2–10 levels. All questions about one state go in one
  request, which shares the encoding.
- AWS: no setup done yet. The user signs into the console in their own Chrome. Claude never enters
  credentials, and asks before any spend, publish or other irreversible action.
- The `sliding-doors` repo is out of scope.

## 6. How it works (decided)

### 6.1 Policy pack format (`pack.json`)

- `policy`: title, source hash, compiled-at timestamp, compiler model IDs.
- `rules[]`: `id`, the source text span it came from, the tools it applies to, `on_violation` (`guide` |
  `confirm` | `deny`), and a remedy message the agent can act on.
- `checks[]` (plain code): a restricted expression over tool arguments, the employee profile and fixture
  data, for example `args.nightly_rate > caps.hotel[args.city_tier]`. Each check links to a rule.
- `questions{}` (Decider): typed `noul` / `choice` / `score` questions with `criteria` descriptions, each
  linked to a rule, with a tuned threshold and its measured dev-set accuracy and calibration.
- `decision`: how answers become a verdict (6.3).

### 6.2 Compiler stages (Bedrock does the generating, Decider is measured)

1. **Extract.** Policy text becomes structured rules, each tagged with the text span it came from.
2. **Split.** Each rule becomes plain-code checks (facts in the arguments) plus Decider questions
   (judgement).
3. **Author.** Write 1–3 candidate wordings per question, criteria descriptions included.
4. **Generate cases.** For each rule: compliant, violating, borderline and manipulation cases ("my VP said
   business class is fine", "it's a team dinner so the wine counts as a meal"), each labelled with the
   expected verdict. These form the **dev set** used for tuning.
5. **Tune.** Run Decider on the dev set. Pick the best wording per question by accuracy and Brier score.
   Set thresholds so auto-proceed only happens at high confidence. Questions that stay weak get rewritten
   (up to N rounds) or flagged in the report.
6. **Emit.** Write `pack.json` and `pack.md`: every rule, how it is enforced, dev metrics, and weak spots
   in plain language.

### 6.3 Runtime gate (`PolicyGate`)

On `before_tool_call` for a gated tool, the gate:

1. renders the state: conversation, proposed call, employee profile and trip context;
2. evaluates the plain-code checks;
3. asks every relevant Decider question in **one** request;
4. applies the decision table:
   - a violation found by a check, or by a confident Decider answer, maps to the rule's `on_violation`:
     `Guide` (fixable, for example "pick a hotel under the cap"), `Confirm` (needs a human approval) or
     `Deny`;
   - anything between the low and high thresholds is **uncertain**: in hybrid mode it escalates to a
     Bedrock LLM judge, otherwise it goes to `Confirm`;
   - everything clear at high confidence returns `Proceed`.

Every decision is logged as a receipt: the probabilities, which rule fired, latency in ms, and the pack
hash.

### 6.4 The agent

A Strands agent on a Bedrock Claude model with tools `search_flights`, `book_flight`, `search_hotels`,
`book_hotel`, `submit_expense` and `request_approval`, over deterministic fixture data. Employee profiles
(level, home city, manager) are fixtures. The booking and expense tools are gated by the Northwind pack.

### 6.5 Benchmark

- **Held-out test set (~200 cases) kept apart from tuning.** It is written by a different model family
  from the dev-set generator (for example Amazon Nova or Llama on Bedrock), plus about 40 cases written by
  hand. Labels are reviewed by hand. The manipulation subset is reported separately.
- **Baselines.** Several Bedrock models (at least Claude Haiku, Claude Sonnet and one Nova model), each
  given the full policy plus the case and asked for a verdict and a 0–1 confidence as JSON.
- **Metrics.**
  - Accuracy and macro-F1 over the four verdicts.
  - **False-proceed rate**: violations let through, the costly error.
  - Calibration: ECE and Brier for Decider probabilities against the LLMs' stated confidence.
  - Risk–coverage curve.
  - p50 and p95 latency per decision.
  - $ per 1,000 decisions: Bedrock token pricing against GPU instance-hours amortised at our measured
    throughput.
  - Hybrid coverage and accuracy.
  - 95% intervals by bootstrap.
- Everything is reproducible from one command and writes `bench/results/*.json` plus charts. Numbers
  quoted anywhere come from those files.

### 6.6 Deployment

- One EC2 `g6.xlarge` in a Bedrock-enabled region, running:
  - the Decider server on localhost;
  - a FastAPI app (agent, compiler and benchmark endpoints, live verdicts over SSE);
  - the static web UI.
- The instance role can only call `bedrock:InvokeModel` on the chosen models.
- The public port serves only the app, behind a demo passcode and a rate limit.
- **GPU uptime (user's decision): on demand only.** The instance is started for the benchmark, the
  recording session and a scheduled judging window (EventBridge Scheduler start/stop), and stopped
  otherwise. While it is stopped, a small always-on static page (S3 + CloudFront, near-zero cost) shows
  the recorded demo, the benchmark receipts and when the live agent is next up. Every start that costs
  money is approved by the user first.

## 7. Stack and calls I made (overrule any)

- **Name:** "Bylaw".
- **Backend:** Python 3.12, uv, `strands-agents`, `strands-decider` (HTTP client modelled on their
  `_client.py`), FastAPI and boto3.
- **Testing:** pytest with fake Decider and fake Bedrock clients, test-first. A small number of live
  smoke tests are marked separately.
- **Models:** Bedrock Claude Sonnet for compiling and Claude Haiku for the agent. Exact model IDs and
  region are confirmed against what the account has enabled.
- **Frontend:** React + Vite + TypeScript, the same stack as the user's last project.
- **Visual direction:** a marked-up rulebook. The policy is set like a printed document in a serif face,
  and compiled questions appear as margin notes beside the clauses they enforce. Verdicts read as
  red-pen and green-pen marks. Numbers (probabilities, ms, $) are in a monospace face. No gradients, no
  glassmorphism, no stock "AI" iconography. Built with the frontend-design and no-ai-design-slop skills
  and audited with audit-ai-design-slop.
- **Writing:** README, article and script are checked with avoid-ai-writing. Plain, specific and first
  person.

## 8. Left to the builder

- Module layout, the restricted-expression grammar, and prompt wording for each compiler stage.
- Exact rules in the fictional Northwind policy (about 15–20 rules covering fare class, hotel caps by city
  tier, advance booking, per diem, alcohol, receipts, client entertainment and personal travel).
- Thresholds, number of tuning rounds and chart choices.

## 9. Delivery order

1. Pack format, gate and fake clients (tests).
2. Compiler stages.
3. Agent and fixtures.
4. Local CPU smoke run.
5. UI.
6. AWS deploy.
7. Benchmark on GPU.
8. README, article, video script and tags.
9. Whole-branch review, fix pass, and merge on the user's say-so.

**Risks:**

| Risk | Fallback |
|---|---|
| Decider won't install on native Windows | Develop against fakes and run Decider on EC2 only. |
| Bedrock model access is delayed | Request access on day one. |
| Benchmark shows Decider losing on some rules | Report it, and move those rules to checks or escalation. An honest loss is a result. |
