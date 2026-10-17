export type Action = "proceed" | "guide" | "confirm" | "deny";
export type Tone = "cleared" | "sent-back" | "sign-off" | "refused";

export function pct(p: number): string {
  return `${Math.round(p * 100)}%`;
}

export function ms(n: number | null | undefined): string {
  if (n === null || n === undefined) return "";
  return n < 1000 ? `${Math.round(n)} ms` : `${(n / 1000).toFixed(1)} s`;
}

const MARKS: Record<Action, { label: string; tone: Tone }> = {
  proceed: { label: "cleared", tone: "cleared" },
  guide: { label: "sent back", tone: "sent-back" },
  confirm: { label: "needs sign-off", tone: "sign-off" },
  deny: { label: "refused", tone: "refused" },
};

export function verdictMark(action: Action): { label: string; tone: Tone } {
  return MARKS[action];
}

export function clauseOf(text: string): string | null {
  const m = text.match(/\b(\d+\.\d+)\b/);
  return m ? m[1] : null;
}
