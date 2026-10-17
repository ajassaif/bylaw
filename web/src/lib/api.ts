import type { Action } from "./format";

export type Rule = { id: string; text: string; tools: string[]; on_violation: Exclude<Action, "proceed">; remedy: string };
export type Check = { id: string; rule_id: string; expr: string; description: string; tools?: string[] | null };
export type Question = {
  id: string;
  rule_id: string;
  type: "noul" | "choice" | "score";
  instructions: string;
  criteria: Record<string, string | null> | string[] | null;
  lo: number;
  hi: number;
  when?: string | null;
  dev?: { n: number; accuracy: number; brier: number; candidates: number } | null;
};
export type Pack = { policy_title: string; hash: string; models: Record<string, string>; rules: Rule[]; checks: Check[]; questions: Question[] };
export type Finding = { rule_id: string; source: "check" | "decider"; item_id: string; p_violation: number | null; status: "violation" | "clear" | "uncertain" };
export type Verdict = { action: Action; rule_id: string | null; message: string; confidence: number; uncertain: boolean; findings: Finding[] };
export type Receipt = {
  tool: string;
  args: Record<string, unknown>;
  verdict: Verdict;
  decider_ms: number | null;
  total_ms: number;
  input_tokens: number;
  pack_hash: string;
  escalated: boolean;
  escalation: Verdict | null;
  error: string | null;
  at: string;
};
export type Employee = { id: string; name: string; title: string; level: string; manager?: string | null };
export type Health = { decider: { status?: string; device?: string; checkpoint?: string }; pack_hash: string; model: string };

export type SystemSummary = {
  n: number;
  accuracy: number;
  accuracy_ci: [number, number];
  macro_f1: number;
  false_proceed: number;
  false_proceed_ci: [number, number];
  ece: number;
  latency: { p50: number | null; p95: number | null; mean: number | null };
  usd_per_1k: number;
  abstains: number;
  manipulation_n: number;
  manipulation_accuracy: number | null;
  risk_coverage: [number, number][];
};
export type BenchSummary = {
  n_cases: number;
  pack_hash: string;
  systems: Record<string, SystemSummary>;
  hybrid: { model: string; coverage: number; escalated: number };
  env: Record<string, unknown>;
};

export type StreamEvent =
  | { event: "receipt"; data: Receipt }
  | { event: "approval"; data: { interrupt_id: string; prompt: string } }
  | { event: "reply"; data: { text: string } }
  | { event: "error"; data: { message: string } }
  | { event: "done"; data: Record<string, never> };

const PASS_KEY = "bylaw-pass";

export function getPass(): string {
  try {
    return sessionStorage.getItem(PASS_KEY) ?? "";
  } catch {
    return "";
  }
}

export function setPass(pass: string): void {
  try {
    sessionStorage.setItem(PASS_KEY, pass);
  } catch {
    /* private mode: the passcode lives only in memory for this page */
  }
  memoryPass = pass;
}

let memoryPass = "";
const headers = (): Record<string, string> => ({ "x-demo-pass": getPass() || memoryPass, "content-type": "application/json" });

export class Unauthorized extends Error {}
export class NotFound extends Error {}

async function check(r: Response): Promise<Response> {
  if (r.status === 401) throw new Unauthorized("passcode required");
  if (r.status === 404) throw new NotFound(await r.text());
  if (r.status === 429) throw new Error("Too many requests this minute. Wait a moment and try again.");
  if (!r.ok) throw new Error(`The server answered ${r.status}.`);
  return r;
}

export async function get<T>(path: string): Promise<T> {
  return (await check(await fetch(path, { headers: headers() }))).json();
}

export async function post<T>(path: string, body: unknown): Promise<T> {
  return (await check(await fetch(path, { method: "POST", headers: headers(), body: JSON.stringify(body) }))).json();
}

/** POST, then read Server-Sent Events off the response body as they arrive. */
export async function* stream(path: string, body: unknown): AsyncGenerator<StreamEvent> {
  const r = await check(await fetch(path, { method: "POST", headers: headers(), body: JSON.stringify(body) }));
  const reader = r.body!.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value;
    let cut: number;
    while ((cut = buffer.indexOf("\n\n")) !== -1) {
      const block = buffer.slice(0, cut);
      buffer = buffer.slice(cut + 2);
      const fields = Object.fromEntries(block.split("\n").map((line) => [line.slice(0, line.indexOf(": ")), line.slice(line.indexOf(": ") + 2)]));
      yield { event: fields.event, data: JSON.parse(fields.data) } as StreamEvent;
    }
  }
}
