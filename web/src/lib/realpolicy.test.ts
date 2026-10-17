import { readFileSync } from "node:fs";
import { expect, it } from "vitest";
import { parsePolicy } from "./policy";

it("parses every clause of the real Northwind policy", () => {
  const doc = parsePolicy(readFileSync("../policies/northwind-travel.md", "utf8"));
  const ids = doc.sections.flatMap((s) => s.clauses.map((c) => c.id));
  expect(ids).toEqual(["1.1", "1.2", "2.1", "2.2", "3.1", "3.2", "3.3", "4.1", "4.2", "4.3", "4.4", "5.1", "5.2", "5.3", "5.4", "6.1", "6.2"]);
  expect(doc.closing[0]).toMatch(/^Questions about this policy/);
});
