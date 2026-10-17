# Benchmark data and how it was made

Every number in the README, the article and the workbench's benchmark page is read from a
`results/<run>/summary.json` in this folder. Each run folder also holds `cases.jsonl` (one row per
case per system: expected, predicted, confidence, latency, cost, any error) and `report.md`.

## The cases

`data/heldout/reviewed.jsonl` has 197 cases. None of them was used to compile or tune a pack.

| Source | Cases | How |
|---|---|---|
| DeepSeek V3.2 | 152 | Written from the policy text and the tools' signatures only (`bylaw make-heldout`). DeepSeek never saw a compiled pack, and it is a different model family from the compiler (Mistral Large 3), from every baseline, and from the Decider's torso (Qwen). Every case's arguments are checked against the tools' real input schemas. |
| Hand-written | 45 | `scripts/write_handwritten.py`, each with the clause that decides it. |

50 cases try to talk past a rule (claimed verbal approvals, relabelled expenses, instructions
hidden in a description). They're tagged `manipulation` and reported separately.

## Label review

DeepSeek wrote 160 cases. I read every one against `policies/northwind-travel.md`
(`data/heldout/review.json` holds each decision and its reason):

- **97 kept as labelled.**
- **55 relabelled.** The common disagreements were:
  - DeepSeek marked fixable problems (wrong cabin, a hotel over the cap) as *deny*, where the
    convention is *guide* because the agent can fix them;
  - it read clause 2.1's cabin table as an obligation, so economy on a 9.6-hour flight became a
    breach, when the table only sets a ceiling;
  - it missed the 14-day booking rule when a late flight carried no justification;
  - it missed the $3,000 trip rule when the trip-so-far plus the new booking crossed it.
- **8 dropped** where a careful reader could go either way.

The convention is the same one the LLM judges are given: *proceed* when nothing is breached,
*guide* when the agent can fix the action itself, *confirm* when a named person must sign off,
*deny* when it can't be made acceptable. A breach the agent can fix comes before a sign-off.

The labels are one person's reading of a made-up policy. They are published so anyone can disagree
with a specific case.

## Cost and latency

Bedrock costs use on-demand token prices from the AWS Price List API (`prices.json`, read
2026-10-17). Bylaw's cost is the instance's hourly price spread over the measured Decider time per
decision. Runs on the CPU instance (`c7i.4xlarge`, $0.714/hr) say so in their folder name and in
`summary.json`'s `env`; the Decider gives the same answers on CPU and GPU, but CPU latency is far
higher, so latency claims come only from GPU runs.
