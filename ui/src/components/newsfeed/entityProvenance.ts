/**
 * Pure helpers for showing where a value came from.
 *
 * These are separated from the panel that renders them because the decisions
 * are the interesting part and they are testable without a DOM: how a source
 * and date read as a label, when the imported baseline is worth flagging as
 * different, and which mentions may be counted toward sentiment.
 *
 * The last one matters most. A company's own posts are content about the
 * company but are not opinions of it, so they are aggregated separately and
 * never enter a net sentiment figure. Mentions nobody has evaluated are
 * counted apart too, rather than folded in as neutral — otherwise a page
 * reports a settled, balanced view assembled entirely from posts no one read.
 */

export const OWNED_CHANNELS = ['owned_web', 'owned_social'] as const;

export type FieldStatus = 'current' | 'stale' | 'conflict' | 'manual_override';

/** Sources whose readings are the company describing itself. */
const SELF_REPORTED = new Set([
  'vendor_web', 'linkedin_jobs', 'linkedin_company_profile', 'workbook',
  'manual',
]);

const SOURCE_LABELS: Record<string, string> = {
  workbook: 'imported workbook',
  manual: 'entered by an operator',
  linkedin_company_profile: 'LinkedIn company profile',
  linkedin_jobs: 'LinkedIn jobs',
  crunchbase_company: 'Crunchbase',
  pitchbook_company: 'PitchBook',
  zoominfo_company: 'ZoomInfo',
  vendor_web: "the vendor's own site",
};

export function sourceLabel(source: string): string {
  return SOURCE_LABELS[source] ?? source.replace(/_/g, ' ');
}

export function isSelfReported(source: string): boolean {
  return SELF_REPORTED.has(source);
}

/** "LinkedIn company profile, 14 Aug 2026" — never a bare number. */
export function provenanceLabel(source: string,
                                observedAt: string | null): string {
  const when = formatDay(observedAt);
  return when ? `${sourceLabel(source)}, ${when}` : sourceLabel(source);
}

export function formatDay(iso: string | null | undefined): string {
  if (!iso) return '';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleDateString(undefined, {
    day: 'numeric', month: 'short', year: 'numeric',
  });
}

/** What the status chip should say, in words rather than a colour alone. */
export function statusNote(status: FieldStatus, staleAfter: string | null):
    { tone: 'neutral' | 'warn' | 'alert'; text: string } {
  switch (status) {
    case 'conflict':
      return { tone: 'alert', text: 'sources disagree' };
    case 'stale':
      return { tone: 'warn',
               text: staleAfter ? `not re-read since ${formatDay(staleAfter)}`
                                : 'overdue for a re-read' };
    case 'manual_override':
      return { tone: 'neutral', text: 'set by an operator' };
    default:
      return { tone: 'neutral', text: 'current' };
  }
}

/**
 * Whether the imported baseline differs enough from the current value to be
 * worth showing side by side.
 *
 * A difference is the system working — a newer reading beat the import — so
 * this is an indicator, not a warning. Numbers use a relative threshold
 * because a headcount moving 62 to 63 is noise, while text differs or it does
 * not.
 */
export function baselineDiffers(baseline: unknown, canonical: unknown,
                                tolerance = 0.02): boolean {
  if (baseline == null || canonical == null) return false;
  const a = Number(baseline);
  const b = Number(canonical);
  if (!Number.isNaN(a) && !Number.isNaN(b)) {
    const scale = Math.max(Math.abs(a), Math.abs(b));
    if (scale === 0) return false;
    return Math.abs(a - b) / scale > tolerance;
  }
  return String(baseline).trim().toLowerCase()
      !== String(canonical).trim().toLowerCase();
}

export interface MentionCounts {
  channel: string;
  total: number;
  unevaluated: number;
  positive: number;
  negative: number;
  owned_claims: number;
}

export interface MentionSplit {
  owned: number;
  external: number;
  evaluated: number;
  unevaluated: number;
  positive: number;
  negative: number;
  /** Null when nothing has been evaluated — not zero, which reads as neutral. */
  netSentiment: number | null;
  /** What the percentage is actually out of, so the figure can be honest. */
  denominator: number;
}

export function splitMentions(rows: MentionCounts[]): MentionSplit {
  const owned = sum(rows.filter(r => isOwned(r.channel)), r => r.total);
  const externalRows = rows.filter(r => !isOwned(r.channel));
  const external = sum(externalRows, r => r.total);
  const unevaluated = sum(externalRows, r => r.unevaluated);
  const positive = sum(externalRows, r => r.positive);
  const negative = sum(externalRows, r => r.negative);
  const evaluated = external - unevaluated;

  return {
    owned, external, evaluated, unevaluated, positive, negative,
    denominator: evaluated,
    // Sentiment over nothing is not zero, it is unknown, and rendering it as
    // 0 puts a neutral verdict on a company nobody has assessed.
    netSentiment: evaluated > 0 ? (positive - negative) / evaluated : null,
  };
}

export function isOwned(channel: string): boolean {
  return (OWNED_CHANNELS as readonly string[]).includes(channel);
}

function sum<T>(rows: T[], pick: (row: T) => number): number {
  return rows.reduce((total, row) => total + (pick(row) || 0), 0);
}

/**
 * What the evidence for an event is, in words a reader can act on.
 *
 * Describes the evidence, never grades the truth. `vendor_claim` used to read
 * "the vendor says so; not yet corroborated", which asserted two things and
 * only one of them was a measurement: that the company said it is a fact about
 * the evidence, whereas "not yet corroborated" reads as doubt about whether the
 * event happened. For a company announcing its own partnership it is close to
 * the best available source that the partnership exists; what is missing is the
 * counterparty and an independent account of what it amounts to.
 *
 * "Not yet" also promised something the system does not do. The ladder only
 * rises if a matching independent source happens to arrive in the corpus, and
 * for a small vendor that may be never — so a permanently accurate state was
 * worded as a temporary one.
 *
 * Tones follow the same rule. A vendor announcing its own news is how you
 * normally learn about it, so that is `neutral`; `warn` is kept for having no
 * recorded source at all, which is a real gap.
 */
export function corroborationNote(corroboration: string, sources: number):
    { tone: 'neutral' | 'warn' | 'good'; text: string } {
  switch (corroboration) {
    case 'primary_document':
      return { tone: 'good', text: 'from a primary document' };
    case 'corroborated':
      return { tone: 'good', text: `${sources} independent sources` };
    case 'single_source':
      return { tone: 'neutral', text: 'one independent source' };
    case 'vendor_claim':
      return { tone: 'neutral',
               text: 'announced by the vendor, no independent source' };
    default:
      return { tone: 'warn', text: 'no source recorded' };
  }
}

/** An event with no stated date says so, rather than borrowing today's. */
export function eventDateLabel(occurredAt: string | null,
                               precision: string): string {
  if (!occurredAt || precision === 'unknown') return 'date not stated by the source';
  if (precision === 'month') {
    const date = new Date(occurredAt);
    return Number.isNaN(date.getTime()) ? 'date not stated by the source'
      : date.toLocaleDateString(undefined, { month: 'short', year: 'numeric' });
  }
  return formatDay(occurredAt);
}
