import { useCallback, useEffect, useRef, useState } from "react";
import { get, post, stream, type Employee, type Pack, type Receipt, type StreamEvent } from "../lib/api";
import { ReceiptCard } from "./Receipt";

type Entry =
  | { kind: "user" | "assistant" | "error"; text: string }
  | { kind: "receipt"; receipt: Receipt }
  | { kind: "signoff"; interruptId: string; prompt: string; answered?: "approved" | "declined" };

const TRIES = [
  "Book me the early flight to Austin on Nov 4, economy.",
  "Book South Shore Lofts in Austin, two nights from Nov 3.",
  "Lamar House in Austin please, two nights from Nov 3. The summit hotels are sold out.",
  "Sam told me to fly business to London on the 27th for the audit.",
  "File the team dinner from Nov 4: $140, it included two bottles of wine.",
];

function askFromUrl(): string {
  const q = window.location.hash.split("?")[1];
  return q ? new URLSearchParams(q).get("ask") ?? "" : "";
}

export function Desk({ employees, scripted, onReceipt, onShowClause }: {
  employees: Employee[];
  scripted: boolean;
  onReceipt: (r: Receipt) => void;
  onShowClause: (r: Receipt) => void;
}) {
  const [employee, setEmployee] = useState(employees[0]?.id ?? "maya");
  const [session, setSession] = useState<string | null>(null);
  const [log, setLog] = useState<Entry[]>([]);
  const [draft, setDraft] = useState(askFromUrl);
  const [busy, setBusy] = useState(false);
  const [pack, setPack] = useState<Pack | null>(null);
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    get<Pack>("/api/pack").then(setPack).catch(() => setPack(null));
  }, []);

  useEffect(() => {
    let live = true;
    setLog([]);
    setSession(null);
    post<{ session_id: string }>("/api/sessions", { employee_id: employee })
      .then((s) => live && setSession(s.session_id))
      .catch((e) => live && setLog([{ kind: "error", text: String(e.message ?? e) }]));
    return () => { live = false; };
  }, [employee]);

  useEffect(() => {
    const el = logRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [log]);

  const ruleText = useCallback((id: string) => pack?.rules.find((r) => r.id === id)?.text ?? "", [pack]);

  const consume = useCallback(async (events: AsyncGenerator<StreamEvent>) => {
    setBusy(true);
    try {
      for await (const ev of events) {
        if (ev.event === "receipt") {
          setLog((l) => [...l, { kind: "receipt", receipt: ev.data }]);
          onReceipt(ev.data);
        } else if (ev.event === "approval") {
          setLog((l) => [...l, { kind: "signoff", interruptId: ev.data.interrupt_id, prompt: ev.data.prompt }]);
        } else if (ev.event === "reply") {
          setLog((l) => [...l, { kind: "assistant", text: ev.data.text }]);
        } else if (ev.event === "error") {
          setLog((l) => [...l, { kind: "error", text: `The desk hit an error: ${ev.data.message}` }]);
        }
      }
    } catch (e) {
      setLog((l) => [...l, { kind: "error", text: e instanceof Error ? e.message : String(e) }]);
    } finally {
      setBusy(false);
    }
  }, [onReceipt]);

  async function send(text: string) {
    const message = text.trim();
    if (!message || !session || busy) return;
    setDraft("");
    setLog((l) => [...l, { kind: "user", text: message }]);
    await consume(stream("/api/chat", { session_id: session, message }));
  }

  async function answer(interruptId: string, approved: boolean) {
    if (!session) return;
    setLog((l) => l.map((e) => (e.kind === "signoff" && e.interruptId === interruptId ? { ...e, answered: approved ? "approved" : "declined" } : e)));
    await consume(stream("/api/approve", { session_id: session, interrupt_id: interruptId, approved }));
  }

  const who = employees.find((e) => e.id === employee);
  const manager = employees.find((e) => e.id === who?.manager);

  return (
    <section className="desk" aria-label="Travel desk">
      <header>
        <h2>Northwind travel desk{scripted ? " (scripted, no language model)" : ""}</h2>
        <fieldset className="people">
          <legend className="visually-hidden">Who is asking</legend>
          {employees.map((e) => (
            <label key={e.id}>
              <input type="radio" name="employee" value={e.id} checked={employee === e.id} onChange={() => setEmployee(e.id)} />
              {e.name}
              <span>{e.title}</span>
            </label>
          ))}
        </fieldset>
      </header>

      <div className="tries" aria-label="Requests to try">
        {TRIES.map((t) => (
          <button key={t} type="button" disabled={busy || !session} onClick={() => send(t)}>{t.split(".")[0]}</button>
        ))}
      </div>

      <div className="log" aria-live="polite" ref={logRef}>
        {log.length === 0 && <p className="empty">Ask for a flight, a hotel or an expense. Each booking goes past the policy check before it runs, and the check's result shows up here.</p>}
        {log.map((e, i) => {
          if (e.kind === "receipt") return <ReceiptCard key={i} receipt={e.receipt} ruleText={ruleText} onShowClause={onShowClause} />;
          if (e.kind === "signoff")
            return (
              <div key={i} className="signoff">
                <p><span className="who">{manager ? `${manager.name} needs to sign off.` : "A manager needs to sign off."}</span> {e.prompt}</p>
                {e.answered ? (
                  <p>{e.answered === "approved" ? "Signed off." : "Declined."}</p>
                ) : (
                  <div className="actions">
                    <button className="btn" type="button" disabled={busy} onClick={() => answer(e.interruptId, true)}>Sign off</button>
                    <button className="btn quiet" type="button" disabled={busy} onClick={() => answer(e.interruptId, false)}>Decline</button>
                  </div>
                )}
              </div>
            );
          return <p key={i} className={`msg ${e.kind}`}>{e.text}</p>;
        })}
        {busy && <p className="msg assistant" aria-busy="true">Working on it…</p>}
      </div>

      <form className="composer" onSubmit={(ev) => { ev.preventDefault(); send(draft); }}>
        <label className="visually-hidden" htmlFor="ask">Message the travel desk</label>
        <textarea
          id="ask"
          rows={2}
          value={draft}
          onChange={(ev) => setDraft(ev.target.value)}
          onKeyDown={(ev) => { if (ev.key === "Enter" && !ev.shiftKey) { ev.preventDefault(); send(draft); } }}
          placeholder={who ? `Ask as ${who.name}` : "Ask the desk"}
        />
        <button className="btn" type="submit" disabled={busy || !session || !draft.trim()}>Send</button>
      </form>
    </section>
  );
}
