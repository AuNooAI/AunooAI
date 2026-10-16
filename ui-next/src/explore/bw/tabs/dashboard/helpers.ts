// Pure helpers for the Brand Watcher dashboard, ported from the old tab
// (ui/src/components/newsfeed/BrandWatcherTab.tsx). No React here.
import type { BWArticle, BWSentimentBucket, BWSocialPost, Brand } from '@monolith/brandWatcherApi';

export type Sent = 'positive' | 'neutral' | 'negative' | 'unrated';

/**
 * Social evaluation says Positive/Neutral/Negative; news enrichment uses richer labels
 * (Optimistic, Cautious, Concerned, Pessimistic, Critical, Alarming). Both map here, or the
 * adverse screens miss negative news.
 */
export function sentimentOf(s: string | null | undefined): Sent {
  const t = (s || '').toLowerCase();
  if (t.includes('pos') || t.includes('optimis')) return 'positive';
  if (t.includes('neg') || t.includes('concern') || t.includes('pessimis') || t.includes('critical') || t.includes('alarm')) return 'negative';
  if (t.includes('neu') || t.includes('cautious') || t === 'mixed') return 'neutral';
  return 'unrated';
}

/** Positive / neutral / negative counts from a label → count map. Unrated labels count as neutral, as the old page did. */
export function bucketCounts(m: Record<string, number>) {
  const out = { pos: 0, neu: 0, neg: 0 };
  for (const [k, n] of Object.entries(m || {})) {
    const s = sentimentOf(k);
    if (s === 'positive') out.pos += n;
    else if (s === 'negative') out.neg += n;
    else out.neu += n;
  }
  return out;
}

/** (positive − negative) ÷ scored × 100; null with nothing scored */
export const netOf = (pos: number, neg: number, scored: number) => (scored ? Math.round(((pos - neg) / scored) * 100) : null);
export const signed = (n: number | null | undefined) => (n == null ? '–' : `${n > 0 ? '+' : ''}${n}`);

/** The brand a social post belongs to, from its topic ("Brand Monitoring Wiley" → "Wiley"). */
export const socialBrandOf = (p: { topic?: string | null }) => (p.topic || '').replace(/^Brand Monitoring\s+/i, '').trim() || 'Other';

/** Likes + 2× reposts + comments + plays/100: the reach measure the old page used. */
export const engagementOf = (p: BWSocialPost) => {
  const m = (p.social_meta || {}) as Record<string, number | undefined>;
  return (m.likes || 0) + (m.reposts || 0) * 2 + (m.comments || 0) + (m.plays || 0) / 100;
};

export const PLATFORM_LABEL: Record<string, string> = { twitter: 'X', bluesky: 'Bluesky', reddit: 'Reddit', instagram: 'Instagram', tiktok: 'TikTok', social: 'Other' };
export const platformLabel = (p: string) => PLATFORM_LABEL[p] || p;
export const ROLE_LABEL: Record<string, string> = {
  patient: 'patient', clinician: 'clinician', caregiver: 'caregiver', customer: 'customer', academic: 'academic', professional: 'professional',
  employee: 'employee', journalist: 'press', investor: 'investor', brand: 'brand voice', dental_professional: 'dental professional', retailer: 'retailer',
  competitor: 'competitor', author: 'author', editor_reviewer: 'editor / reviewer', journal_society: 'journal / society', librarian: 'librarian',
  student: 'student', educator: 'educator', reader: 'reader',
};

export const fmtCount = (n?: number | null) => (n == null ? null : n >= 1000 ? `${(n / 1000).toFixed(n >= 10000 ? 0 : 1)}k` : `${Math.round(n)}`);

/**
 * The post's author handle (no "@"): collector metadata, then the old "Post by @handle" title,
 * then the handle in the post URL. A bare @mention in the body is never the author.
 */
export function handleOf(p: { title?: string | null; uri?: string; social_meta?: { author?: string | null } | null }): string | null {
  const sm = (p.social_meta?.author || '').trim();
  if (sm) return sm;
  const m = (p.title || '').match(/^Post by @([\w.-]+)/i);
  if (m) return m[1];
  const u = (p.uri || '').match(/^https?:\/\/(?:www\.|mobile\.)?(?:x\.com\/|twitter\.com\/|tiktok\.com\/@|bsky\.app\/profile\/|threads\.net\/@)([\w.-]+)/i);
  return u ? u[1] : null;
}

export function bodyOf(p: { title?: string | null; summary?: string | null }) {
  const body = (p.summary || '').trim();
  if (body) return body;
  return (p.title || '').replace(/^Post by @[\w.-]+\s*/i, '').trim() || (p.title || '').trim() || '(no text)';
}

/** Story-level flags from the sentiment mix across syndicated copies of one story. */
export const isNegConsensus = (a: BWArticle) => (a.story_scored || 0) >= 3 && (a.story_neg || 0) / (a.story_scored || 1) >= 0.7;
export const isPolarized = (a: BWArticle) => (a.story_scored || 0) >= 4 && Math.min(a.story_neg || 0, a.story_pos || 0) / (a.story_scored || 1) >= 0.3;
export const RISK_CAT = /legal|regulat|governance|leadership|financial|investor|crisis|controvers|integrity|litigation/i;

export function relDate(d?: string | null) {
  if (!d) return '';
  const days = Math.floor((Date.now() - new Date(d).getTime()) / 86400e3);
  if (Number.isNaN(days)) return '';
  if (days <= 0) return 'today';
  if (days === 1) return '1 day ago';
  if (days < 30) return `${days} days ago`;
  const months = Math.floor(days / 30);
  return `${months} ${months === 1 ? 'month' : 'months'} ago`;
}

/** Monday of the week, matching the server's DATE_TRUNC('week') */
export function weekOf(ds: string) {
  const d = new Date(`${ds.slice(0, 10)}T00:00:00Z`);
  if (Number.isNaN(+d)) return null;
  d.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 6) % 7));
  return d.toISOString().slice(0, 10);
}

export interface FanCritic {
  author: string;
  platform: string;
  brand: string;
  pos: number;
  neg: number;
  posEng: number;
  negEng: number;
  spanDays: number;
  trend: 'up' | 'down' | 'flat' | null;
}

/**
 * Fans and critics among on-brand (relevance ≥ 0.4) scored posts, ranked by reach: each aligned
 * post is worth 5 plus the engagement it earned. The brand's own handles are left out of fans.
 */
export function fansAndCritics(posts: BWSocialPost[], brands: Brand[]) {
  const norm = (s: string) => (s || '').toLowerCase().replace(/[^a-z0-9]/g, '');
  const own: Record<string, string[]> = {};
  for (const b of brands) own[b.display_name] = [...new Set([b.name, ...(b.brand_keywords || [])].map(norm).filter((t) => t.length >= 3))];
  const isOwn = (handle: string, brand: string) => {
    const lead = norm((handle || '').split('.')[0]);
    return !!lead && (own[brand] || []).some((t) => lead.startsWith(t));
  };
  const dates = posts.map((p) => p.publication_date || '').filter(Boolean).sort();
  const mid = dates.length ? dates[Math.floor(dates.length / 2)] : '';
  const by: Record<string, FanCritic & { first: string; last: string; recent: number; prior: number }> = {};
  for (const p of posts) {
    if ((p.relevance ?? 0) < 0.4) continue;
    const s = sentimentOf(p.sentiment);
    if (s === 'unrated') continue;
    const h = (handleOf(p) || '').trim();
    if (!h || h === 'unknown' || h.includes(':')) continue;
    const key = `${p.platform}:${h.toLowerCase()}`;
    const a = (by[key] ||= { author: h, platform: p.platform, brand: socialBrandOf(p), pos: 0, neg: 0, posEng: 0, negEng: 0, spanDays: 0, trend: null, first: '', last: '', recent: 0, prior: 0 });
    if (s === 'positive') { a.pos++; a.posEng += engagementOf(p); }
    if (s === 'negative') { a.neg++; a.negEng += engagementOf(p); }
    if (s !== 'neutral') {
      const d = p.publication_date || '';
      if (d) {
        if (!a.first || d < a.first) a.first = d;
        if (!a.last || d > a.last) a.last = d;
        if (mid && d >= mid) a.recent++;
        else a.prior++;
      }
    }
  }
  const all = Object.values(by).map((a) => ({
    ...a,
    spanDays: a.first && a.last ? Math.max(0, Math.round((new Date(a.last).getTime() - new Date(a.first).getTime()) / 86400e3)) : 0,
    trend: a.recent + a.prior >= 2 ? (a.recent > a.prior ? 'up' : a.recent < a.prior ? 'down' : 'flat') : null,
    own: isOwn(a.author, a.brand),
  })) as (FanCritic & { own: boolean })[];
  const fans = all.filter((a) => a.pos > a.neg && !a.own).sort((x, y) => (y.pos * 5 + y.posEng) - (x.pos * 5 + x.posEng) || y.pos - x.pos).slice(0, 10);
  const critics = all.filter((a) => a.neg > a.pos).sort((x, y) => (y.neg * 5 + y.negEng) - (x.neg * 5 + x.negEng) || y.neg - x.neg).slice(0, 10);
  return { fans, critics };
}

/** Weekly net sentiment for a set of weekly buckets (news), skipping thin weeks. */
export function weeklyNet(buckets: BWSentimentBucket[], minScored: number) {
  const out: Record<string, number> = {};
  for (const t of buckets) {
    const w = (t.week || '').slice(0, 10);
    if (!w) continue;
    const c = bucketCounts(t.sentiments);
    const tot = c.pos + c.neu + c.neg;
    if (tot >= minScored) out[w] = Math.round(((c.pos - c.neg) / tot) * 100);
  }
  return out;
}
