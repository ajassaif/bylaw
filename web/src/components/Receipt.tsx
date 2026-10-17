import type { Receipt } from "../lib/api";
import { clauseOf, ms, pct, verdictMark } from "../lib/format";

function summary(r: Receipt): string {
  const a = r.args as Record<string, unknown>;
  if (r.tool === "book_flight") return `${a.flight_id} in ${String(a.cabin ?? "").replace(/_/g, " ")}`;
  if (r.tool === "book_hotel") return `${a.hotel_id}, ${a.nights} nights from ${a.check_in}`;
  if (r.tool === "submit_expense") return `${String(a.category ?? "").replace(/_/g, " ")} expense, $${a.amount_usd}`;
  return JSON.stringify(a);
}

export function ReceiptCard({ receipt, ruleText, onShowClause }: { receipt: Receipt; ruleText: (id: string) => string; onShowClause: (r: Receipt) => void }) {
  const verdict = receipt.escalation ?? receipt.verdict;
  const mark = verdictMark(verdict.action);
  const questions = receipt.verdict.findings.filter((f) => f.source === "decider");
  const failedChecks = receipt.verdict.findings.filter((f) => f.source === "check" && f.status !== "clear");
  const clause = verdict.rule_id ? clauseOf(ruleText(verdict.rule_id)) : null;

  return (
    <div className={`receipt tone-${mark.tone}`}>
      <div className="head">
        <span className="verdict">{mark.label}</span>
        <span className="call">{receipt.tool.replace(/_/g, " ")}: {summary(receipt)}</span>
      </div>
      {verdict.message && <p className="why">{verdict.message}</p>}
      {receipt.escalated && <p className="why">Decider wasn't sure, so a Bedrock model made this call.</p>}
      {receipt.error && <p className="why">{receipt.error}</p>}
      {(questions.length > 0 || failedChecks.length > 0) && (
        <table>
          <tbody>
            {failedChecks.map((f) => (
              <tr key={f.item_id}>
                <td className="name">{f.item_id.replace(/_/g, " ")}</td>
                <td>{f.status === "violation" ? "breached in code" : "couldn't be checked"}</td>
                <td className="p" />
              </tr>
            ))}
            {questions.map((f) => (
              <tr key={f.item_id}>
                <td className="name">{f.item_id.replace(/_/g, " ")}</td>
                <td>
                  <div className={`bar ${f.status}`} role="img" aria-label={`${pct(f.p_violation ?? 0)} likely breached, ${f.status}`}>
                    <i style={{ width: `${Math.round((f.p_violation ?? 0) * 100)}%` }} />
                  </div>
                </td>
                <td className="p">{f.p_violation === null ? "" : pct(f.p_violation)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <div className="foot">
        <span>
          {receipt.decider_ms !== null ? `Decider answered in ${ms(receipt.decider_ms)}` : "No Decider call"}, pack {receipt.pack_hash.slice(0, 6)}
        </span>
        {clause && <button type="button" onClick={() => onShowClause(receipt)}>Show clause {clause}</button>}
      </div>
    </div>
  );
}
