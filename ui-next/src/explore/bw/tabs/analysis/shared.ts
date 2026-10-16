import { CATEGORY_SHORT_NAMES } from '@monolith/brandWatcherApi';
import type { ChartColor } from '@aunoo/ui';

/*
 * Helpers shared by Brand analysis, Comparison, Insights and Perception, lifted from the old
 * BrandWatcherTab.tsx so the numbers match it.
 */

export type Bucket = 'positive' | 'neutral' | 'negative';

/**
 * News labels are richer than social ones (Optimistic, Concerned, Critical…); both map to three
 * buckets as the old page did for its sentiment bars.
 */
export function bucketOf(label: string): Bucket {
  const lo = label.toLowerCase();
  if (lo.includes('pos') || lo.includes('optimis')) return 'positive';
  if (lo.includes('neg') || lo.includes('pessimis') || lo.includes('concern') || lo.includes('critical') || lo.includes('alarm')) return 'negative';
  return 'neutral';
}

export function bucketCounts(breakdown: Record<string, number> | undefined) {
  const out = { positive: 0, neutral: 0, negative: 0 };
  for (const [s, n] of Object.entries(breakdown ?? {})) out[bucketOf(s)] += n;
  return out;
}

/** (positive − negative) ÷ scored × 100, or null with nothing scored */
export function netOf(breakdown: Record<string, number> | undefined): number | null {
  const c = bucketCounts(breakdown);
  const t = c.positive + c.neutral + c.negative;
  return t ? Math.round(((c.positive - c.negative) / t) * 100) : null;
}

export const signed = (n: number | null | undefined) => (n == null ? '–' : `${n > 0 ? '+' : ''}${n}`);
export const short = (cat: string) => CATEGORY_SHORT_NAMES[cat] || cat;
export const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

/** A fixed chart colour per brand, by its place in the brand list (the primary first) */
export function brandColors(ids: number[]): Map<number, ChartColor> {
  return new Map(ids.map((id, i) => [id, ((i % 5) + 1) as ChartColor]));
}

/** The report's sections, keyed by lowercase H2 heading */
export function splitSections(md: string): Record<string, string> {
  const out: Record<string, string> = {};
  const re = /^##\s+(.+)$/gm;
  let m: RegExpExecArray | null;
  let last: { name: string; start: number } | null = null;
  const push = (end: number) => {
    if (last) out[last.name.trim().toLowerCase()] = md.slice(last.start, end).trim();
  };
  while ((m = re.exec(md))) {
    push(m.index);
    last = { name: m[1], start: m.index + m[0].length };
  }
  push(md.length);
  return out;
}

/** The report's known sections, in reading order */
export const REPORT_SECTIONS: [string, string][] = [
  ['executive summary', 'Executive summary'],
  ['category analysis', 'Category analysis'],
  ['sentiment & reputation', 'Sentiment and reputation'],
  ['social pulse', 'Social pulse'],
  ['risk & compliance', 'Risk and compliance'],
  ['workforce signal', 'Workforce signal'],
  ['forward-looking concerns', 'Forward-looking concerns'],
];

export const titleCase = (s: string) => s.replace(/\b\w/g, (c) => c.toUpperCase());

/** Ranks rows by volume and keeps the top N, always including the primary brand */
export function topN<T extends { brand_id: number }>(rows: T[], n: number, volume: (r: T) => number, primaryIds: Set<number>): Set<number> {
  const keep = new Set<number>(primaryIds);
  for (const r of [...rows].sort((a, b) => volume(b) - volume(a))) {
    if (keep.size >= n) break;
    keep.add(r.brand_id);
  }
  return keep;
}

export function topNOptions(total: number) {
  return [3, 5, 8, 10, total]
    .filter((n, i, arr) => n <= total && arr.indexOf(n) === i)
    .map((n) => ({ value: String(n), label: n === total ? `All ${n} brands` : `Top ${n} brands` }));
}

/** CSV cell */
export const csv = (v: unknown) => `"${String(v ?? '').replace(/"/g, '""')}"`;
