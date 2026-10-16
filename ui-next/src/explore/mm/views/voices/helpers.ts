import type { Voice } from '@monolith/marketMonitorApi';

/* Label maps and formatters for Top voices, copied from the old MarketVoicesView.tsx. */

export const PLATFORM_LABEL: Record<string, string> = {
  twitter: 'X', bluesky: 'Bluesky', reddit: 'Reddit', tiktok: 'TikTok', instagram: 'Instagram', linkedin: 'LinkedIn',
};
/** Platforms the account profiler can read */
export const PROFILABLE = new Set(['twitter', 'bluesky', 'reddit', 'instagram', 'tiktok']);
const ROLE_LABEL: Record<string, string> = {
  vendor: 'vendor', vendor_staff: 'vendor staff', practitioner: 'practitioner', analyst_or_press: 'analyst or press',
  reseller: 'reseller', promoter_or_bot: 'promoter or bot', unrelated: 'unrelated',
};

export const platformLabel = (p: string) => PLATFORM_LABEL[p] ?? p;
export const keyOf = (v: Voice) => `${v.platform}:${v.author}`;

/** Who is speaking, in a word: the vendor tag, else the profile's role, else what the account's own posts say */
export function roleOf(v: Voice): string {
  if (v.vendor_tag) return v.vendor_tag.label;
  const r = v.account?.role;
  if (r) return ROLE_LABEL[r] ?? r;
  if (v.audience?.source === 'account_posts') return v.audience.label.toLowerCase();
  return v.account?.profiled ? 'not read' : 'not profiled';
}

/** Said beside a role that was read from posts rather than a profile */
export function roleNote(v: Voice): string | null {
  if (v.vendor_tag || v.account?.role) return null;
  if (v.audience?.source === 'account_posts') return `read from ${v.audience.n ?? 'their'} classified post(s); a profile gives a stronger reading`;
  return null;
}

/** A vendor's own account, or their staff: kept on the list and marked */
export function vendorTagText(tag: NonNullable<Voice['vendor_tag']>): string {
  return `${tag.label}${tag.org ? `: ${tag.org}` : ''}${tag.tracked ? ' (a vendor we track)' : ''}${tag.linked ? ', recorded on the vendor profile' : ''}`;
}

export function compact(n: number | null | undefined): string {
  if (n == null) return '—';
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 10_000) return `${Math.round(n / 1000)}k`;
  if (n >= 1_000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}

export function clip(s: string | null | undefined, n: number): string {
  const t = (s ?? '').trim();
  return t.length > n ? `${t.slice(0, n - 1).trimEnd()}…` : t;
}

/** The coverage clause starts with a capital, as a sentence */
export const sentence = (s: string) => (s ? s[0].toUpperCase() + s.slice(1) : s);
