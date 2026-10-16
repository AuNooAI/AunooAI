import type { IconName } from '@aunoo/ui';

const nf = new Intl.NumberFormat('en-US');
export const fmt = (n: number) => nf.format(n);

/** "1 keyword" / "25 keywords" */
export const plural = (n: number, one: string, many = `${one}s`) => `${fmt(n)} ${n === 1 ? one : many}`;

/** Next-check label: "Due now", "In 5 min", "In 21 hr", "In 3 days". */
export function nextLabel(at: Date | null, now: Date) {
  if (!at) return 'Unknown';
  const minutes = Math.round((at.getTime() - now.getTime()) / 60000);
  if (minutes <= 0) return 'Due now';
  if (minutes < 60) return `In ${minutes} min`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `In ${hours} hr`;
  return `In ${Math.round(hours / 24)} days`;
}

/** "Just now", "5m ago", "3h ago", or the date. */
export function ago(at: Date | string | null | undefined, now: Date) {
  if (!at) return 'Never';
  const d = typeof at === 'string' ? new Date(at) : at;
  const m = Math.floor((now.getTime() - d.getTime()) / 60000);
  if (m < 1) return 'Just now';
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return d.toLocaleDateString('en-GB');
}

export const stamp = (date: Date) =>
  date.toLocaleString('en-GB', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });

/** Whole number in [min, max], or an error message. */
export function rangeError(value: string, min: number, max: number) {
  const n = Number(value);
  if (value.trim() === '' || !Number.isInteger(n)) return 'Enter a whole number.';
  if (n < min || n > max) return `Use a value from ${fmt(min)} to ${fmt(max)}.`;
  return undefined;
}

export type Notify = (message: string, icon?: IconName) => void;
