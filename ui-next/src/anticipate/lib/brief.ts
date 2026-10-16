/**
 * Reads the Situation Assessment brief's threat/opportunity and recommended-action sections into
 * structured items. The layout comes from the headings the synthesis prompt asks for
 * (data/auspex/agents/sio_synthesis_agent.md). When a section doesn't parse, it comes back as
 * plain Markdown, so wording drift loses the layout but never the content.
 */

export interface Field { label: string; value: string }
export interface Item { name: string; fields: Field[]; notes: string[] }
export interface Action { text: string; rationale?: string; owner?: string }
export interface ActionGroup { key: 'immediate' | 'near' | 'strategic'; title: string; timeframe: string; actions: Action[] }

export type Section =
  | { kind: 'markdown'; text: string }
  | { kind: 'threats'; title: string; threats: Item[]; opportunities: Item[] }
  | { kind: 'actions'; title: string; groups: ActionGroup[] };

const headingOf = (s: string, level: string) => s.match(new RegExp(`^${level} (.+?)\\s*$`, 'm'))?.[1] ?? '';
const subsections = (s: string) => s.split(/(?=^### )/m).filter((x) => x.startsWith('### '));
const stripMd = (s: string) => s.replace(/\*\*/g, '').replace(/^\*(.*)\*$/, '$1').trim();

/** Items headed `**THREAT 1: Name**` / `**OPPORTUNITY 2: Name**`, each followed by bullets. */
export function parseItems(text: string): Item[] {
  const parts = text.split(/^\s*\*\*(?:THREAT|OPPORTUNITY)\s*\d*\s*[:.-]?\s*(.+?)\*\*\s*$/gim);
  const items: Item[] = [];
  for (let i = 1; i < parts.length; i += 2) {
    const name = stripMd(parts[i] ?? '');
    if (!name) continue;
    const fields: Field[] = [];
    const notes: string[] = [];
    for (const raw of (parts[i + 1] ?? '').split('\n')) {
      const line = raw.trim();
      if (!/^[-*]\s+/.test(line)) continue;
      const body = line.replace(/^[-*]\s+/, '');
      // "**Likelihood:** High | **Impact:** Medium" holds two fields on one line
      const labelled = [...body.matchAll(/\*\*([^*:]+):\*\*\s*([^|]*)/g)];
      if (labelled.length) labelled.forEach((m) => fields.push({ label: m[1].trim(), value: stripMd(m[2]) }));
      else notes.push(stripMd(body));
    }
    items.push({ name, fields, notes });
  }
  return items;
}

const GROUPS: { key: ActionGroup['key']; title: string; timeframe: string; test: RegExp }[] = [
  { key: 'immediate', title: 'Immediate', timeframe: '0–48 hours', test: /immediate|0-48|48.hour|today|urgent/i },
  { key: 'near', title: 'Near-term', timeframe: '1–2 weeks', test: /near.term|short.term|1-2 week|week/i },
  { key: 'strategic', title: 'Strategic', timeframe: '1–3 months', test: /strategic|long.term|month|quarter/i },
];

/** `- [ ] **Action** - Rationale - Owner: Function`, with the box, bold and parts all optional. */
export function parseAction(line: string): Action | null {
  const m = line.trim().match(/^[-*]\s+(?:\[[ xX]?\]\s*)?(.+)$/);
  if (!m) return null;
  let body = m[1];
  const owner = body.match(/[-–—]?\s*Owner:\s*(.+?)\s*$/i);
  if (owner) body = body.slice(0, owner.index).trim();
  const bold = body.match(/^\*\*(.+?)\*\*\s*(?:[-–—:]\s*)?(.*)$/);
  const [text, rationale] = bold ? [bold[1], bold[2]] : body.split(/\s+[-–—]\s+/, 2);
  const clean = stripMd(text ?? '');
  if (!clean) return null;
  return { text: clean, rationale: stripMd(rationale ?? '').replace(/\s*[-–—]\s*$/, '') || undefined, owner: owner ? stripMd(owner[1]) : undefined };
}

export function parseActions(section: string): ActionGroup[] {
  const groups = GROUPS.map(({ key, title, timeframe }) => ({ key, title, timeframe, actions: [] as Action[] }));
  for (const sub of subsections(section)) {
    const head = headingOf(sub, '###');
    const at = GROUPS.findIndex((g) => g.test.test(head));
    if (at < 0) continue;
    const span = head.match(/\(([^)]+)\)/)?.[1];
    if (span) groups[at].timeframe = span.replace(/-/g, '–');
    for (const line of sub.split('\n').slice(1)) {
      const a = parseAction(line);
      if (a) groups[at].actions.push(a);
    }
  }
  return groups;
}

export function parseBrief(brief: string): Section[] {
  return brief.split(/(?=^## )/m).map((section): Section => {
    const head = headingOf(section, '##').toUpperCase();
    if (head.includes('THREAT') && head.includes('OPPORTUNIT')) {
      let threats: Item[] = [];
      let opportunities: Item[] = [];
      for (const sub of subsections(section)) {
        const h = headingOf(sub, '###');
        if (/threat/i.test(h)) threats = parseItems(sub);
        else if (/opportunit/i.test(h)) opportunities = parseItems(sub);
      }
      if (threats.length || opportunities.length) return { kind: 'threats', title: headingOf(section, '##'), threats, opportunities };
    }
    if (head.includes('RECOMMENDED ACTION') || head.includes('PRIORITY ACTION')) {
      const groups = parseActions(section);
      if (groups.some((g) => g.actions.length)) return { kind: 'actions', title: headingOf(section, '##'), groups };
    }
    return { kind: 'markdown', text: section };
  });
}
