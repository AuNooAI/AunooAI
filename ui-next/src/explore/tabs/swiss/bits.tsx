// Labels shared by the Swiss Election Watch panels. Colour backs up the text, never replaces it.
import { Chip, EmptyState, Skeleton } from '@aunoo/ui';

type Tone = 'accent' | 'neutral' | 'muted' | 'success' | 'warning' | 'info' | 'error';

export const TIER_LABEL: Record<string, string> = {
  state_media: 'State media', alt_media: 'Alternative media', mainstream: 'Mainstream', party: 'Party',
  fact_checker: 'Fact-checker', institution: 'Institution', research: 'Research', unknown: 'Unknown',
};
const TIER_TONE: Record<string, Tone> = {
  state_media: 'error', alt_media: 'warning', mainstream: 'info', party: 'accent', fact_checker: 'success',
  institution: 'neutral', research: 'neutral', unknown: 'muted',
};
export const LANG_NAME: Record<string, string> = { de: 'German', fr: 'French', it: 'Italian', en: 'English' };
export const LANGS = ['de', 'fr', 'it', 'en'] as const;
const STANCE_TONE: Record<string, Tone> = { promotes: 'error', reports: 'info', debunks: 'success' };

export const label = (s: string) => s.replace(/_/g, ' ');
export const when = (t: string | null | undefined) => (t ? t.slice(0, 16).replace('T', ' ') : '–');

export function TierChip({ tier }: { tier: string | null }) {
  const t = tier || 'unknown';
  return <Chip size="sm" tone={TIER_TONE[t] ?? 'muted'}>{TIER_LABEL[t] ?? label(t)}</Chip>;
}

export function LangChip({ lang }: { lang: string | null }) {
  if (!lang) return null;
  return (
    <Chip size="sm" tone="neutral">
      <span aria-hidden="true">{lang.toUpperCase()}</span>
      <span className="visually-hidden">{LANG_NAME[lang] ?? lang}</span>
    </Chip>
  );
}

export function StanceChip({ stance }: { stance: string }) {
  return <Chip size="sm" tone={STANCE_TONE[stance] ?? 'muted'}>{stance}</Chip>;
}

/** "12 (▲ from 4)" so the week-on-week change reads without colour */
export function trend(now: number, prev: number) {
  if (!now && !prev) return '–';
  if (now === prev) return `${now} (same as before)`;
  return `${now} (${now > prev ? 'up' : 'down'} from ${prev})`;
}

export function Loading() {
  return <Skeleton variant="block" size="chart" />;
}

export function Empty({ children }: { children: React.ReactNode }) {
  return <EmptyState headingLevel={4}>{children}</EmptyState>;
}
