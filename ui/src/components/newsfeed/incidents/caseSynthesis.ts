/**
 * Case synthesis: turns the raw incident payload (locker evidence + agent
 * candidates + signals + timeline) into what a brand-protection analyst
 * actually asks of a case —
 *
 *   coverage:   every post/article about this incident, in the case or
 *               found by AI, with platform/author/date/engagement
 *   accounts:   who is involved (profiled accounts + authors seen posting)
 *   credibility: the Five Signals verdicts across screened items
 *   chronology: how it unfolded — content by publication date merged with
 *               case milestones
 *
 * Display-title/clean-text helpers mirror incidentReportService.ts (kept
 * separate so report generation and the live UI can evolve independently).
 */
import {
  BWEnrichmentState, BWIncidentDetail, BWIncidentEvidence,
} from '../../../services/brandWatcherApi';

export function cleanText(s: any): string {
  return String(s ?? '')
    .replace(/\\n/g, '\n')
    .replace(/�+ ?/g, '')
    .replace(/[ \t]+\n/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

function truncate(s: string, n: number): string {
  const t = s.replace(/\s+/g, ' ').trim();
  if (t.length <= n) return t;
  const cut = t.slice(0, n);
  return (cut.slice(0, cut.lastIndexOf(' ') > n - 25 ? cut.lastIndexOf(' ') : n)).trim() + '…';
}

const PLATFORM_LABEL: Record<string, string> = {
  bluesky: 'Bluesky', twitter: 'X', x: 'X', instagram: 'Instagram',
  reddit: 'Reddit', tiktok: 'TikTok', mastodon: 'Mastodon',
};

function authorFromUrl(ref?: string | null): { handle?: string; platform?: string } {
  const r = String(ref || '');
  let m = /bsky\.app\/profile\/([^/?]+)/.exec(r);
  if (m) return { handle: m[1], platform: 'Bluesky' };
  m = /(?:^|\/\/)(?:www\.)?(?:x|twitter)\.com\/([^/?]+)\/status/.exec(r);
  if (m) return { handle: m[1], platform: 'X' };
  m = /reddit\.com\/(?:user|u)\/([^/?]+)/.exec(r);
  if (m) return { handle: m[1], platform: 'Reddit' };
  m = /tiktok\.com\/@([^/?]+)/.exec(r);
  if (m) return { handle: m[1], platform: 'TikTok' };
  if (/instagram\.com\//.test(r)) return { platform: 'Instagram' };
  if (/reddit\.com\//.test(r)) return { platform: 'Reddit' };
  return {};
}

export function hostOf(url?: string | null): string {
  try { return url ? new URL(url).hostname.replace(/^www\./, '') : ''; } catch { return ''; }
}

// Cyrillic → CJK ranges; mirrors the report generator's heuristic.
const NON_LATIN_RE = /[Ѐ-ӿ԰-֏֐-׿؀-ۿ܀-޿ऀ-෿฀-໿ᄀ-ᇿ一-鿿぀-ヿ가-힯]/g;

/** True when the text is substantially non-English and worth translating. */
export function needsTranslation(s: string): boolean {
  const t = cleanText(s);
  const nonLatin = (t.match(NON_LATIN_RE) || []).length;
  if (nonLatin < 10) return false;
  const latin = (t.match(/[A-Za-z]/g) || []).length;
  return nonLatin / (nonLatin + latin) > 0.3;
}

/** One row of coverage — a post or article about this incident. */
export interface CoverageItem {
  key: string;
  inCase: boolean;                 // true = locker evidence, false = AI-found candidate
  candidateId?: number;            // set when inCase=false (accept/reject targets)
  evidence?: BWIncidentEvidence;   // set when inCase=true
  type: 'article' | 'social_post';
  title: string;                   // human label: "Post by @x on Bluesky" / article title
  url?: string | null;
  platform?: string;               // 'News' for articles
  author?: string | null;
  date?: string | null;            // publication date (YYYY-MM-DD)
  engagement: number;
  engagementLine: string;
  body?: string;                   // cleaned snippet/content
  signals?: any;                   // signals_summary for screened articles
  aiReason?: string;               // triage rationale / find reason (agent items)
}

export interface InvolvedAccount {
  key: string;
  handle: string;
  platform: string;
  displayName?: string | null;
  avatarUrl?: string | null;
  followers?: number | null;
  posts: number;                   // posts by this account in the coverage
  engagement: number;
  profiled: boolean;               // has an attached account_profile snapshot
}

export interface ChronologyRow {
  date: string;                    // YYYY-MM-DD
  time?: string;
  kind: 'content' | 'milestone';
  label: string;
  item?: CoverageItem;
}

export interface CaseSynthesis {
  coverage: CoverageItem[];        // newest first
  agentFound: CoverageItem[];      // subset: not yet in the case
  platforms: { name: string; count: number }[];
  totalEngagement: number;
  accounts: InvolvedAccount[];
  verdicts: { title: string; url?: string | null; verdict: string | null; composite: number | null }[];
  worstVerdict: string | null;
  chronology: ChronologyRow[];     // oldest first
  otherEvidence: BWIncidentEvidence[]; // files, notes, alert events — non-content locker items
}

const meta = (o: any) => o?.meta || {};

function itemEngagement(m: any): number {
  const e = m?.engagement != null && typeof m.engagement === 'number' ? m.engagement : null;
  if (e != null) return e;
  const sm = m?.social_meta || m || {};
  return ['likes', 'reposts', 'comments'].reduce((s, k) => s + (Number(sm[k]) || 0), 0);
}

function engagementLine(m: any): string {
  const sm = (m?.social_meta && typeof m.social_meta === 'object') ? m.social_meta
    : (m?.engagement && typeof m.engagement === 'object') ? m.engagement : m || {};
  const parts: string[] = [];
  if (sm.likes != null) parts.push(`${sm.likes} likes`);
  if (sm.reposts != null) parts.push(`${sm.reposts} reposts`);
  if (sm.comments != null) parts.push(`${sm.comments} comments`);
  if (parts.length) return parts.join(' · ');
  // Some payloads only carry a precomputed total
  const total = itemEngagement(m);
  return total > 0 ? `${total} engagement` : '';
}

function socialTitle(title: string | null | undefined, ref: string | null | undefined, m: any): { title: string; author?: string; platform: string } {
  const author = m?.author || m?.social_meta?.author;
  const platformKey = String(m?.platform || m?.social_meta?.platform || '').toLowerCase();
  const urlInfo = authorFromUrl(ref);
  const platform = PLATFORM_LABEL[platformKey] || urlInfo.platform || 'Social';
  const handle = author || urlInfo.handle;
  if (handle) return { title: `Post by @${handle} on ${platform}`, author: handle, platform };
  const t = cleanText(title || '');
  return { title: platform !== 'Social' && t ? `${platform} post: “${truncate(t, 60)}”` : truncate(t || String(ref || 'Social post'), 80), platform };
}

export function synthesizeCase(inc: BWIncidentDetail, enrich: BWEnrichmentState | null): CaseSynthesis {
  const coverage: CoverageItem[] = [];
  const otherEvidence: BWIncidentEvidence[] = [];

  for (const ev of inc.evidence || []) {
    const m = meta(ev);
    if (ev.evidence_type === 'article') {
      coverage.push({
        key: `ev-${ev.id}`, inCase: true, evidence: ev, type: 'article',
        title: cleanText(ev.title) || hostOf(ev.source_ref) || '(untitled article)',
        url: ev.source_ref, platform: 'News',
        date: (m.publication_date || '').slice(0, 10) || null,
        engagement: 0, engagementLine: '',
        body: cleanText(ev.content).slice(0, 400) || undefined,
        signals: (ev as any).signals_summary || null,
      });
    } else if (ev.evidence_type === 'social_post') {
      const st = socialTitle(ev.title, ev.source_ref, m);
      coverage.push({
        key: `ev-${ev.id}`, inCase: true, evidence: ev, type: 'social_post',
        title: st.title, url: ev.source_ref, platform: st.platform, author: st.author || null,
        date: (m.publication_date || '').slice(0, 10) || null,
        engagement: itemEngagement(m), engagementLine: engagementLine(m),
        body: cleanText(ev.content).slice(0, 400) || undefined,
      });
    } else {
      otherEvidence.push(ev);
    }
  }

  for (const cand of enrich?.candidates || []) {
    const m = meta(cand);
    if (cand.candidate_type === 'article') {
      coverage.push({
        key: `cand-${cand.id}`, inCase: false, candidateId: cand.id, type: 'article',
        title: cleanText(cand.title) || hostOf(cand.source_ref) || '(untitled article)',
        url: cand.source_ref, platform: 'News',
        date: (m.publication_date || '').slice(0, 10) || null,
        engagement: 0, engagementLine: '',
        body: cleanText(cand.snippet).slice(0, 400) || undefined,
        aiReason: cand.triage_rationale || cand.reason || undefined,
      });
    } else if (cand.candidate_type === 'social_post') {
      const st = socialTitle(cand.title, cand.source_ref, m);
      coverage.push({
        key: `cand-${cand.id}`, inCase: false, candidateId: cand.id, type: 'social_post',
        title: st.title, url: cand.source_ref, platform: st.platform, author: st.author || null,
        date: (m.publication_date || '').slice(0, 10) || null,
        engagement: itemEngagement(m), engagementLine: engagementLine(m),
        body: cleanText(cand.snippet).slice(0, 400) || undefined,
        aiReason: cand.triage_rationale || cand.reason || undefined,
      });
    }
    // account_profile candidates fold into `accounts` below
  }

  coverage.sort((a, b) => (b.date || '').localeCompare(a.date || ''));

  // Platforms + reach
  const platCounts: Record<string, number> = {};
  let totalEngagement = 0;
  for (const it of coverage) {
    platCounts[it.platform || 'Other'] = (platCounts[it.platform || 'Other'] || 0) + 1;
    totalEngagement += it.engagement;
  }
  const platforms = Object.entries(platCounts).map(([name, count]) => ({ name, count }))
    .sort((a, b) => b.count - a.count);

  // Who's involved: profiled accounts + authors seen in coverage
  const accounts = new Map<string, InvolvedAccount>();
  for (const ev of inc.evidence || []) {
    if (ev.evidence_type !== 'account_profile') continue;
    const m = meta(ev);
    const p = m.profile || {};
    const key = `${(m.platform || '').toLowerCase()}:${(m.handle || p.handle || '').toLowerCase()}`;
    accounts.set(key, {
      key, handle: m.handle || p.handle || '?', platform: PLATFORM_LABEL[String(m.platform || '').toLowerCase()] || m.platform || '',
      displayName: m.display_name || p.display_name, avatarUrl: m.avatar_url || p.avatar_url,
      followers: m.followers_count ?? p.followers_count, posts: 0, engagement: 0, profiled: true,
    });
  }
  for (const cand of enrich?.candidates || []) {
    if (cand.candidate_type !== 'account_profile') continue;
    const m = meta(cand);
    const key = `${(m.platform || '').toLowerCase()}:${(m.handle || '').toLowerCase()}`;
    if (!accounts.has(key)) {
      accounts.set(key, {
        key, handle: m.handle || '?', platform: PLATFORM_LABEL[String(m.platform || '').toLowerCase()] || m.platform || '',
        displayName: m.display_name, avatarUrl: m.avatar_url, followers: m.followers_count,
        posts: 0, engagement: 0, profiled: false,
      });
    }
  }
  for (const it of coverage) {
    if (!it.author) continue;
    const key = `${(it.platform || '').toLowerCase()}:${it.author.toLowerCase()}`;
    const acc = accounts.get(key) || {
      key, handle: it.author, platform: it.platform || '', displayName: null,
      avatarUrl: null, followers: null, posts: 0, engagement: 0, profiled: false,
    };
    acc.posts += 1;
    acc.engagement += it.engagement;
    accounts.set(key, acc);
  }
  const accountList = Array.from(accounts.values())
    .sort((a, b) => (b.followers || 0) - (a.followers || 0) || b.engagement - a.engagement);

  // Credibility: screened attached articles
  const verdicts = coverage
    .filter(it => it.inCase && it.signals?.status === 'completed')
    .map(it => ({ title: it.title, url: it.url, verdict: it.signals.verdict ?? null, composite: it.signals.composite ?? null }));
  const VERDICT_RANK = ['likely_coordinated', 'contested', 'corroborated', 'non_independent', 'single_source', 'satire', 'unverifiable_input', 'no_verifiable_claims'];
  const worstVerdict = verdicts.map(v => v.verdict).filter(Boolean)
    .sort((a, b) => VERDICT_RANK.indexOf(a!) - VERDICT_RANK.indexOf(b!))[0] || null;

  // Chronology: content by publication date + case milestones, oldest first
  const chronology: ChronologyRow[] = [];
  for (const it of coverage) {
    if (it.inCase && it.date) chronology.push({ date: it.date, kind: 'content', label: it.title, item: it });
  }
  for (const ev of inc.timeline || []) {
    const d = (ev.at || '').slice(0, 10);
    if (!d) continue;
    if (ev.kind === 'created') chronology.push({ date: d, time: (ev.at || '').slice(11, 16), kind: 'milestone', label: 'Case opened' });
    if (ev.kind === 'status_change') chronology.push({ date: d, time: (ev.at || '').slice(11, 16), kind: 'milestone', label: `Status: ${ev.old_value || '?'} → ${ev.new_value}` });
  }
  chronology.sort((a, b) => a.date.localeCompare(b.date) || (a.time || '').localeCompare(b.time || ''));

  return {
    coverage,
    agentFound: coverage.filter(it => !it.inCase),
    platforms, totalEngagement,
    accounts: accountList,
    verdicts, worstVerdict,
    chronology,
    otherEvidence,
  };
}

export const VERDICT_LABEL: Record<string, string> = {
  corroborated: 'independently corroborated',
  partial: 'partially verified',
  single_source: 'single source only',
  contested: 'claims contested',
  non_independent: 'echo coverage — not independent',
  unverifiable_input: 'could not be verified',
  satire: 'satire outlet',
  likely_coordinated: 'looks coordinated',
  no_verifiable_claims: 'no checkable claims',
};

/** true = the verdict indicates real risk for a brand story */
export const RISKY_VERDICTS = new Set(['corroborated', 'contested', 'likely_coordinated']);
