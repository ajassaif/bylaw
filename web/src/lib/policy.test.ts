import { describe, expect, it } from "vitest";
import { inline, parsePolicy } from "./policy";

const MD = `# Northwind Supply Co. — Travel and Expense Policy

Version 4.2 · Owner: Finance Operations

This policy covers business travel.

## 3. Hotels

**3.1 Nightly caps.** The most Northwind pays per night depends on the city:

| City tier | Nightly cap |
|---|---|
| A | $260 |
| B | $190 |

**3.2 Going over the cap.** You may go up to 10% over.

---

Questions go to finance.`;

describe("parsePolicy", () => {
  const doc = parsePolicy(MD);

  it("reads the title and the preamble", () => {
    expect(doc.title).toBe("Northwind Supply Co. — Travel and Expense Policy");
    expect(doc.preamble).toEqual(["Version 4.2 · Owner: Finance Operations", "This policy covers business travel."]);
  });

  it("groups clauses under sections and attaches tables to the clause above", () => {
    expect(doc.sections).toHaveLength(1);
    const [s] = doc.sections;
    expect(s.heading).toBe("3. Hotels");
    expect(s.clauses.map((c) => c.id)).toEqual(["3.1", "3.2"]);
    expect(s.clauses[0].title).toBe("Nightly caps.");
    expect(s.clauses[0].body).toEqual(["The most Northwind pays per night depends on the city:"]);
    expect(s.clauses[0].tables[0]).toEqual({ head: ["City tier", "Nightly cap"], rows: [["A", "$260"], ["B", "$190"]] });
  });

  it("keeps the closing note", () => {
    expect(doc.closing).toEqual(["Questions go to finance."]);
  });

  it("splits bold runs for inline rendering", () => {
    expect(inline("Plain **bold** end")).toEqual([
      { text: "Plain ", bold: false },
      { text: "bold", bold: true },
      { text: " end", bold: false },
    ]);
  });
});
