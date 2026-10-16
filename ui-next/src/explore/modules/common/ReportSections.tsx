import { useMemo, useState } from 'react';
import { Chip, SegmentedControl, Stack } from '@aunoo/ui';
import { Markdown } from '../../../shell/Markdown';
import './common.css';

/*
 * An AI report shown as coloured section cards, as the old Insights tabs did: the report is split on
 * its headings (#, ##, a bold line on its own, or a known "Title:" line), and each section gets a card
 * whose colour follows its subject (summary blue, threats amber, risk and priorities red, outlook and
 * recommendations green). A jump list sits on top. "Plain text" shows the report as it was written,
 * and a report with fewer than two sections is always shown plain.
 */

export interface ReportSection { title: string; content: string }
type Tone = 'info' | 'warning' | 'error' | 'success' | 'accent' | 'neutral';

const KNOWN = [
  'executive summary', 'summary', 'overview', 'key findings', 'trend analysis', 'thematic spotlight', 'escalation assessment',
  'forward-looking insights', 'forward looking insights', 'forward-looking concerns', 'institutional targets', 'key actors',
  'geographic focus', 'regional analysis', 'emerging threats', 'strategic outlook', 'outlook', 'priority areas', 'risk assessment',
  'recommendations', 'watchlist', 'threat landscape', 'notable incidents', 'indicators', 'funding trends', 'research priorities',
  'policy implications', 'conclusion', 'methodology',
];

const TONES: [RegExp, Tone][] = [
  [/summary|overview|key findings|conclusion|methodology/i, 'info'],
  [/risk|priorit|escalat|critical|target/i, 'error'],
  [/threat|concern|watch|incident|indicator/i, 'warning'],
  [/outlook|forward|recommend|opportunit|implication|next/i, 'success'],
  [/actor|region|geograph|institution|theme|trend|spotlight|funding|research/i, 'accent'],
];
const toneOf = (title: string): Tone => TONES.find(([re]) => re.test(title))?.[1] ?? 'neutral';
const clean = (s: string) => s.replace(/\*\*/g, '').replace(/:$/, '').trim();
const isKnown = (t: string) => KNOWN.some((k) => t.toLowerCase().includes(k) || k.includes(t.toLowerCase()));

/** Splits a Markdown report into titled sections; text before the first heading becomes "Overview" */
export function parseSections(md: string): ReportSection[] {
  const out: ReportSection[] = [];
  let title = '';
  let buf: string[] = [];
  const flush = () => {
    const content = buf.join('\n').trim();
    if (content || title) out.push({ title: title || 'Overview', content });
    buf = [];
  };
  for (const line of md.split('\n')) {
    const t = line.trim();
    let head: string | null = null;
    const h = t.match(/^#{1,3}\s+(.+)$/);
    if (h) head = clean(h[1]);
    else if (/^\*\*[^*]+\*\*:?$/.test(t) && isKnown(clean(t))) head = clean(t);
    else if (t.endsWith(':') && !t.includes('.') && t.length < 50 && isKnown(clean(t))) head = clean(t);
    if (head) {
      flush();
      title = head;
    } else buf.push(line);
  }
  flush();
  // A lone title line (e.g. "# Weekly briefing") with nothing under it isn't a section
  return out.filter((s) => s.content);
}

export function ReportSections({ markdown, sections: given, idPrefix = 'report' }: {
  markdown?: string;
  /** Already-split sections (a report stored field by field); used instead of parsing */
  sections?: ReportSection[];
  idPrefix?: string;
}) {
  const sections = useMemo(() => (given?.length ? given.filter((s) => s.content?.trim()) : parseSections(markdown ?? '')), [given, markdown]);
  const [mode, setMode] = useState<'cards' | 'plain'>('cards');
  const plainText = markdown ?? sections.map((s) => `## ${s.title}\n\n${s.content}`).join('\n\n');
  if (sections.length < 2) return <Markdown text={plainText} />;

  return (
    <Stack gap="md">
      <Stack direction="row" justify="between" gap="sm">
        <SegmentedControl label="Show the report as" options={[{ value: 'cards', label: 'Sections' }, { value: 'plain', label: 'Plain text' }]} value={mode} onValueChange={(v) => setMode(v as 'cards' | 'plain')} />
      </Stack>
      {mode === 'plain' ? <Markdown text={plainText} /> : (
        <>
          <Stack direction="row" gap="sm">
            {sections.map((s, i) => (
              <Chip key={i} tone="neutral" variant="outline" size="sm" label={`Jump to ${s.title}`} onClick={() => document.getElementById(`${idPrefix}-section-${i}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })}>
                {s.title}
              </Chip>
            ))}
          </Stack>
          <Stack gap="md">
            {sections.map((s, i) => (
              <section key={i} id={`${idPrefix}-section-${i}`} className={`report-card report-card--${toneOf(s.title)}`} aria-labelledby={`${idPrefix}-section-${i}-h`}>
                <h3 id={`${idPrefix}-section-${i}-h`} className="report-card__title">{s.title}</h3>
                <Markdown text={s.content} />
              </section>
            ))}
          </Stack>
        </>
      )}
    </Stack>
  );
}
