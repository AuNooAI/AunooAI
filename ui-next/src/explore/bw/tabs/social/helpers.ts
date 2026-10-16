// Shared by the Social, Accounts and Voices sub-tabs: how a social post is read (brand, author,
// sentiment, text), platform names, and the hand-off from a post author to the Accounts tab.
import { cleanSocialText } from '@monolith/socialText';
import type { BWSocialPost } from '@monolith/brandWatcherApi';

export type Sent = 'positive' | 'neutral' | 'negative' | 'unrated';

export const PLATFORM_LABELS: Record<string, string> = {
  twitter: 'X', bluesky: 'Bluesky', reddit: 'Reddit', instagram: 'Instagram', tiktok: 'TikTok', glassdoor: 'Glassdoor', social: 'Other',
};
export const PLATFORM_ORDER = ['twitter', 'bluesky', 'reddit', 'instagram', 'tiktok', 'social'];
/** Networks an account profile can be built for */
export const PROFILE_PLATFORMS = ['twitter', 'bluesky', 'reddit', 'instagram', 'tiktok'];
export const platLabel = (p: string) => PLATFORM_LABELS[p] ?? p;

/** "Brand Monitoring Wiley" → "Wiley" */
export const brandOf = (p: { topic?: string | null }) => (p.topic || '').replace(/^Brand Monitoring\s+/i, '').trim() || 'Other';

/**
 * Social eval writes Positive/Neutral/Negative; news enrichment writes richer labels
 * (Optimistic, Concerned, Critical…). Both map here, as in the old tab.
 */
export function sentOf(s: string | null | undefined): Sent {
  const t = (s || '').toLowerCase();
  if (t.includes('pos') || t.includes('optimis')) return 'positive';
  if (t.includes('neg') || t.includes('concern') || t.includes('pessimis') || t.includes('critical') || t.includes('alarm')) return 'negative';
  if (t.includes('neu') || t.includes('cautious') || t === 'mixed') return 'neutral';
  return 'unrated';
}

export const SENT_TONE: Record<Sent, 'success' | 'error' | 'muted' | 'neutral'> = { positive: 'success', negative: 'error', neutral: 'neutral', unrated: 'muted' };
export const SENT_LABEL: Record<Sent, string> = { positive: 'Positive', neutral: 'Neutral', negative: 'Negative', unrated: 'Not scored' };

/**
 * The post's author handle (no "@"): collector metadata, then the old "Post by @handle" title,
 * then the handle in the post URL. A bare @mention in the text is never taken as the author,
 * because the post may be about that account.
 */
export function handleOf(p: { title?: string | null; uri?: string; social_meta?: { author?: string | null } | null }): string | null {
  const sm = (p.social_meta?.author || '').trim();
  if (sm) return sm;
  const m = (p.title || '').match(/^Post by @([\w.-]+)/i);
  if (m) return m[1];
  const u = (p.uri || '').match(/^https?:\/\/(?:www\.|mobile\.)?(?:x\.com\/|twitter\.com\/|tiktok\.com\/@|bsky\.app\/profile\/|threads\.net\/@)([\w.-]+)/i);
  return u ? u[1] : null;
}

export const authorOf = (p: BWSocialPost) => {
  const h = handleOf(p);
  return h ? `@${h}` : p.news_source || p.platform || 'unknown';
};

export function bodyOf(p: { title?: string | null; summary?: string | null }) {
  const body = (p.summary || '').trim();
  const text = body || (p.title || '').replace(/^Post by @[\w.-]+\s*/i, '').trim() || (p.title || '').trim() || '(no text)';
  return cleanSocialText(text)
    .replace(/^\s*#{1,6}\s*/gm, '')
    .replace(/^\s*([-*_]\s*){3,}\s*$/gm, '')
    .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '$1')
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/\n{2,}/g, '\n')
    .trim();
}

/** Likes + 2 × reposts + comments + plays/100, as the old tab weighed reach */
export function engOf(p: { social_meta?: BWSocialPost['social_meta'] }) {
  const m = p.social_meta || {};
  return (m.likes || 0) + (m.reposts || 0) * 2 + (m.comments || 0) + (m.plays || 0) / 100;
}

export const fmtCount = (n?: number | null) => (n == null ? null : n >= 1000 ? `${(n / 1000).toFixed(n >= 10000 ? 0 : 1)}k` : `${Math.round(n)}`);
export const netOf = (pos: number, neg: number, scored: number) => (scored ? Math.round(((pos - neg) / scored) * 100) : null);
export const signed = (n: number | null) => (n == null ? '–' : `${n > 0 ? '+' : ''}${n}`);
export const netTone = (n: number | null): 'success' | 'error' | 'warning' | 'muted' => (n == null ? 'muted' : n >= 20 ? 'success' : n <= -20 ? 'error' : 'warning');

/** Who wrote the post (articles.author_role); same list as the Voices view */
export const ROLE_LABEL: Record<string, string> = {
  patient: 'Patient', clinician: 'Clinician', caregiver: 'Caregiver', customer: 'Customer', academic: 'Academic', professional: 'Professional',
  employee: 'Employee', journalist: 'Press', investor: 'Investor', brand: 'Brand voice', dental_professional: 'Dental professional',
  retailer: 'Retailer', competitor: 'Competitor', author: 'Author', editor_reviewer: 'Editor or reviewer', journal_society: 'Journal or society',
  librarian: 'Librarian', student: 'Student', educator: 'Educator', reader: 'Reader',
};

// ── Hand-off from a post author to the Accounts tab ─────────────────────
// BwContext.goTo switches tabs but carries no payload, so the handle waits here until Accounts opens.

let pendingAccount: { platform: string; handle: string } | null = null;
export function queueAccount(platform: string, handle: string) {
  pendingAccount = { platform, handle: handle.replace(/^@/, '') };
}
export function takeQueuedAccount() {
  const p = pendingAccount;
  pendingAccount = null;
  return p;
}

/** Saves text as a file in the browser. */
export function download(name: string, text: string, type = 'text/csv') {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([text], { type }));
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}
