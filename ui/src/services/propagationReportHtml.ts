/**
 * Story Propagation Report — self-contained HTML for one screened article.
 *
 * Answers "how did this story spread?": the spread sequence across networks
 * (Bluesky live trace + cross-network pickup from xpoz corpus/live queries),
 * daily timeline, per-network stats + sample posts, amplification-integrity
 * read (concentration, fresh accounts, cohorts, reception), and the claim-
 * validation context so the reader knows WHAT spread, not just how far.
 *
 * Same house style as the other Brand Watcher reports: no external assets,
 * CSS bars instead of chart libs, safe to email, works offline.
 */

import type { BWArticleSignals } from './brandWatcherApi';

export interface PropagationReportData {
  articleTitle: string;
  articleUri: string;
  brandName?: string | null;
  signals: BWArticleSignals;      // completed row: signals + validation + reach + xnet
  generatedAt: string;            // ISO string (caller stamps it)
}

function esc(s: unknown): string {
  return String(s ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

const NET_LABEL: Record<string, string> = {
  bluesky: 'Bluesky', twitter: 'X / Twitter', reddit: 'Reddit',
  tiktok: 'TikTok', instagram: 'Instagram',
};
const netLabel = (k: string) => NET_LABEL[k] || (k.charAt(0).toUpperCase() + k.slice(1));

const SIG_TITLES: Record<string, string> = {
  veracity: 'Claim veracity', source_credibility: 'Source credibility',
  corroboration: 'Corroboration & independence', propagation: 'Propagation & reach',
  amplification_integrity: 'Amplification integrity',
};

export function buildPropagationReportHtml(d: PropagationReportData): string {
  const det = d.signals;
  const sigs: Record<string, any> = det.signals || {};
  const val: any = det.validation || null;
  const reach: any = det.reach || null;
  const xnet: any = (det as any).xnet || null;

  // ---- Per-network rollup (Bluesky live trace + xnet platforms) ----
  type Net = { key: string; posts: number; accounts?: number | null; engagement: number;
               first?: string | null; last?: string | null; origin: string; sample: any[] };
  const nets: Net[] = [];
  if (reach && reach.search_available !== false) {
    const t = reach.totals || {};
    nets.push({
      key: 'bluesky', posts: t.posts || 0, accounts: t.unique_accounts ?? null,
      engagement: (t.likes || 0) + (t.reposts || 0) + (t.replies || 0) + (t.quotes || 0),
      first: reach.first_seen || null, last: reach.last_seen || null,
      origin: 'live trace', sample: (reach.posts || []).slice(0, 8),
    });
  }
  for (const [k, p] of Object.entries<any>((xnet?.platforms) || {})) {
    const origins = new Set((p.sample || []).map((s: any) => s.origin));
    nets.push({
      key: k, posts: p.posts || 0, accounts: null, engagement: p.engagement || 0,
      first: p.first_seen || null, last: p.last_seen || null,
      origin: origins.has('live') && origins.has('corpus') ? 'live query + monitoring corpus'
        : origins.has('live') ? 'live query' : 'monitoring corpus',
      sample: p.sample || [],
    });
  }
  const withPosts = nets.filter(n => n.posts > 0);
  const totalPosts = withPosts.reduce((a, n) => a + n.posts, 0);
  const totalEng = withPosts.reduce((a, n) => a + n.engagement, 0);
  const exposure = reach?.total_followers || reach?.exposure || 0;

  // ---- Spread sequence (first-seen order across networks) ----
  const seq = withPosts.filter(n => n.first).sort((a, b) => String(a.first).localeCompare(String(b.first)));
  const seqHtml = seq.length ? seq.map((n, i) => `
    <div class="seq-row">
      <span class="seq-n">${i + 1}</span>
      <span class="seq-net">${esc(netLabel(n.key))}</span>
      <span class="seq-date">${esc(String(n.first).slice(0, 10))}</span>
      <span class="muted">${n.posts} post${n.posts !== 1 ? 's' : ''}${n.last && String(n.last).slice(0, 10) !== String(n.first).slice(0, 10) ? ` · active through ${esc(String(n.last).slice(0, 10))}` : ''}</span>
    </div>`).join('')
    : '<p class="muted">No dated pickup found — nothing to sequence.</p>';

  // ---- Daily timeline (Bluesky daily counts as CSS bars) ----
  const timeline: { day: string; count: number }[] = reach?.timeline || [];
  const maxDay = Math.max(1, ...timeline.map(t => t.count));
  const timelineHtml = timeline.length ? `
    <div class="tl">${timeline.map(t => `
      <div class="tl-col" title="${esc(t.day)}: ${t.count} post${t.count !== 1 ? 's' : ''}">
        <div class="tl-bar" style="height:${Math.max(4, (t.count / maxDay) * 70)}px"></div>
        <span class="tl-day">${esc(String(t.day).slice(5))}</span>
      </div>`).join('')}
    </div>
    <p class="muted" style="margin-top:4px">Bluesky posts per day (the live trace carries daily resolution; other networks show first/last seen in the sequence above).</p>`
    : '<p class="muted">No daily timeline available (no Bluesky pickup).</p>';

  // ---- Per-network detail sections ----
  const netHtml = withPosts.length ? withPosts.map(n => `
    <div class="card">
      <h3>${esc(netLabel(n.key))} <span class="muted" style="font-weight:400">— ${n.posts} post${n.posts !== 1 ? 's' : ''}${n.accounts != null ? ` by ${n.accounts} account${n.accounts !== 1 ? 's' : ''}` : ''} · ${n.engagement} engagement · source: ${esc(n.origin)}</span></h3>
      ${(n.sample || []).map((p: any) => `
        <div class="post">
          <div class="post-head">
            <span class="post-author">@${esc(p.handle || p.author || 'unknown')}</span>
            <span class="muted">${p.total_engagement ?? p.engagement ?? 0} eng${p.created_at || p.date ? ` · ${esc(String(p.created_at || p.date).slice(0, 10))}` : ''}</span>
            ${p.post_url || p.url ? `<a href="${esc(p.post_url || p.url)}" target="_blank" rel="noopener noreferrer">view post →</a>` : ''}
            ${p.origin ? `<span class="chip neu">${esc(p.origin)}</span>` : ''}
          </div>
          ${p.text ? `<p class="post-text">${esc(String(p.text).slice(0, 280))}</p>` : ''}
        </div>`).join('')}
    </div>`).join('')
    : '<div class="card"><p class="muted">No social pickup found on any covered network in the window.</p></div>';

  // ---- Amplification integrity ----
  const amp = sigs.amplification_integrity || null;
  const conc = reach?.concentration || {};
  const fresh = reach?.fresh_accounts || {};
  const cohorts = (reach?.cohorts?.cohorts) || [];
  const reception = reach?.reception || null;
  const recBits = reception?.sentiment_breakdown
    ? Object.entries<any>(reception.sentiment_breakdown).map(([k, v]) => `${esc(k)}: ${v}`).join(' · ') : '';
  const ampHtml = `
    ${amp ? `<p><strong>${amp.score != null ? `${amp.score}/100` : 'No data'}</strong> — ${esc(amp.summary)}</p>` : '<p class="muted">Not assessed.</p>'}
    <div class="fact-grid">
      ${conc.label ? `<div class="fact"><div class="eyebrow">Engagement concentration</div><div>${esc(conc.label)}${typeof conc.account_gini === 'number' ? ` (gini ${conc.account_gini.toFixed(2)})` : ''}</div></div>` : ''}
      ${fresh.resolved ? `<div class="fact"><div class="eyebrow">Fresh accounts</div><div>${fresh.fresh_count ?? 0} of ${fresh.resolved} younger than ${fresh.cutoff_days ?? 30}d${fresh.surge ? ' — <strong style="color:var(--neg)">surge</strong>' : ''}</div></div>` : ''}
      <div class="fact"><div class="eyebrow">Coordination cohorts</div><div>${cohorts.length ? `<strong style="color:var(--neg)">${cohorts.length} detected</strong>` : 'none detected'}</div></div>
      ${recBits ? `<div class="fact"><div class="eyebrow">Reply reception</div><div>${recBits}</div></div>` : ''}
    </div>`;

  // ---- Claims context ----
  const claimRows = (val?.claim_verifications || []).slice(0, 10).map((c: any) => `
    <div class="claim"><span class="chip ${c.status === 'supported' ? 'pos' : (c.status === 'contested' || c.status === 'unsupported') ? 'neg' : 'neu'}">${esc(c.status || 'uncertain')}</span> ${esc(c.claim_text || c.claim || '')}</div>`).join('');
  const verdict = det.verdict || null;
  const verdictCls = ['contested', 'non_independent', 'satire'].includes(verdict || '') ? 'neg'
    : verdict === 'corroborated' ? 'pos' : 'med';

  const brand = d.brandName ? ` · ${esc(d.brandName)}` : '';
  const prop = sigs.propagation || null;

  return `<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Propagation report — ${esc(d.articleTitle).slice(0, 80)}</title>
<style>
:root{--accent:#D6409F;--accent-tint:rgba(214,64,159,.12);--live:#16a34a;--amber:#E8A838;--neg:#dc2626;--ink:#1a1523;--muted:#6f6e77;--line:#e4e2e8;--card:#fff;--bg:#fbfafc}
*{box-sizing:border-box}body{margin:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:var(--ink);background:var(--bg);line-height:1.5}
main{max-width:860px;margin:0 auto;padding:28px 20px 60px}
h1{font-size:22px;margin:0 0 4px}h2{font-size:16px;margin:28px 0 10px;padding-bottom:6px;border-bottom:2px solid var(--accent-tint)}h3{font-size:13px;margin:0 0 8px}
.lead{color:var(--muted);font-size:13px;margin:0 0 6px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin-bottom:10px}
.muted{color:var(--muted);font-size:12px}
.chip{display:inline-block;font-size:11px;font-weight:600;padding:2px 8px;border-radius:99px;background:#eef0f5;color:#475569}
.chip.pos{background:#e7f6ec;color:#15803d}.chip.neg{background:#fdeaea;color:#b91c1c}.chip.med{background:#fbeedd;color:#b45309}.chip.neu{background:#eef0f5;color:#475569}
.stat-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin:12px 0}
.stat{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 12px}
.eyebrow{font-size:10px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin-bottom:2px}
.val{font-size:20px;font-weight:700}.sub{font-size:11px;color:var(--muted)}
.seq-row{display:flex;align-items:center;gap:10px;padding:6px 0;border-bottom:1px dashed var(--line);font-size:13px}
.seq-row:last-child{border-bottom:0}
.seq-n{width:22px;height:22px;border-radius:50%;background:var(--accent-tint);color:var(--accent);font-weight:700;font-size:11px;display:inline-flex;align-items:center;justify-content:center;flex-shrink:0}
.seq-net{font-weight:600;min-width:100px}.seq-date{font-variant-numeric:tabular-nums;color:var(--muted)}
.tl{display:flex;align-items:flex-end;gap:3px;padding-top:6px;overflow-x:auto}
.tl-col{display:flex;flex-direction:column;align-items:center;gap:2px;min-width:26px}
.tl-bar{width:16px;background:var(--accent);border-radius:3px 3px 0 0;opacity:.85}
.tl-day{font-size:9px;color:var(--muted);white-space:nowrap}
.post{border-top:1px dashed var(--line);padding:8px 0}
.post-head{display:flex;align-items:center;gap:8px;font-size:12px;flex-wrap:wrap}
.post-author{font-weight:600}.post-text{font-size:12px;color:#3f3e44;margin:4px 0 0;white-space:pre-wrap}
.post-head a{color:var(--accent);text-decoration:none;font-size:12px}
.fact-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px;margin-top:8px}
.fact{border:1px solid var(--line);border-radius:8px;padding:8px 10px;font-size:12px}
.claim{font-size:12px;padding:4px 0;border-bottom:1px dashed var(--line)}.claim:last-child{border-bottom:0}
.foot{margin-top:28px;font-size:11px;color:var(--muted);border-top:1px solid var(--line);padding-top:10px}
a{color:var(--accent)}
@media print{.card{break-inside:avoid}}
</style></head><body><main>
  <h1>Story propagation report</h1>
  <p class="lead">${esc(d.generatedAt.slice(0, 10))}${brand} · <a href="${esc(d.articleUri)}" target="_blank" rel="noopener noreferrer">${esc(d.articleTitle)}</a></p>
  <p><span class="chip ${verdictCls}">claim validation: ${esc(verdict || 'not run')}</span>
     ${det.composite_score != null ? `<span class="chip neu">screen composite ${det.composite_score}/100</span>` : ''}
     ${prop?.score != null ? `<span class="chip ${prop.band === 'bad' ? 'neg' : prop.band === 'warn' ? 'med' : 'pos'}">spread magnitude ${prop.score}/100</span>` : ''}</p>

  <h2>Spread at a glance</h2>
  <div class="stat-grid">
    <div class="stat"><div class="eyebrow">Total posts</div><div class="val">${totalPosts}</div><div class="sub">across ${withPosts.length} network${withPosts.length !== 1 ? 's' : ''}</div></div>
    <div class="stat"><div class="eyebrow">Total engagement</div><div class="val">${totalEng.toLocaleString()}</div><div class="sub">likes + reposts + replies</div></div>
    <div class="stat"><div class="eyebrow">Est. follower reach</div><div class="val">${exposure ? Number(exposure).toLocaleString() : '—'}</div><div class="sub">Bluesky, follower-weighted</div></div>
    <div class="stat"><div class="eyebrow">Networks covered</div><div class="val">${nets.length}</div><div class="sub">Bluesky live${xnet ? ` + ${Object.keys(xnet.platforms || {}).length || 'no'} via xpoz` : ''}</div></div>
  </div>

  <h2>Spread sequence</h2>
  <div class="card">${seqHtml}</div>

  <h2>Daily timeline</h2>
  <div class="card">${timelineHtml}</div>

  <h2>Pickup by network</h2>
  ${netHtml}

  <h2>Amplification integrity</h2>
  <div class="card">${ampHtml}</div>

  ${val ? `<h2>What spread: claims context</h2>
  <div class="card">
    <p style="font-size:13px">${esc(sigs.veracity?.summary || '')}</p>
    ${claimRows || '<p class="muted">No individual claims extracted.</p>'}
  </div>` : ''}

  <div class="foot">
    <p><strong>Method.</strong> Bluesky pickup is a live URL trace via the Aunoo analysis platform (deep mode: follower-weighted reach, fresh-account surge, coordination cohorts, reply reception). Other networks (X/Twitter, Reddit, TikTok, Instagram) come from ${xnet?.live_available ? 'live xpoz URL/headline queries plus ' : ''}the tenant's own social-monitoring corpus — a lower bound, not an exhaustive trace${xnet?.live_available ? ' (xpoz serves a rolling ~60-day window)' : ' (live cross-network query not provisioned on this run)'}. Facebook, Instagram and TikTok expose no public propagation-by-URL APIs; coverage there is best-effort. Engagement metrics are platform-native and not directly comparable across networks.</p>
    <p>Generated by AunooAI Brand Watcher · Five Signals screen of ${esc(String(det.updated_at || '').slice(0, 16)).replace('T', ' ')}</p>
  </div>
</main></body></html>`;
}

export function downloadPropagationReport(d: PropagationReportData): void {
  const html = buildPropagationReportHtml(d);
  const blob = new Blob([html], { type: 'text/html' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  const slug = d.articleTitle.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 50) || 'article';
  a.download = `propagation-${slug}-${d.generatedAt.slice(0, 10)}.html`;
  document.body.appendChild(a); a.click(); document.body.removeChild(a); URL.revokeObjectURL(url);
}
