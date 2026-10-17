import { describe, expect, it } from "vitest";
import { clauseOf, ms, pct, verdictMark } from "./format";

describe("format", () => {
  it("pct rounds to a whole percent", () => {
    expect(pct(0.913)).toBe("91%");
    expect(pct(0.0049)).toBe("0%");
    expect(pct(1)).toBe("100%");
  });

  it("ms switches to seconds at one second", () => {
    expect(ms(183.6)).toBe("184 ms");
    expect(ms(1600)).toBe("1.6 s");
    expect(ms(null)).toBe("");
  });

  it("verdictMark names each action in plain words", () => {
    expect(verdictMark("proceed")).toEqual({ label: "cleared", tone: "cleared" });
    expect(verdictMark("guide")).toEqual({ label: "sent back", tone: "sent-back" });
    expect(verdictMark("confirm")).toEqual({ label: "needs sign-off", tone: "sign-off" });
    expect(verdictMark("deny")).toEqual({ label: "refused", tone: "refused" });
  });

  it("clauseOf finds the clause number a rule quotes", () => {
    expect(clauseOf("3.2 Going over the cap.")).toBe("3.2");
    expect(clauseOf("Hotels must follow 4.3 and 4.4")).toBe("4.3");
    expect(clauseOf("no number")).toBeNull();
  });
});
