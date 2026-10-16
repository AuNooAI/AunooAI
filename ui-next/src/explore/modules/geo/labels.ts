import type { RiskLevel, ThreatCategory, Trend } from '@monolith/geopoliticalHotspotsApi';

/** Risk levels, most severe first, as the old page ordered them */
export const RISK_ORDER: RiskLevel[] = ['critical', 'high', 'medium', 'low', 'info'];

export const RISK_LABEL: Record<RiskLevel, string> = {
  critical: 'Critical', high: 'High', medium: 'Medium', low: 'Low', info: 'Info',
};

/** Chip tones per risk level; the label always carries the level too, so colour is never the only cue */
export const RISK_TONE: Record<RiskLevel, 'error' | 'warning' | 'success' | 'info' | 'neutral'> = {
  critical: 'error', high: 'error', medium: 'warning', low: 'success', info: 'info',
};

export const CATEGORIES: ThreatCategory[] = [
  'conflict', 'protest', 'disaster', 'diplomatic', 'economic', 'terrorism', 'cyber',
  'health', 'environmental', 'military', 'crime', 'piracy', 'infrastructure', 'commodities',
];

export const cap = (s: string | null | undefined) => (s ? s.charAt(0).toUpperCase() + s.slice(1).replace(/_/g, ' ') : '');

export const TREND_LABEL: Record<Trend, string> = { escalating: 'Escalating', stable: 'Stable', 'de-escalating': 'De-escalating' };

export const fmtDate = (s: string | null | undefined) =>
  s ? new Date(s).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) : '';
export const fmtDateTime = (s: string | null | undefined) =>
  s ? new Date(s).toLocaleString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '';
export const shortDate = (s: string) => new Date(s).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });

export const PERIOD_OPTIONS = [
  { value: '7', label: 'Last 7 days' },
  { value: '30', label: 'Last 30 days' },
  { value: '90', label: 'Last 90 days' },
  { value: '180', label: 'Last 6 months' },
  { value: '365', label: 'Last year' },
];

/** Round tick steps for a chart axis from 0 to just above max */
export function ticksFor(max: number, steps = 4): number[] {
  if (max <= 0) return [0, 1];
  const raw = max / steps;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? raw;
  const top = Math.ceil(max / step) * step;
  const out: number[] = [];
  for (let v = 0; v <= top + step / 2; v += step) out.push(Math.round(v * 100) / 100);
  return out;
}
