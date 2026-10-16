export function fmtDate(d?: string): string {
  if (!d) return 'unknown date';
  const t = new Date(d);
  return Number.isNaN(t.getTime()) ? d : t.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}

export const URGENCY_LABEL = { immediate: 'Immediate', this_week: 'This week', this_month: 'This month', this_quarter: 'This quarter' } as const;
export const URGENCY_TONE = { immediate: 'error', this_week: 'warning', this_month: 'info', this_quarter: 'muted' } as const;
