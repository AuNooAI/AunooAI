/*
 * The periods a report can be written for, as the old MarketBriefingsView.tsx. Each option is an ISO
 * date the backend resolves back to the whole period. The period in progress is left out on purpose:
 * a report about it would be wrong by the time it ends, and the backend refuses it anyway.
 */

export type PeriodKind = 'day' | 'week' | 'month' | 'year';

export const PERIOD_KINDS: { value: PeriodKind; label: string }[] = [
  { value: 'day', label: 'Day' },
  { value: 'week', label: 'Week' },
  { value: 'month', label: 'Month' },
  { value: 'year', label: 'Year' },
];

export interface PeriodOption {
  /** What the backend is sent */
  refDate: string;
  /** First day of the period, to match an existing report's period_start */
  start: string;
  label: string;
}

const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
const fmt = (d: Date, o: Intl.DateTimeFormatOptions) => d.toLocaleDateString('en-GB', o);

/** Options for one kind, newest first */
export function periodOptions(kind: PeriodKind): PeriodOption[] {
  const now = new Date();
  const out: PeriodOption[] = [];
  if (kind === 'day') {
    for (let i = 1; i <= 30; i++) {
      const d = new Date(now.getFullYear(), now.getMonth(), now.getDate() - i);
      out.push({ refDate: iso(d), start: iso(d), label: fmt(d, { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' }) });
    }
  } else if (kind === 'week') {
    const thisMonday = new Date(now.getFullYear(), now.getMonth(), now.getDate() - ((now.getDay() + 6) % 7));
    for (let i = 1; i <= 12; i++) {
      const monday = new Date(thisMonday.getFullYear(), thisMonday.getMonth(), thisMonday.getDate() - 7 * i);
      const sunday = new Date(monday.getFullYear(), monday.getMonth(), monday.getDate() + 6);
      out.push({ refDate: iso(monday), start: iso(monday), label: `Week of ${fmt(monday, { day: 'numeric', month: 'short' })} to ${fmt(sunday, { day: 'numeric', month: 'short', year: 'numeric' })}` });
    }
  } else if (kind === 'year') {
    for (let i = 1; i <= 5; i++) {
      const y = now.getFullYear() - i;
      out.push({ refDate: `${y}-06-15`, start: `${y}-01-01`, label: String(y) });
    }
  } else {
    for (let i = 1; i <= 12; i++) {
      const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
      out.push({ refDate: iso(d), start: iso(d), label: fmt(d, { month: 'long', year: 'numeric' }) });
    }
  }
  return out;
}
