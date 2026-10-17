import { useCallback, useEffect, useState } from "react";
import { Desk } from "./components/Desk";
import { PassGate } from "./components/PassGate";
import { PolicyDocument } from "./components/PolicyDocument";
import { get, Unauthorized, type Employee, type Health, type Pack, type Receipt } from "./lib/api";
import { parsePolicy, type PolicyDoc } from "./lib/policy";
import { Bench } from "./pages/Bench";

type Loaded = { doc: PolicyDoc; pack: Pack; employees: Employee[] };

function useRoute(): string {
  const [hash, setHash] = useState(() => window.location.hash || "#/");
  useEffect(() => {
    const on = () => setHash(window.location.hash || "#/");
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return hash.startsWith("#/bench") ? "bench" : "desk";
}

export default function App() {
  const route = useRoute();
  const [health, setHealth] = useState<Health | null>(null);
  const [data, setData] = useState<Loaded | null>(null);
  const [locked, setLocked] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [focus, setFocus] = useState<Receipt | null>(null);

  const load = useCallback(async () => {
    try {
      const [policy, pack, employees] = await Promise.all([
        get<{ title: string; markdown: string }>("/api/policy"),
        get<Pack>("/api/pack"),
        get<Employee[]>("/api/employees"),
      ]);
      setData({ doc: parsePolicy(policy.markdown), pack, employees });
      setLocked(false);
    } catch (e) {
      if (e instanceof Unauthorized) setLocked(true);
      else setError("The workbench couldn't reach its server. Check that bylaw serve is running, then reload.");
    }
  }, []);

  useEffect(() => {
    get<Health>("/api/health").then(setHealth).catch(() => setHealth(null));
    load();
  }, [load]);

  if (locked) return <PassGate onUnlock={load} />;

  const up = health?.decider?.status !== "down" && !!health;
  const scripted = health?.model?.startsWith("scripted");
  const counts = data ? `${data.pack.checks.length} code checks and ${data.pack.questions.length} Decider questions` : "";

  return (
    <>
      <header className="masthead">
        <p className="wordmark">Bylaw</p>
        <p className="about">
          {data ? `The Northwind travel and expense policy, compiled into ${counts}. Every booking the desk makes is checked against it first.` : "Loading the policy…"}
        </p>
        <span className={`status ${health ? (up ? "is-up" : "is-down") : ""}`}>
          <span className="dot" aria-hidden="true" />
          {health
            ? up
              ? `Decider on ${health.decider.device ?? "?"}${scripted ? ", scripted desk" : ""}`
              : "Decider offline"
            : "Checking the Decider"}
        </span>
        <nav aria-label="Pages">
          <a href="#/" aria-current={route === "desk" ? "page" : undefined}>Desk</a>
          <a href="#/bench" aria-current={route === "bench" ? "page" : undefined}>Benchmark</a>
        </nav>
      </header>

      {error && <p className="gate err" role="alert">{error}</p>}

      {route === "bench" ? (
        <Bench />
      ) : (
        data && (
          <main className="workbench">
            <PolicyDocument doc={data.doc} pack={data.pack} focus={focus} />
            <Desk employees={data.employees} scripted={!!scripted} onReceipt={setFocus} onShowClause={setFocus} />
          </main>
        )
      )}
    </>
  );
}
