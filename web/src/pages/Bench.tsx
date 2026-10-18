import { useEffect, useState } from "react";
import { get, NotFound, type BenchSummary, type SplitCounts, type SystemSummary } from "../lib/api";
import { ms, pct, systemName } from "../lib/format";

const OURS = "var(--series-ours)";
const THEIRS = "var(--series-theirs)";
const ours = (system: string) => system.startsWith("bylaw");

type Row = { system: string; s: SystemSummary };

function Tip({ tip }: { tip: { x: number; y: number; text: string } | null }) {
  if (!tip) return null;
  return <div className="tip" style={{ left: tip.x, top: tip.y }} role="status">{tip.text}</div>;
}

/** Horizontal bars, one per system, labelled at the bar. Optional 95% whiskers. */
function BarChart({ rows, value, ci, format, log = false, caption, note }: {
  rows: Row[];
  value: (s: SystemSummary) => number | null;
  ci?: (s: SystemSummary) => [number, number];
  format: (v: number) => string;
  log?: boolean;
  caption: string;
  note: string;
}) {
  const [tip, setTip] = useState<{ x: number; y: number; text: string } | null>(null);
  const shown = rows.filter((r) => value(r.s) !== null);
  const vals = shown.map((r) => value(r.s)!);
  const max = Math.max(...vals, ...(ci ? shown.map((r) => ci(r.s)[1]) : []), log ? 1 : 0.0001);
  const min = log ? Math.max(Math.min(...vals) / 2, 1e-4) : 0;
  const W = 460, label = 170, rowH = 30, H = shown.length * rowH + 24;
  const x = (v: number) => label + (log ? (Math.log10(Math.max(v, min)) - Math.log10(min)) / (Math.log10(max) - Math.log10(min) || 1) : v / max) * (W - label - 60);

  return (
    <figure className="chart" onMouseLeave={() => setTip(null)}>
      <figcaption>{caption}</figcaption>
      <div className="chart-wrap">
        <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${caption}. ${shown.map((r) => `${systemName(r.system)} ${format(value(r.s)!)}`).join("; ")}`}>
          <line className="axis" x1={label} x2={label} y1={0} y2={H - 20} />
          {shown.map((r, i) => {
            const v = value(r.s)!;
            const y = i * rowH + 6;
            const end = Math.max(x(v), label + 3);
            return (
              <g key={r.system}
                 onMouseMove={(e) => setTip({ x: e.nativeEvent.offsetX + 12, y: e.nativeEvent.offsetY - 8, text: `${systemName(r.system)}: ${format(v)}${ci ? ` (95% CI ${format(ci(r.s)[0])} to ${format(ci(r.s)[1])})` : ""}` })}>
                <rect x={0} y={y - 4} width={W} height={rowH} fill="transparent" />
                <text x={label - 8} y={y + 12} textAnchor="end">{systemName(r.system)}</text>
                <rect x={label} y={y + 2} width={end - label} height={14} rx={4} fill={ours(r.system) ? OURS : THEIRS} />
                {ci && (() => {
                  const [lo, hi] = ci(r.s);
                  return <line x1={x(lo)} x2={x(hi)} y1={y + 9} y2={y + 9} stroke="var(--ink)" strokeWidth={1.5} />;
                })()}
                <text x={Math.max(end, ci ? x(ci(r.s)[1]) : end) + 6} y={y + 13} className="val">{format(v)}</text>
              </g>
            );
          })}
        </svg>
        <Tip tip={tip} />
      </div>
      <p>{note}</p>
    </figure>
  );
}

function RiskCoverage({ rows }: { rows: Row[] }) {
  const [tip, setTip] = useState<{ x: number; y: number; text: string } | null>(null);
  const W = 460, H = 300, L = 44, B = 32, T = 10, R = 130;
  const px = (c: number) => L + c * (W - L - R);
  const lo = Math.min(...rows.flatMap((r) => r.s.risk_coverage.map(([, a]) => a)), 0.5);
  const py = (a: number) => T + (1 - (a - lo) / (1 - lo || 1)) * (H - T - B);
  return (
    <figure className="chart" onMouseLeave={() => setTip(null)}>
      <figcaption>Accuracy when each system keeps only its most confident answers</figcaption>
      <div className="chart-wrap">
        <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Risk and coverage curves for each system">
          {[0, 0.25, 0.5, 0.75, 1].map((c) => (
            <g key={c}>
              <line className="grid" x1={px(c)} x2={px(c)} y1={T} y2={H - B} />
              <text x={px(c)} y={H - B + 16} textAnchor="middle">{pct(c)}</text>
            </g>
          ))}
          {[lo, (lo + 1) / 2, 1].map((a) => <text key={a} x={L - 6} y={py(a) + 4} textAnchor="end">{pct(a)}</text>)}
          <text x={px(0.5)} y={H - 2} textAnchor="middle">share of cases answered, most confident first</text>
          {rows.map((r) => {
            const pts = r.s.risk_coverage;
            if (!pts.length) return null;
            const last = pts[pts.length - 1];
            return (
              <g key={r.system}>
                <polyline fill="none" stroke={ours(r.system) ? OURS : THEIRS} strokeWidth={ours(r.system) ? 2.5 : 1.5}
                          strokeLinejoin="round" points={pts.map(([c, a]) => `${px(c)},${py(a)}`).join(" ")} />
                {pts.map(([c, a], i) => (
                  <circle key={i} cx={px(c)} cy={py(a)} r={7} fill="transparent"
                          onMouseMove={(e) => setTip({ x: e.nativeEvent.offsetX + 12, y: e.nativeEvent.offsetY - 8, text: `${systemName(r.system)}: ${pct(a)} right on the top ${pct(c)}` })} />
                ))}
                <text x={px(last[0]) + 8} y={py(last[1]) + 4} className="val">{systemName(r.system)}</text>
              </g>
            );
          })}
        </svg>
        <Tip tip={tip} />
      </div>
      <p>A system whose confidence means something stays accurate on the left of this chart. That is what lets Bylaw hand only its unsure cases to a person.</p>
    </figure>
  );
}

const frac = (a: number, b: number) => `${a} of ${b}`;

/** The same results, split by where each case's label came from. */
function Split({ groups }: { groups: { name: string; systems: Record<string, SplitCounts> }[] }) {
  return (
    <section aria-labelledby="split-h">
      <h2 id="split-h">Where the labels came from</h2>
      <p className="lede">
        DeepSeek wrote 152 cases from the policy alone. On review I kept 97 of its labels and corrected 55, most of them breaches it
        had missed: a trip passing $3,000 with no recorded approval, a booking inside 14 days with no reason. I wrote the other 45.
        On the 97 untouched cases the Bedrock models get more verdicts exactly right; across every group, the hand-written pack lets
        no breach through.
      </p>
      {groups.map((g) => {
        const rows = Object.entries(g.systems);
        const n = rows[0]?.[1].n ?? 0;
        return (
          <table className="results" key={g.name}>
            <caption>{g.name}, {n} cases</caption>
            <thead>
              <tr><th scope="col">System</th><th scope="col">Right verdict</th><th scope="col">Let a breach through</th><th scope="col">Talked into a breach</th><th scope="col">Clean cases sent to a person</th></tr>
            </thead>
            <tbody>
              {rows.map(([system, t]) => (
                <tr key={system} className={system.startsWith("Bylaw") ? "ours" : ""}>
                  <td>{system.replace(/^us\.amazon\./, "").replace(/-v\d+:\d+/, "").replace(/^mistral\./, "")}</td>
                  <td>{pct(t.right / t.n)}</td>
                  <td>{frac(t.through, t.breaches)}</td>
                  <td>{frac(t.talked_past, t.manip)}</td>
                  <td>{frac(t.clean_to_person, t.clean)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        );
      })}
    </section>
  );
}

export function Bench() {
  const [data, setData] = useState<BenchSummary | null>(null);
  const [missing, setMissing] = useState(false);

  useEffect(() => {
    get<BenchSummary>("/api/bench").then(setData).catch((e) => setMissing(e instanceof NotFound));
  }, []);

  if (missing)
    return (
      <main className="bench">
        <h1>No benchmark results yet</h1>
        <p className="lede">Run <code>bylaw bench</code>. Its summary.json shows up here, and every number on this page comes from that file.</p>
      </main>
    );
  if (!data) return <main className="bench"><p className="lede">Loading results…</p></main>;

  const rows: Row[] = Object.entries(data.systems).map(([system, s]) => ({ system, s }));
  const env = data.env as Record<string, unknown>;
  const decider = (env.decider ?? {}) as Record<string, unknown>;
  const hasLlms = rows.some((r) => !ours(r.system));

  return (
    <main className="bench">
      <h1>{data.n_cases} held-out cases, decided by Bylaw{hasLlms ? " and by Bedrock models reading the policy" : ""}</h1>
      <p className="lede">
        Every system saw the same rendered state for each case, and none of it was used to tune the compiled pack. One person wrote the
        hand-written pack, 45 of the cases and every label correction, so read the split below before the pooled numbers. A model
        that never produced a usable answer is counted as wrong.
        {!hasLlms && " This run has no Bedrock rows: it was scored without language models."}
      </p>

      <h2>Results</h2>
      <table className="results">
        <thead>
          <tr><th scope="col">System</th><th scope="col">Accuracy</th><th scope="col">Let a breach through</th><th scope="col">Macro-F1</th><th scope="col">Calibration error</th><th scope="col">p50</th><th scope="col">p95</th><th scope="col">$ per 1,000</th><th scope="col">No answer</th></tr>
        </thead>
        <tbody>
          {rows.map(({ system, s }) => (
            <tr key={system} className={ours(system) ? "ours" : ""}>
              <td>{systemName(system)}</td>
              <td>{pct(s.accuracy)} <span className="ci">{pct(s.accuracy_ci[0])} to {pct(s.accuracy_ci[1])}</span></td>
              <td>{pct(s.false_proceed)}</td>
              <td>{s.macro_f1.toFixed(2)}</td>
              <td>{s.ece.toFixed(3)}</td>
              <td>{ms(s.latency.p50)}</td>
              <td>{ms(s.latency.p95)}</td>
              <td>{s.usd_per_1k ? `$${s.usd_per_1k.toFixed(3)}` : "not priced"}</td>
              <td>{s.abstains}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {data.hybrid && (
        <p className="lede">With Bedrock as the fallback, Decider settled {pct(data.hybrid.coverage)} of cases on its own and passed {data.hybrid.escalated} to the model.</p>
      )}

      <h2>How they compare</h2>
      {hasLlms && <p className="legend"><span className="swatch" style={{ background: OURS }} /> Bylaw <span className="swatch" style={{ background: THEIRS }} /> a Bedrock model deciding alone</p>}
      <div className="charts">
        <BarChart rows={rows} value={(s) => s.accuracy} ci={(s) => s.accuracy_ci} format={pct} caption="Right verdict"
                  note="Share of cases where the system chose the action the policy requires. Lines show the 95% bootstrap interval." />
        <BarChart rows={rows} value={(s) => s.false_proceed} ci={(s) => s.false_proceed_ci} format={pct} caption="Let a breach through"
                  note="Of the cases that should have been stopped, the share that would have gone ahead anyway. Lower is better." />
        <BarChart rows={rows} value={(s) => s.latency.p50} format={(v) => ms(v)} log caption="Time to decide, median"
                  note="Per decision. Log scale. Bylaw's time is the Decider call plus the code checks." />
        {rows.some((r) => r.s.usd_per_1k > 0) && <BarChart rows={rows.filter((r) => r.s.usd_per_1k > 0)} value={(s) => s.usd_per_1k} format={(v) => `$${v.toFixed(3)}`} log
                  caption="Cost per 1,000 decisions"
                  note="Bedrock at on-demand token prices; Bylaw at the instance's hourly price spread over measured decision time, as if it were busy all the time." />}
        {rows.some((r) => r.s.risk_coverage.length) && <RiskCoverage rows={rows} />}
      </div>

      {data.split && <Split groups={data.split.groups} />}

      <p className="env">
        Pack {data.pack_hash}. Decider {String(decider.checkpoint ?? "?")} on {String(decider.device ?? "?")}, {String(env.instance ?? "unknown machine")}.
        {env.git_sha ? ` Code ${String(env.git_sha)}.` : ""} {env.date ? `Run ${String(env.date)}.` : ""}
      </p>
    </main>
  );
}
