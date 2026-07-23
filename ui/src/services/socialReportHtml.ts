/**
 * Self-contained SOCIAL report for Brand Watcher (distinct from the full brand report).
 * Focuses purely on social listening for one brand: sentiment, perception by network,
 * fans & critics, and the actual positive / negative posts driving sentiment.
 * Single downloadable .html file, inline CSS + no deps, AunooAI house style.
 */
import type { Brand, BWSocialResponse } from './brandWatcherApi';
import { stripSocialMarkdown } from './socialText';
import { computePostedVsSeen, computePlatformMix, computeNegThemes,
         postedVsSeenHtml, platformMixHtml, negThemesHtml } from './socialAnalytics';

export interface SocialReportData {
  brand?: Brand;
  daysBack: number;
  social: BWSocialResponse | null;
  generatedAt: string; // ISO string (caller stamps it)
}

function esc(s: unknown): string {
  return String(s ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}
function sentClass(s: string | null | undefined): 'pos' | 'neg' | 'neu' {
  const lo = (s || '').toLowerCase();
  if (lo.includes('pos')) return 'pos';
  if (lo.includes('neg')) return 'neg';
  return 'neu';
}
function authorOf(p: any): string {
  const a = p.social_meta?.author;
  if (a) return a;
  const m = (p.title || '').match(/@([\w.\-]+)/);
  return m ? m[1] : '';
}
function bodyOf(p: any): string {
  const body = stripSocialMarkdown(p.summary || '').trim();
  if (body) return body;
  return stripSocialMarkdown((p.title || '').replace(/^Post by @[\w.\-]+\s*/i, '')).trim() || '(no text)';
}

export function buildSocialReportHtml(d: SocialReportData): string {
  const brandName = d.brand?.display_name || 'All brands';
  const period = d.daysBack === 0 ? 'All time' : `Last ${d.daysBack} days`;
  const gen = esc(d.generatedAt.replace('T', ' ').slice(0, 16));

  // On-brand posts for this brand only.
  const posts = (d.social?.posts || []).filter(p =>
    (p.relevance ?? 0) >= 0.4 && (!d.brand || (p.topic || '') === `Brand Monitoring ${d.brand.display_name}`));

  let pos = 0, neg = 0, neu = 0;
  for (const p of posts) { if (!p.sentiment) continue; const c = sentClass(p.sentiment); if (c === 'pos') pos++; else if (c === 'neg') neg++; else neu++; }
  const scored = pos + neg + neu;
  const net = scored ? Math.round(((pos - neg) / scored) * 100) : null;

  // Perception by network.
  const plat: Record<string, { pos: number; neg: number; neu: number; total: number }> = {};
  for (const p of posts) {
    if (!p.sentiment) continue;
    const a = (plat[p.platform || 'social'] ||= { pos: 0, neg: 0, neu: 0, total: 0 });
    const c = sentClass(p.sentiment);
    if (c === 'pos') a.pos++; else if (c === 'neg') a.neg++; else a.neu++;
    a.total++;
  }
  // Networks with <5 scored posts are muted + sorted last — a +100 from a single
  // post is noise, not signal, and shouldn't outrank a large network.
  const MIN_PERCEPTION_N = 5;
  const perception = Object.entries(plat).map(([pl, a]) => {
    const sc = a.pos + a.neg + a.neu;
    return { pl, ...a, net: sc ? Math.round(((a.pos - a.neg) / sc) * 100) : null, low: sc < MIN_PERCEPTION_N };
  }).sort((x, y) => (Number(x.low) - Number(y.low)) || (y.net ?? -999) - (x.net ?? -999));

  // Shared analytics (identical math to the Social tab)
  const pvSeen = computePostedVsSeen(posts);
  const platMix = computePlatformMix(posts);
  const negThemes = computeNegThemes(posts);

  // Fans & Critics (own-brand handles excluded from fans).
  const normH = (s: string) => (s || '').toLowerCase().replace(/[^a-z0-9]/g, '');
  const ownToks = d.brand ? Array.from(new Set([d.brand.name, ...(d.brand.brand_keywords || [])].map(normH).filter(t => t.length >= 3))) : [];
  const isOwn = (h: string) => { const lead = normH((h || '').split('.')[0]); return !!lead && ownToks.some(t => lead.startsWith(t)); };
  const byAuthor: Record<string, { a: string; pos: number; neg: number; neu: number; total: number }> = {};
  for (const p of posts) {
    if (!p.sentiment) continue;
    const h = authorOf(p); if (!h || h === 'unknown' || h.includes(':')) continue;
    const x = (byAuthor[h.toLowerCase()] ||= { a: h, pos: 0, neg: 0, neu: 0, total: 0 });
    const c = sentClass(p.sentiment);
    if (c === 'pos') x.pos++; else if (c === 'neg') x.neg++; else x.neu++;
    x.total++;
  }
  const authors = Object.values(byAuthor).map(x => ({ ...x, net: x.pos - x.neg, own: isOwn(x.a) }));
  const fans = authors.filter(x => x.net > 0 && !x.own).sort((p1, q) => q.net - p1.net || q.pos - p1.pos).slice(0, 12);
  const critics = authors.filter(x => x.net < 0).sort((p1, q) => p1.net - q.net || q.neg - p1.neg).slice(0, 12);

  // Actual positive / negative posts (the content driving sentiment). Default order:
  // engagement (reach) first — a negative post with 500 reposts matters far more than
  // one nobody saw — with relevance as tiebreak. Sortable client-side.
  const engagementOf = (p: any) => {
    const sm = p.social_meta || {};
    return (sm.likes || 0) + (sm.reposts || 0) * 2 + (sm.comments || 0) + (sm.plays || 0) / 100;
  };
  const byImpact = (a: any, b: any) => engagementOf(b) - engagementOf(a) || (b.relevance ?? 0) - (a.relevance ?? 0);
  const topPos = posts.filter(p => sentClass(p.sentiment) === 'pos' && p.sentiment).sort(byImpact).slice(0, 25);
  const topNeg = posts.filter(p => sentClass(p.sentiment) === 'neg' && p.sentiment).sort(byImpact).slice(0, 25);
  const totPos = posts.filter(p => p.sentiment && sentClass(p.sentiment) === 'pos').length;
  const totNeg = posts.filter(p => p.sentiment && sentClass(p.sentiment) === 'neg').length;

  const stat = (eyebrow: string, value: string, sub = '', cls = '') =>
    `<div class="stat"><div class="eyebrow">${esc(eyebrow)}</div><div class="val ${cls}">${esc(value)}</div>${sub ? `<div class="sub">${esc(sub)}</div>` : ''}</div>`;

  const authorRow = (x: { a: string; pos: number; neu: number; neg: number; total: number; net: number }, kind: 'fan' | 'crit') => {
    const tot = x.total || 1;
    return `<div class="auth">
      <span class="auth-h">@${esc(x.a)}</span>
      <span class="sbar" title="${x.pos}+ ${x.neu}· ${x.neg}−">
        <span class="pos" style="width:${(x.pos / tot * 100).toFixed(0)}%"></span>
        <span class="neu" style="width:${(x.neu / tot * 100).toFixed(0)}%"></span>
        <span class="neg" style="width:${(x.neg / tot * 100).toFixed(0)}%"></span>
      </span>
      <span class="chip ${kind === 'fan' ? 'pos' : 'neg'}">${x.net > 0 ? '+' : ''}${x.net}</span>
      <span class="cnt">${x.total}</span>
    </div>`;
  };

  const PLAT_COLORS: Record<string, string> = { twitter: '#1d9bf0', bluesky: '#0085ff', reddit: '#ff4500', instagram: '#e1306c', tiktok: '#111', social: '#6b7280' };
  const postCard = (p: any) => {
    const h = authorOf(p);
    const s = sentClass(p.sentiment);
    const sm = p.social_meta || {};
    const rel = p.relevance != null ? `<span class="rel">rel ${p.relevance.toFixed(2)}</span>` : '';
    const date = p.publication_date ? esc(p.publication_date.slice(0, 10)) : '';
    const kws = (p.matched_keywords || []).map((k: string) => `<span class="kw">#${esc(k)}</span>`).join('');
    const eng = ([['♥', sm.likes], ['↻', sm.reposts], ['💬', sm.comments], ['▶', sm.plays]] as Array<[string, number | undefined]>)
      .filter(([, v]) => v != null && v > 0)
      .map(([i, v]) => `<span class="eng">${i} ${Number(v).toLocaleString()}</span>`).join('');
    const platColor = PLAT_COLORS[(p.platform || 'social') as string] || PLAT_COLORS.social;
    return `<div class="post ${s}" data-text="${esc((bodyOf(p) + ' ' + h).toLowerCase())}" data-eng="${engagementOf(p)}" data-rel="${p.relevance ?? 0}" data-date="${esc(p.publication_date || '')}">
      <div class="post-head">
        <span class="plat" style="background:${platColor}18;color:${platColor}">${esc(p.platform || 'social')}</span>
        <a class="post-h" href="${esc(p.uri)}" target="_blank" rel="noopener noreferrer">${h ? '@' + esc(h) : 'view post'}</a>
        ${sm.subreddit ? `<span class="date">r/${esc(sm.subreddit)}</span>` : ''}
        ${date ? `<span class="date">${date}</span>` : ''}${rel}
        <span class="spacer"></span>${eng}
      </div>
      <div class="post-body">${esc(bodyOf(p))}</div>
      ${kws ? `<div class="post-kws">${kws}</div>` : ''}
    </div>`;
  };
  const sortBar = (id: string) => `<div class="sortbar">
      <label>Sort:</label>
      <select data-sort-for="${id}">
        <option value="eng">Reach (engagement)</option>
        <option value="rel">Relevance</option>
        <option value="date">Newest</option>
      </select></div>`;

  const perceptionHtml = perception.length ? perception.map(pv => {
    const n = pv.net ?? 0;
    const sc = pv.pos + pv.neu + pv.neg;
    const posPct = sc ? (pv.pos / sc) * 50 : 0;   // half-track = 100%
    const negPct = sc ? (pv.neg / sc) * 50 : 0;
    const counts = `${pv.pos}+ ${pv.neu}· ${pv.neg}−`;
    return `<div class="bar-row${pv.low ? ' low-n' : ''}" title="${counts}${pv.low ? ' — low sample' : ''}">
      <span class="bar-label">${esc(pv.pl)}${pv.low ? ' <span class="lown-tag">low sample</span>' : ''}</span>
      <span class="dbar"><span class="n" style="width:${negPct.toFixed(1)}%"></span><span class="p" style="width:${posPct.toFixed(1)}%"></span><span class="c"></span></span>
      <span class="bar-val">${pv.net == null ? 'n/a' : (n > 0 ? '+' : '') + n} · ${counts}</span></div>`;
  }).join('') : '<p class="muted">No on-brand social posts in range.</p>';

  const fansHtml = fans.length ? fans.map(x => authorRow(x, 'fan')).join('') : '<p class="muted">No net-positive third-party authors.</p>';
  const criticsHtml = critics.length ? critics.map(x => authorRow(x, 'crit')).join('') : '<p class="muted">No net-negative authors.</p>';
  const posHtml = topPos.length ? topPos.map(postCard).join('') : '<p class="muted">No positive posts in range.</p>';
  const negHtml = topNeg.length ? topNeg.map(postCard).join('') : '<p class="muted">No negative posts in range.</p>';
  const sentTot = scored || 1;

  return `<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Social Report — ${esc(brandName)}</title>
<style>
:root{--accent:#D6409F;--accent-tint:rgba(214,64,159,.12);--live:#16a34a;--neg:#dc2626;
--bg:#ECEDF3;--card:#fff;--border:#e0e1e9;--text:#1a1a2e;--text2:#3d3a4a;--muted:#65636d;--r:12px;}
*{box-sizing:border-box}
body{margin:0;font-family:Inter,-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:var(--bg);color:var(--text);font-size:14px;line-height:1.55}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
.topnav{position:sticky;top:0;z-index:10;background:rgba(255,255,255,.92);backdrop-filter:blur(8px);border-bottom:1px solid var(--border);padding:10px 20px;display:flex;align-items:center;gap:14px;flex-wrap:wrap}
.topnav .brand{font-weight:700;font-size:15px}.topnav .brand b{color:var(--accent)}
.topnav .meta{color:var(--muted);font-size:12px}
.nav{display:flex;gap:4px;margin-left:auto;flex-wrap:wrap}
.nav a{padding:5px 11px;border-radius:999px;font-size:12.5px;color:var(--text2);font-weight:500}
.nav a:hover{background:var(--accent-tint);color:var(--accent);text-decoration:none}
.search{padding:5px 10px;border:1px solid var(--border);border-radius:999px;font-size:12.5px;width:170px;background:#fff}
main{max-width:1040px;margin:0 auto;padding:22px 20px 60px}
h1{font-size:22px;margin:6px 0 2px}.lead{color:var(--muted);margin:0 0 18px}
section{margin:26px 0;scroll-margin-top:64px}
section>h2{font-size:13px;text-transform:uppercase;letter-spacing:.06em;color:var(--accent);margin:0 0 12px;font-weight:700}
.card{background:var(--card);border:1px solid var(--border);border-radius:var(--r);padding:16px 18px;margin-bottom:14px}
.card h3{font-size:13.5px;margin:0 0 12px;color:var(--text)}
.two-col{display:grid;grid-template-columns:1fr 1fr;gap:14px}.two-col .card{margin-bottom:0}
.stat-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:14px}
.stat{background:var(--card);border:1px solid var(--border);border-radius:var(--r);padding:14px 16px}
.stat .eyebrow{font-size:10.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);font-weight:600}
.stat .val{font-size:26px;font-weight:700;margin-top:4px;line-height:1.1}.stat .sub{font-size:11.5px;color:var(--muted);margin-top:2px}
.val.pos{color:var(--live)}.val.neg{color:var(--neg)}
.bar-row{display:flex;align-items:center;gap:10px;padding:3px 0}
.bar-label{font-size:12.5px;color:var(--text2);width:110px;flex-shrink:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.bar-track{flex:1;height:14px;background:#eef0f5;border-radius:999px;overflow:hidden}
.bar-fill{display:block;height:100%;border-radius:999px}
.bar-val{font-size:11.5px;color:var(--muted);width:130px;text-align:right;flex-shrink:0;font-variant-numeric:tabular-nums}
.low-n{opacity:.5}
.lown-tag{font-size:9.5px;color:var(--muted);background:#f1f1f5;padding:0 5px;border-radius:999px;font-style:italic}
.dbar{flex:1;height:14px;background:#eef0f5;border-radius:999px;overflow:hidden;position:relative}
.dbar .n{position:absolute;right:50%;top:0;bottom:0;background:var(--neg)}
.dbar .p{position:absolute;left:50%;top:0;bottom:0;background:var(--live)}
.dbar .c{position:absolute;left:50%;top:0;bottom:0;width:1px;background:#d5d7e0}
.sbar{height:12px;border-radius:999px;overflow:hidden;display:flex;background:#eef0f5;flex:0 0 80px}
.sbar .pos{background:var(--live)}.sbar .neu{background:#94a3b8}.sbar .neg{background:var(--neg)}
.auth{display:flex;align-items:center;gap:9px;padding:5px 0;border-bottom:1px solid #f4f4f7}
.auth:last-child{border-bottom:none}
.auth-h{flex:1;font-size:12.5px;font-weight:600;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.chip{font-size:10.5px;padding:1px 7px;border-radius:999px;font-weight:600}
.chip.pos{background:#e7f6ec;color:#15803d}.chip.neg{background:#fdeaea;color:#b91c1c}
.cnt{font-size:11px;color:var(--muted);width:22px;text-align:right}
.post{border-bottom:1px solid #f0f0f4;padding:9px 0 9px 10px;border-left:3px solid transparent;margin-bottom:2px}
.post:last-child{border-bottom:none}
.post.pos{border-left-color:var(--live)}.post.neg{border-left-color:var(--neg)}
.post-head{display:flex;align-items:center;gap:8px;margin-bottom:3px;flex-wrap:wrap}
.plat{font-size:10px;text-transform:uppercase;letter-spacing:.04em;padding:1px 7px;border-radius:999px;font-weight:600}
.spacer{flex:1}
.eng{font-size:11px;color:var(--muted);font-variant-numeric:tabular-nums}
.h-sub{font-size:11px;color:var(--muted);text-transform:none;letter-spacing:0;font-weight:500;margin-left:8px}
.sortbar{display:flex;align-items:center;gap:7px;justify-content:flex-end;margin-bottom:6px}
.sortbar label{font-size:11px;color:var(--muted)}
.sortbar select{font-size:12px;padding:3px 8px;border:1px solid var(--border);border-radius:8px;background:#fff;color:var(--text2)}
.post-h{font-size:12px;font-weight:600}.date,.rel{font-size:11px;color:var(--muted)}
.post-body{font-size:13px;color:var(--text2);white-space:pre-wrap;word-break:break-word}
.post-kws{margin-top:4px;display:flex;gap:5px;flex-wrap:wrap}
.kw{font-size:10px;color:var(--muted);background:#f1f1f5;padding:1px 6px;border-radius:999px}
.muted{color:var(--muted);font-size:12.5px;font-style:italic}
.col{max-height:none}
footer{margin-top:40px;padding-top:16px;border-top:1px solid var(--border);color:var(--muted);font-size:11.5px;text-align:center}
@media(max-width:760px){.stat-grid{grid-template-columns:1fr 1fr}.two-col{grid-template-columns:1fr}}
@media print{.topnav{position:static}.nav,.search{display:none}}
</style></head>
<body>
<header class="topnav">
  <span class="brand">Social Report · <b>${esc(brandName)}</b></span>
  <span class="meta">${esc(period)} · generated ${gen}</span>
  <nav class="nav">
    <a href="#overview">Overview</a>
    <a href="#voices">Fans &amp; Critics</a>
    <a href="#positive">Positive</a>
    <a href="#negative">Negative</a>
  </nav>
  <input class="search" id="q" type="search" placeholder="Search posts…" />
</header>
<main>
  <h1>${esc(brandName)} — Social Report</h1>
  <p class="lead">${esc(period)} · ${posts.length.toLocaleString()} on-brand social posts (relevance ≥ 0.4)</p>

  <section id="overview">
    <h2>Overview</h2>
    <div class="stat-grid">
      ${stat('On-brand posts', posts.length.toLocaleString(), period)}
      ${stat('Net sentiment', net == null ? '—' : `${net > 0 ? '+' : ''}${net}`, '% pos − % neg', net == null ? '' : net > 0 ? 'pos' : net < 0 ? 'neg' : '')}
      ${stat('Fans / Critics', `${fans.length} / ${critics.length}`, 'net-pos / net-neg authors')}
      ${stat('Positive / Negative', `${pos} / ${neg}`, `${neu} neutral`)}
    </div>
    <div class="card"><h3>Sentiment split</h3>
      <div class="bar-row"><span class="bar-label">All posts</span>
        <span class="sbar" style="flex:1;height:16px">
          <span class="pos" style="width:${(pos / sentTot * 100).toFixed(1)}%" title="Positive ${pos}"></span>
          <span class="neu" style="width:${(neu / sentTot * 100).toFixed(1)}%" title="Neutral ${neu}"></span>
          <span class="neg" style="width:${(neg / sentTot * 100).toFixed(1)}%" title="Negative ${neg}"></span>
        </span>
        <span class="bar-val">${pos}+ ${neu}· ${neg}−</span></div>
    </div>
    <div class="card"><h3>Perception by network — net sentiment <span class="muted">(% positive − % negative of scored posts; neutrals count in the base, so many neutrals pull the net toward 0)</span></h3>${perceptionHtml}</div>
    ${postedVsSeenHtml(pvSeen) ? `<div class="card"><h3>Posted vs seen <span class="muted">(engagement-weighted)</span></h3>${postedVsSeenHtml(pvSeen)}</div>` : ''}
    ${platformMixHtml(platMix) ? `<div class="card"><h3>Sentiment &amp; platform mix</h3>${platformMixHtml(platMix)}</div>` : ''}
    ${negThemesHtml(negThemes) ? `<div class="card"><h3>What the negativity is about <span class="muted">(theme keywords over negative posts)</span></h3>${negThemesHtml(negThemes)}</div>` : ''}
  </section>

  <section id="voices">
    <h2>Fans &amp; Critics</h2>
    <div class="two-col">
      <div class="card"><h3>😊 Top fans <span class="muted">(own accounts excluded)</span></h3>${fansHtml}</div>
      <div class="card"><h3>😠 Top critics</h3>${criticsHtml}</div>
    </div>
  </section>

  <section id="positive">
    <h2>👍 Positive posts <span class="h-sub">top ${topPos.length} of ${totPos} · ordered by reach</span></h2>
    <div class="card">${topPos.length ? sortBar('pos-list') : ''}<div id="pos-list">${posHtml}</div></div>
  </section>

  <section id="negative">
    <h2>👎 Negative posts <span class="h-sub">top ${topNeg.length} of ${totNeg} · ordered by reach</span></h2>
    <div class="card">${topNeg.length ? sortBar('neg-list') : ''}<div id="neg-list">${negHtml}</div></div>
  </section>

  <footer>Generated ${gen} · Powered by AunooAI · Social listening report</footer>
</main>
<script>
(function(){
  var q=document.getElementById('q');
  if(q){q.addEventListener('input',function(){
    var t=q.value.trim().toLowerCase();
    document.querySelectorAll('.post').forEach(function(el){
      el.style.display=(!t||(el.getAttribute('data-text')||'').indexOf(t)>-1)?'':'none';
    });
  });}
  // per-section sorting of post lists (reach / relevance / newest)
  document.querySelectorAll('select[data-sort-for]').forEach(function(sel){
    sel.addEventListener('change',function(){
      var list=document.getElementById(sel.getAttribute('data-sort-for'));
      if(!list) return;
      var key=sel.value;
      var items=Array.prototype.slice.call(list.querySelectorAll('.post'));
      items.sort(function(a,b){
        if(key==='date') return (b.getAttribute('data-date')||'').localeCompare(a.getAttribute('data-date')||'');
        var ka=parseFloat(a.getAttribute('data-'+key)||'0'), kb=parseFloat(b.getAttribute('data-'+key)||'0');
        return kb-ka;
      });
      items.forEach(function(el){list.appendChild(el);});
    });
  });
})();
</script>
</body></html>`;
}

export function downloadSocialReport(d: SocialReportData): void {
  const html = buildSocialReportHtml(d);
  const blob = new Blob([html], { type: 'text/html' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  const slug = (d.brand?.display_name || 'all').toLowerCase().replace(/\s+/g, '-');
  a.download = `social-report-${slug}-${d.generatedAt.slice(0, 10)}.html`;
  document.body.appendChild(a); a.click(); document.body.removeChild(a); URL.revokeObjectURL(url);
}
