import { CATEGORY_COLORS, CATEGORY_DESCRIPTIONS, CATEGORY_SHORT_NAMES, DEFAULT_SCIENCE_TOPIC } from '@monolith/scienceFundingApi';

/*
 * Labels and small helpers shared by the ScienceWatch sub-tabs. Category names, colours and
 * descriptions come from the old service (ui/src/services/scienceFundingApi.ts) so both pages
 * describe the ten funding categories the same way.
 */

export const SCIENCE_TOPIC = DEFAULT_SCIENCE_TOPIC;

export const PERIOD_OPTIONS = [
  { value: '7', label: 'Last 7 days' },
  { value: '30', label: 'Last 30 days' },
  { value: '90', label: 'Last 90 days' },
  { value: '180', label: 'Last 6 months' },
  { value: '365', label: 'Last year' },
  { value: '0', label: 'All time' },
];

export const periodText = (days: number) =>
  days === 0 ? 'all time' : days === 365 ? 'the last year' : days === 180 ? 'the last 6 months' : `the last ${days} days`;

export const shortName = (category: string) => CATEGORY_SHORT_NAMES[category] || category;
export const categoryColor = (category: string) => CATEGORY_COLORS[category] || '#6B7280';
export const categoryDescription = (category: string) => CATEGORY_DESCRIPTIONS[category] || '';

export function fmtDate(value: string | null | undefined, withYear = true): string {
  if (!value) return '';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString('en-GB', withYear ? { day: 'numeric', month: 'short', year: 'numeric' } : { day: 'numeric', month: 'short' });
}

export const fmtDateTime = (value: string | null | undefined) => {
  if (!value) return '';
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
};

/** About five y-axis ticks on a 1-2-5 step, from zero */
export function ticks(max: number): { domain: [number, number]; ticks: number[] } {
  const top = max > 0 ? max : 1;
  const raw = top / 5;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const step = [1, 2, 5, 10].map((m) => m * mag).find((x) => x >= raw) ?? 10 * mag;
  const end = Math.ceil(top / step) * step;
  const out: number[] = [];
  for (let v = 0; v <= end + step / 2; v += step) out.push(Number(v.toPrecision(6)));
  return { domain: [0, end], ticks: out };
}

/** What an empty ScienceWatch shows: where its articles come from */
export const HOW_DATA_ARRIVES =
  `ScienceWatch reads the articles collected for the topic “${DEFAULT_SCIENCE_TOPIC}”. Once that topic has articles, ` +
  'use Classify articles to sort them into the ten funding categories (or set a schedule to do it). The counts, charts and ' +
  'themes here fill in from those categorised articles.';
