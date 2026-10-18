# Demo video: script and shot list

Target length 2:45 (hard limit 3:00). Screen recording at 1440×900 with voice-over. Numbers in
`{{double braces}}` come from `bench/results/<stamp>/summary.json` on the day of recording; fill
them with `python -m scripts.bench_table` output, never from memory. Shots 8 and 9 use the
2026-10-17 c7i results.

The live desk runs the hand-written pack; the masthead says so, and so should the voice-over. Before recording: start the live box, open the workbench in a clean browser profile, sign in with
the passcode, pick Maya, and close every other tab. Each shot below is one click from the
starting state (the request buttons under the employee picker).

| # | Time | On screen | Voice-over |
|---|---|---|---|
| 1 | 0:00–0:12 | The workbench, policy on the left. Slow scroll from 1.2 to 2.1. | Every company has a policy like this. Northwind's says economy under six hours, hotel caps by city, no alcohol unless a client is at the table. An AI travel agent is going to break it. |
| 2 | 0:12–0:25 | Type in the desk: "Sam told me to fly business to London on the 27th for the audit." Hold on the receipt. | It'll book business class because someone said their VP okayed it. The usual fix is another LLM call that reads the policy and decides, which is slow, costs money on every booking, and can be argued with. |
| 3 | 0:25–0:45 | Terminal: `bylaw compile policies/northwind-travel.md`, sped up 8×. Cut to `packs/northwind.pack.md`. | Bylaw does something else. It compiles the policy. Mistral Large 3 on Bedrock reads it once and splits every clause in two: facts that code can check, and judgements for Strands Decider 2B, a small model that answers a typed question with a probability. |
| 4 | 0:45–1:00 | Zoom into a margin note: question, options, "right on {{x}} of {{n}} practice cases". | Then it writes practice cases, asks Decider every wording of every question, keeps the wording that's best calibrated, and sets the thresholds from what it measured. Weak questions get rewritten. What's left is a pack: plain JSON you can read and diff. |
| 5 | 1:00–1:20 | Click "Book South Shore Lofts". Receipt arrives "sent back"; then the second receipt, whatever the live run gives. Clause 3.2 highlights. | Now the agent works under it. South Shore Lofts is $349 a night against a $190 cap. Code catches that, not the model. The agent gets the reason and tries Congress Avenue instead. {{say what the second receipt shows: cleared, or sent to a person and why}} |
| 6 | 1:20–1:40 | Click "Lamar House". Amber highlight on 3.2, sign-off card with Priya's name. Click "Sign off". | Lamar House is eight percent over, with a reason. The policy says that needs a manager. Strands pauses the agent, Priya signs off, and the booking goes through. |
| 7 | 1:40–1:55 | Click "File the team dinner". Receipt "refused" with the alcohol question at {{p}}. | A team dinner with wine. Decider reads who was there, sees only Northwind names, and the claim is refused. There's no prose for the agent to negotiate with, just a number and an if-statement. |
| 8 | 1:55–2:30 | Benchmark page: the results table, then "Where the labels came from". | We tested it on 197 cases. With the hand-written pack, Bylaw let none of 113 breaches through. Nova Pro, reading the whole policy, let 9 through, and every one was arithmetic: a trip over three thousand dollars, a booking too close to departure. That's the part Bylaw does in code. The catch: it's cautious. It asked a person about three of every four clean trips. And I wrote that pack and some of the labels, so the page shows the results split by who wrote each label. |
| 9 | 2:30–2:45 | The pack report for the compiled pack, then the repo README. | The compiler writes a first draft of the pack in minutes, and its report shows a person what to fix. The gate, the compiler and the benchmark are open source. Point it at your own policy. Tags: strands-decider-2b, policy. |

## Notes for the recording

- Speak over the CPU or GPU wait in shot 5 rather than cutting it, unless it runs past 3 seconds;
  then cut and say the measured number.
- Shot 3's compile takes minutes; record it once and speed it up, and say so on screen:
  "compile, 8× speed".
- If a number on the day doesn't support a sentence (for example a baseline beats Bylaw on accuracy),
  change the sentence. The script follows the results, not the other way round.
