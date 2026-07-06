/**
 * Shared social analytics for the Social tab and the downloadable reports
 * (social listening report + master brand report) — one implementation so
 * the numbers match everywhere.
 *
 * Inputs are on-brand social posts (relevance-filtered upstream) shaped like
 * the /api/brand-watcher/social rows: { sentiment, platform, title, summary,
 * social_meta: { likes, reposts, comments, plays } }.
 */

const POS = new Set(['positive', 'optimistic', 'positive development']);
const NEG = new Set(['negative', 'pessimistic', 'concerning', 'concerned', 'critical', 'alarming']);

export const SENT_COLORS = { pos: '#10b981', neu: '#94a3b8', neg: '#ef4444' };

export function sentBucket(s: string | null | undefined): 'pos' | 'neu' | 'neg' | null {
  if (!s) return null;
  const lo = s.toLowerCase();
  if (POS.has(lo) || lo.includes('pos')) return 'pos';
  if (NEG.has(lo) || lo.includes('neg')) return 'neg';
  return 'neu';
}

/** Engagement proxy, mirroring the Social tab: reposts count double, plays /100. */
export function engagementOf(p: any): number {
  const m = p?.social_meta || {};
  return (m.likes || 0) + (m.reposts || 0) * 2 + (m.comments || 0) + (m.plays || 0) / 100;
}

const netOf = (m: { pos: number; neu: number; neg: number }): number | null => {
  const t = m.pos + m.neu + m.neg;
  return t ? Math.round(((m.pos - m.neg) / t) * 100) : null;
};

// ── Posted vs seen ───────────────────────────────────────────────────────────

export interface PostedVsSeen {
  posts: { pos: number; neu: number; neg: number };
  reach: { pos: number; neu: number; neg: number };
  postsNet: number | null;
  reachNet: number | null;
  /** reach-weighted net is ≥15 points worse than by volume */
  amplifiedNegatively: boolean;
}

export function computePostedVsSeen(posts: any[]): PostedVsSeen {
  const mix = { posts: { pos: 0, neu: 0, neg: 0 }, reach: { pos: 0, neu: 0, neg: 0 } };
  for (const p of posts) {
    const k = sentBucket(p.sentiment);
    if (!k) continue;
    mix.posts[k]++;
    mix.reach[k] += engagementOf(p) + 1; // +1: a post with zero engagement was still posted
  }
  const postsNet = netOf(mix.posts), reachNet = netOf(mix.reach);
  return {
    ...mix, postsNet, reachNet,
    amplifiedNegatively: postsNet != null && reachNet != null && reachNet <= postsNet - 15,
  };
}

// ── Sentiment & platform mix / best & worst network ──────────────────────────

export interface PlatformMixRow {
  pl: string;
  total: number;            // all on-brand posts on this network (incl. unscored)
  share: number;            // % of all posts
  pos: number; neu: number; neg: number;
  scored: number;
  net: number | null;
  low: boolean;             // <5 scored posts — muted, excluded from best/worst
}

export function computePlatformMix(posts: any[]): {
  rows: PlatformMixRow[];
  best: PlatformMixRow | null;
  worst: PlatformMixRow | null;
} {
  const by: Record<string, { total: number; pos: number; neu: number; neg: number }> = {};
  for (const p of posts) {
    const a = (by[p.platform || 'social'] ||= { total: 0, pos: 0, neu: 0, neg: 0 });
    a.total++;
    const k = sentBucket(p.sentiment);
    if (k) a[k]++;
  }
  const all = Math.max(1, posts.length);
  const rows = Object.entries(by).map(([pl, a]) => {
    const scored = a.pos + a.neu + a.neg;
    return {
      pl, ...a, scored,
      share: Math.round((a.total / all) * 100),
      net: scored ? Math.round(((a.pos - a.neg) / scored) * 100) : null,
      low: scored < 5,
    };
  }).sort((x, y) => y.total - x.total);
  const eligible = rows.filter(r => !r.low && r.net !== null);
  const best = eligible.length ? eligible.reduce((a, b) => (b.net! > a.net! ? b : a)) : null;
  const worst = eligible.length > 1 ? eligible.reduce((a, b) => (b.net! < a.net! ? b : a)) : null;
  return { rows, best, worst: worst && best && worst.pl === best.pl ? null : worst };
}

// ── What the negativity is about ─────────────────────────────────────────────
// MUST mirror the Social tab's SOCIAL_NEG_THEMES (BrandWatcherTab.tsx).

export const SOCIAL_NEG_THEMES: Array<{ key: string; label: string; re: RegExp }> = [
  { key: 'legal', label: 'Legal / IP', re: /\b(lawsuit|sued|sues|court|copyright|infringe\w*|piracy|legal action|settlement|dmca)\b/i },
  { key: 'integrity', label: 'Ethics / integrity', re: /\b(fraud\w*|scam|predatory|unethical|greed\w*|exploit\w*|plagiar\w*|retract\w*|paper mill)\b/i },
  { key: 'pricing', label: 'Pricing / fees', re: /\b(pricing|priced?|costs?|costly|expensive|fees?|apcs?|charged?|charges|unaffordable|overpriced)\b/i },
  { key: 'access', label: 'Access / paywalls', re: /\b(paywall\w*|open access|locked|inaccessible|subscription|log ?in wall)\b/i },
  { key: 'quality', label: 'Quality / errors', re: /\b(errors?|typos?|mistakes?|wrong answers?|poor quality|shoddy|misprint\w*|badly (written|edited))\b/i },
  { key: 'service', label: 'Service / support', re: /\b(customer service|support ticket|refunds?|no (reply|response)|unresponsive|complaints?)\b/i },
  { key: 'exams', label: 'Exams / education', re: /\b(exams?|marking|graded?|grading|a-levels?|gcses?|sats?|syllabus|past papers?)\b/i },
  { key: 'ai', label: 'AI / data use', re: /\b(ai|artificial intelligence|llms?|machine learning|training data|chatgpt|genai)\b/i },
];

export function computeNegThemes(posts: any[]): Array<{ key: string; label: string; n: number }> {
  const blobOf = (p: any) => `${p.title || ''} ${p.summary || ''}`;
  const negPosts = posts.filter(p => sentBucket(p.sentiment) === 'neg');
  const themes = SOCIAL_NEG_THEMES
    .map(t => ({ key: t.key, label: t.label, n: negPosts.filter(p => t.re.test(blobOf(p))).length }))
    .filter(t => t.n > 0).sort((a, b) => b.n - a.n);
  const otherN = negPosts.filter(p => !SOCIAL_NEG_THEMES.some(t => t.re.test(blobOf(p)))).length;
  if (otherN > 0) themes.push({ key: 'other', label: 'Other', n: otherN });
  return themes;
}

// ── Report HTML builders (inline styles — safe in both report stylesheets) ───

const escH = (s: unknown) => String(s ?? '')
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

const triBar = (m: { pos: number; neu: number; neg: number }) => {
  const t = Math.max(1, m.pos + m.neu + m.neg);
  const seg = (n: number, c: string) => n > 0
    ? `<span style="display:inline-block;height:100%;width:${(n / t * 100).toFixed(1)}%;background:${c}"></span>` : '';
  return `<span style="display:inline-flex;flex:1;height:10px;border-radius:5px;overflow:hidden;background:#eef0f5;min-width:80px">${seg(m.pos, SENT_COLORS.pos)}${seg(m.neu, SENT_COLORS.neu)}${seg(m.neg, SENT_COLORS.neg)}</span>`;
};

const netChipH = (v: number | null) => {
  const color = v == null ? '#94a3b8' : v > 0 ? '#15803d' : v < 0 ? '#b91c1c' : '#64748b';
  return `<span style="font-family:ui-monospace,monospace;font-weight:600;font-size:12px;color:${color};min-width:34px;text-align:right">${v == null ? '—' : `${v > 0 ? '+' : ''}${v}`}</span>`;
};

/** "Posted vs seen" card body: volume vs engagement-weighted sentiment. */
export function postedVsSeenHtml(pv: PostedVsSeen): string {
  if (pv.postsNet === null) return '';
  const row = (label: string, m: { pos: number; neu: number; neg: number }, net: number | null) =>
    `<div style="display:flex;align-items:center;gap:8px;margin:6px 0"><span style="font-size:11px;color:#888;flex:0 0 64px">${label}</span>${triBar(m)}${netChipH(net)}</div>`;
  const warn = pv.amplifiedNegatively
    ? `<p style="font-size:12px;color:#b45309;margin:8px 0 0">⚠ Negative posts are being amplified: sentiment by reach is ${pv.postsNet! - pv.reachNet!} points worse than by volume.</p>` : '';
  return `<p class="muted" style="margin:0 0 6px;font-size:12px">The same posts weighted by engagement — what the audience actually saw, not just what was posted.</p>
${row('By posts', pv.posts, pv.postsNet)}${row('By reach', pv.reach, pv.reachNet)}${warn}`;
}

/** "Sentiment & platform mix" card body + best/worst callout. */
export function platformMixHtml(mix: ReturnType<typeof computePlatformMix>): string {
  if (!mix.rows.length) return '';
  const callout = (mix.best || mix.worst)
    ? `<p style="font-size:12px;margin:0 0 8px">${mix.best ? `<strong style="color:#15803d">Best network:</strong> ${escH(mix.best.pl)} (${mix.best.net! > 0 ? '+' : ''}${mix.best.net})` : ''}${mix.best && mix.worst ? ' · ' : ''}${mix.worst ? `<strong style="color:#b91c1c">Worst network:</strong> ${escH(mix.worst.pl)} (${mix.worst.net! > 0 ? '+' : ''}${mix.worst.net})` : ''} <span class="muted" style="font-size:11px">(networks with ≥5 scored posts)</span></p>` : '';
  const rows = mix.rows.map(r => `
    <div style="display:flex;align-items:center;gap:8px;margin:5px 0${r.low ? ';opacity:.55' : ''}">
      <span style="font-size:12px;flex:0 0 84px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${escH(r.pl)}</span>
      <span style="font-size:11px;color:#888;flex:0 0 84px">${r.total} posts · ${r.share}%</span>
      ${triBar(r)}${netChipH(r.net)}${r.low ? '<span class="muted" style="font-size:10px">low sample</span>' : ''}
    </div>`).join('');
  return callout + rows;
}

/** "What the negativity is about" card body. */
export function negThemesHtml(themes: Array<{ label: string; n: number }>): string {
  if (!themes.length) return '';
  const max = Math.max(1, ...themes.map(t => t.n));
  return themes.map(t => `
    <div style="display:flex;align-items:center;gap:8px;margin:5px 0">
      <span style="font-size:12px;flex:0 0 130px">${escH(t.label)}</span>
      <span style="display:inline-flex;flex:1;height:10px;border-radius:5px;overflow:hidden;background:#eef0f5"><span style="display:inline-block;height:100%;width:${(t.n / max * 100).toFixed(0)}%;background:${SENT_COLORS.neg}"></span></span>
      <span style="font-size:11px;color:#888;min-width:24px;text-align:right">${t.n}</span>
    </div>`).join('');
}
