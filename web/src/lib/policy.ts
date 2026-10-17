/** Just enough markdown for the policy document: headings, clause paragraphs, tables, a rule. */

export type Table = { head: string[]; rows: string[][] };
export type Clause = { id: string; title: string; body: string[]; tables: Table[] };
export type Section = { heading: string; clauses: Clause[]; notes: string[] };
export type PolicyDoc = { title: string; preamble: string[]; sections: Section[]; closing: string[] };

const CLAUSE = /^\*\*(\d+\.\d+)\s+(.+?)\*\*\s*(.*)$/;

function cells(line: string): string[] {
  return line.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
}

export function parsePolicy(md: string): PolicyDoc {
  const doc: PolicyDoc = { title: "", preamble: [], sections: [], closing: [] };
  const blocks = md.replace(/\r\n/g, "\n").split(/\n\s*\n/).map((b) => b.trim()).filter(Boolean);
  let section: Section | null = null;
  let afterRule = false;

  for (const block of blocks) {
    if (block.startsWith("# ")) {
      doc.title = block.slice(2).trim();
    } else if (block.startsWith("## ")) {
      section = { heading: block.slice(3).trim(), clauses: [], notes: [] };
      doc.sections.push(section);
    } else if (/^-{3,}$/.test(block)) {
      afterRule = true;
    } else if (afterRule) {
      doc.closing.push(block);
    } else if (block.startsWith("|")) {
      const lines = block.split("\n").filter((l) => !/^\|?\s*-{3}/.test(l.trim()));
      const table = { head: cells(lines[0]), rows: lines.slice(1).map(cells) };
      section?.clauses.at(-1)?.tables.push(table);
    } else if (section) {
      const text = block.replace(/\s*\n\s*/g, " ");
      const m = text.match(CLAUSE);
      if (m) section.clauses.push({ id: m[1], title: m[2].trim(), body: m[3] ? [m[3]] : [], tables: [] });
      else if (section.clauses.length) section.clauses.at(-1)!.body.push(text);
      else section.notes.push(text);
    } else {
      doc.preamble.push(block.replace(/\s*\n\s*/g, " "));
    }
  }
  return doc;
}

export type Run = { text: string; bold: boolean };

export function inline(text: string): Run[] {
  return text
    .split(/(\*\*[^*]+\*\*)/)
    .filter(Boolean)
    .map((part) => (part.startsWith("**") ? { text: part.slice(2, -2), bold: true } : { text: part, bold: false }));
}
