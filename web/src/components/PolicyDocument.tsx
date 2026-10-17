import { useEffect, useMemo, useRef } from "react";
import type { Finding, Pack, Question, Receipt, Rule } from "../lib/api";
import { clauseOf, pct, verdictMark } from "../lib/format";
import { inline, type Clause, type PolicyDoc } from "../lib/policy";

function Inline({ text }: { text: string }) {
  return (
    <>
      {inline(text).map((run, i) => (run.bold ? <strong key={i}>{run.text}</strong> : <span key={i}>{run.text}</span>))}
    </>
  );
}

function options(q: Question): string | null {
  if (Array.isArray(q.criteria)) return q.criteria.join(", then ");
  if (q.type === "choice" && q.criteria) return Object.keys(q.criteria).map((k) => k.replace(/_/g, " ")).join(", ");
  return null;
}

function LiveLine({ finding, tone }: { finding: Finding | undefined; tone: string }) {
  if (!finding) return null;
  const p = finding.p_violation;
  const text =
    finding.status === "violation" ? `breached${p !== null && finding.source === "decider" ? `, p ${pct(p)}` : ""}`
    : finding.status === "clear" ? `clear${p !== null && finding.source === "decider" ? `, p ${pct(p)}` : ""}`
    : finding.source === "check" ? "couldn't be checked from what's there" : `unsure, p ${pct(p ?? 0.5)}`;
  return <span className={`live ${finding.status}`} style={{ ["--tone" as string]: `var(--${tone})` }}>{text}</span>;
}

function Note({ rules, pack, findings, tone }: { rules: Rule[]; pack: Pack; findings: Map<string, Finding>; tone: string }) {
  if (!rules.length) return <aside className="note" />;
  const items = rules.flatMap((r) => [
    ...pack.checks.filter((c) => c.rule_id === r.id).map((c) => (
      <li key={c.id}>
        <span className="kind">code check</span> {c.description}
        <LiveLine finding={findings.get(c.id)} tone={tone} />
      </li>
    )),
    ...pack.questions.filter((q) => q.rule_id === r.id).map((q) => (
      <li key={q.id}>
        <span className="kind">asks Decider</span> <span className="q">{q.instructions}</span>
        {options(q) && <span className="opts">{options(q)}</span>}
        {q.dev && <span className="opts">right on {pct(q.dev.accuracy)} of {q.dev.n} practice cases</span>}
        <LiveLine finding={findings.get(q.id)} tone={tone} />
      </li>
    )),
    ...rules.filter((r) => pack.unenforced?.[r.id]).map((r) => (
      <li key={`pulled-${r.id}`} className="pulled">
        <span className="kind">not enforced automatically</span> {pack.unenforced![r.id]}, so the compiler pulled it. A person has to watch for this.
      </li>
    )),
  ]);
  return (
    <aside className="note" aria-label="How this clause is enforced">
      <ul>{items}</ul>
    </aside>
  );
}

function ClauseRow({ clause, rules, pack, focus }: { clause: Clause; rules: Rule[]; pack: Pack; focus: Receipt | null }) {
  const ref = useRef<HTMLDivElement>(null);
  const verdict = focus ? (focus.escalation ?? focus.verdict) : null;
  const decided = !!verdict?.rule_id && rules.some((r) => r.id === verdict.rule_id);
  const touched = !!focus && rules.some((r) => focus.verdict.findings.some((f) => f.rule_id === r.id));
  const tone = verdict ? verdictMark(verdict.action).tone : "cleared";
  const findings = useMemo(() => new Map((touched ? focus!.verdict.findings : []).map((f) => [f.item_id, f])), [focus, touched]);

  useEffect(() => {
    if (decided) ref.current?.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "center" });
  }, [decided, focus]);

  return (
    <div ref={ref} id={`clause-${clause.id}`} className={`clause tone-${tone} ${decided ? "is-active" : ""}`}>
      <div className="clause-no">{clause.id}</div>
      <div className="clause-text">
        <p>
          <span className="mark-run">
            <strong>{clause.title}</strong> <Inline text={clause.body[0] ?? ""} />
          </span>
        </p>
        {clause.body.slice(1).map((b, i) => <p key={i}><Inline text={b} /></p>)}
        {clause.tables.map((t, i) => (
          <table key={i}>
            <thead><tr>{t.head.map((h) => <th key={h} scope="col">{h}</th>)}</tr></thead>
            <tbody>{t.rows.map((r, j) => <tr key={j}>{r.map((c, k) => <td key={k}>{c}</td>)}</tr>)}</tbody>
          </table>
        ))}
      </div>
      <Note rules={rules} pack={pack} findings={findings} tone={tone} />
    </div>
  );
}

export function PolicyDocument({ doc, pack, focus }: { doc: PolicyDoc; pack: Pack; focus: Receipt | null }) {
  const byClause = useMemo(() => {
    const map = new Map<string, Rule[]>();
    for (const r of pack.rules) {
      const id = clauseOf(r.text);
      if (id) map.set(id, [...(map.get(id) ?? []), r]);
    }
    return map;
  }, [pack]);

  return (
    <article className="ledger" aria-label="Policy document">
      <h1>{doc.title}</h1>
      {doc.preamble.map((p, i) => <p key={i} className="front"><Inline text={p} /></p>)}
      {doc.sections.map((s) => (
        <section key={s.heading} aria-label={s.heading}>
          <h2>{s.heading}</h2>
          {s.clauses.map((c) => <ClauseRow key={c.id} clause={c} rules={byClause.get(c.id) ?? []} pack={pack} focus={focus} />)}
        </section>
      ))}
      {doc.closing.map((p, i) => <p key={i} className="front"><Inline text={p} /></p>)}
    </article>
  );
}
