/**
 * Self-contained interactive HTML report for Brand Watcher.
 * Produces a single downloadable .html file (inline CSS + vanilla JS, no deps),
 * matching the AunooAI report house style (Consensus / Threat Intelligence):
 * design-token CSS, card layout, CSS-positioned bars, <details> accordions,
 * and progressive-enhancement JS for section nav + search.
 */
import type {
  Brand, BWStats, BWCategory, BWSentimentTrend, BWAlert,
  BWComparison, BWShareOfVoice, BWSocialResponse, BWSavedNarrative,
} from './brandWatcherApi';
import { stripSocialMarkdown } from './socialText';

export interface BrandReportData {
  brand?: Brand;
  daysBack: number;
  stats: BWStats | null;
  categories: BWCategory[];
  sentimentTrends: BWSentimentTrend[];
  alerts: BWAlert[];
  comparison: BWComparison[];
  shareOfVoice: BWShareOfVoice[];
  narrative: BWSavedNarrative | null;
  social: BWSocialResponse | null;
  generatedAt: string; // ISO string (caller stamps it — no Date in module scope)
}

const NEG = new Set(['negative', 'pessimistic', 'concerning', 'concerned', 'critical', 'alarming']);
const POS = new Set(['positive', 'optimistic', 'positive development']);

function esc(s: unknown): string {
  return String(s ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

/** Minimal, safe markdown → HTML for the LLM narrative (## headers, **bold**, links, lists). */
function mdToHtml(md: string): string {
  const lines = (md || '').replace(/\r/g, '').split('\n');
  const out: string[] = [];
  let inList = false;
  const inline = (t: string) => esc(t)
    .replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|[^*])\*([^*]+)\*/g, '$1<em>$2</em>');
  const closeList = () => { if (inList) { out.push('</ul>'); inList = false; } };
  for (const raw of lines) {
    const line = raw.trimEnd();
    if (!line.trim()) { closeList(); continue; }
    let m: RegExpMatchArray | null;
    if ((m = line.match(/^###\s+(.*)/))) { closeList(); out.push(`<h4>${inline(m[1])}</h4>`); }
    else if ((m = line.match(/^##\s+(.*)/))) { closeList(); out.push(`<h3>${inline(m[1])}</h3>`); }
    else if ((m = line.match(/^#\s+(.*)/))) { closeList(); out.push(`<h2>${inline(m[1])}</h2>`); }
    else if ((m = line.match(/^[-*]\s+(.*)/))) { if (!inList) { out.push('<ul>'); inList = true; } out.push(`<li>${inline(m[1])}</li>`); }
    else { closeList(); out.push(`<p>${inline(line)}</p>`); }
  }
  closeList();
  return out.join('\n');
}

function sentClass(s: string | null | undefined): string {
  const lo = (s || '').toLowerCase();
  if (POS.has(lo) || lo.includes('pos')) return 'pos';
  if (NEG.has(lo) || lo.includes('neg')) return 'neg';
  return 'neu';
}

function statCard(eyebrow: string, value: string, sub = ''): string {
  return `<div class="stat"><div class="eyebrow">${esc(eyebrow)}</div><div class="val">${esc(value)}</div>${sub ? `<div class="sub">${esc(sub)}</div>` : ''}</div>`;
}

function articleRow(a: { uri: string; title: string; publication_date: string | null; sentiment: string | null; news_source: string | null }): string {
  const date = a.publication_date ? esc(a.publication_date.slice(0, 10)) : '';
  const src = a.news_source ? esc(a.news_source) : '';
  const sent = a.sentiment ? `<span class="chip ${sentClass(a.sentiment)}">${esc(a.sentiment)}</span>` : '';
  const text = `${a.title || ''} ${src}`.toLowerCase();
  return `<div class="art" data-text="${esc(text)}">
    <a href="${esc(a.uri)}" target="_blank" rel="noopener noreferrer" class="art-title">${esc(a.title || '(untitled)')}</a>
    <span class="art-meta">${sent}${src ? `<span class="src">${src}</span>` : ''}${date ? `<span class="date">${date}</span>` : ''}</span>
  </div>`;
}

export function buildBrandWatcherReportHtml(d: BrandReportData): string {
  const brandName = d.brand?.display_name || 'All Brands';
  const period = d.daysBack === 0 ? 'All time' : `Last ${d.daysBack} days`;
  const gen = esc(d.generatedAt.replace('T', ' ').slice(0, 16));

  // ---- Overview ----
  const catSorted = [...d.categories].sort((a, b) => b.article_count - a.article_count);
  const totalCatArticles = catSorted.reduce((s, c) => s + c.article_count, 0) || 1;
  const totalArticles = d.stats?.total_articles ?? totalCatArticles;
  const topCat = catSorted[0]?.category || '—';

  // ---- Risk (mirrors the in-app computation, relevance-filtered upstream) ----
  const alertsSorted = [...d.alerts].sort((a, b) => b.spike_ratio - a.spike_ratio);
  const highAlerts = d.alerts.filter(a => a.severity === 'high').length;

  // ---- Sentiment by category ----
  const byCat: Record<string, { pos: number; neu: number; neg: number }> = {};
  for (const t of d.sentimentTrends) {
    const c = (byCat[t.category] ||= { pos: 0, neu: 0, neg: 0 });
    for (const [s, cnt] of Object.entries(t.sentiments || {})) {
      const lo = s.toLowerCase();
      if (POS.has(lo)) c.pos += cnt as number; else if (NEG.has(lo)) c.neg += cnt as number; else c.neu += cnt as number;
    }
  }

  // ---- Social ---- (scoped to THIS brand, on-brand posts only)
  const soc = d.social;
  let socNet: number | null = null;
  const socTop = soc ? soc.posts.filter(p => (p.relevance ?? 0) >= 0.4 && (!d.brand || (p.topic || '') === `Brand Monitoring ${d.brand.display_name}`)) : [];
  let socPos = 0, socNeg = 0, socNeu = 0;
  if (soc) {
    for (const post of socTop) {
      if (!post.sentiment) continue;
      const c = sentClass(post.sentiment);
      if (c === 'pos') socPos++; else if (c === 'neg') socNeg++; else socNeu++;
    }
    const sc = socPos + socNeg + socNeu;
    socNet = sc ? Math.round(((socPos - socNeg) / sc) * 100) : null;
  }

  // Perception by network — net sentiment (% pos − % neg) per platform.
  const socPlat: Record<string, { pos: number; neg: number; neu: number; total: number }> = {};
  for (const p of socTop) {
    if (!p.sentiment) continue;
    const pl = p.platform || 'social';
    const a = (socPlat[pl] ||= { pos: 0, neg: 0, neu: 0, total: 0 });
    const c = sentClass(p.sentiment);
    if (c === 'pos') a.pos++; else if (c === 'neg') a.neg++; else a.neu++;
    a.total++;
  }
  // Networks with <5 scored posts are muted + sorted last (single-post +100s are noise).
  const socPerception = Object.entries(socPlat).map(([pl, a]) => {
    const sc = a.pos + a.neg + a.neu;
    return { pl, ...a, net: sc ? Math.round(((a.pos - a.neg) / sc) * 100) : null, low: sc < 5 };
  }).sort((x, y) => (Number(x.low) - Number(y.low)) || (y.net ?? -999) - (x.net ?? -999));

  // Fans & Critics — authors ranked by net sentiment; own-brand handles excluded from fans.
  const normH = (s: string) => (s || '').toLowerCase().replace(/[^a-z0-9]/g, '');
  const ownToks = d.brand ? Array.from(new Set([d.brand.name, ...(d.brand.brand_keywords || [])].map(normH).filter(t => t.length >= 3))) : [];
  const isOwnH = (h: string) => { const lead = normH((h || '').split('.')[0]); return !!lead && ownToks.some(t => lead.startsWith(t)); };
  const authorOfP = (p: any) => { const a = p.social_meta?.author; if (a) return a; const m = (p.title || '').match(/@([\w.\-]+)/); return m ? m[1] : ''; };
  const socByAuthor: Record<string, { a: string; pos: number; neg: number; neu: number; total: number }> = {};
  for (const p of socTop) {
    if (!p.sentiment) continue;
    const h = authorOfP(p); if (!h || h === 'unknown' || h.includes(':')) continue;
    const x = (socByAuthor[h.toLowerCase()] ||= { a: h, pos: 0, neg: 0, neu: 0, total: 0 });
    const c = sentClass(p.sentiment);
    if (c === 'pos') x.pos++; else if (c === 'neg') x.neg++; else x.neu++;
    x.total++;
  }
  const socAuthors = Object.values(socByAuthor).map(x => ({ ...x, net: x.pos - x.neg, own: isOwnH(x.a) }));
  const socFans = socAuthors.filter(x => x.net > 0 && !x.own).sort((p, q) => q.net - p.net || q.pos - p.pos).slice(0, 10);
  const socCritics = socAuthors.filter(x => x.net < 0).sort((p, q) => p.net - q.net || q.neg - p.neg).slice(0, 10);

  const catBars = catSorted.map(c => `
    <div class="bar-row">
      <span class="bar-label">${esc(c.category)}</span>
      <span class="bar-track"><span class="bar-fill" style="width:${((c.article_count / totalCatArticles) * 100).toFixed(1)}%"></span></span>
      <span class="bar-val">${c.article_count} · ${c.percentage.toFixed(0)}%</span>
    </div>`).join('');

  const sentBars = Object.entries(byCat).map(([cat, s]) => {
    const tot = s.pos + s.neu + s.neg || 1;
    return `<div class="bar-row">
      <span class="bar-label">${esc(cat)}</span>
      <span class="sbar">
        <span style="width:${(s.pos / tot * 100).toFixed(1)}%" class="pos" title="Positive ${s.pos}"></span>
        <span style="width:${(s.neu / tot * 100).toFixed(1)}%" class="neu" title="Neutral ${s.neu}"></span>
        <span style="width:${(s.neg / tot * 100).toFixed(1)}%" class="neg" title="Negative ${s.neg}"></span>
      </span>
      <span class="bar-val">${s.pos + s.neu + s.neg}</span>
    </div>`;
  }).join('') || '<p class="muted">No sentiment data.</p>';

  const sovBars = d.shareOfVoice.map(s => `
    <div class="bar-row">
      <span class="bar-label"><span class="dot" style="background:${esc(s.color || '#6b7280')}"></span>${esc(s.brand_name)}</span>
      <span class="bar-track"><span class="bar-fill" style="width:${s.percentage.toFixed(1)}%;background:${esc(s.color || 'var(--accent)')}"></span></span>
      <span class="bar-val">${s.percentage.toFixed(1)}% · ${s.mention_count}</span>
    </div>`).join('') || '<p class="muted">No share-of-voice data.</p>';

  const alertsHtml = alertsSorted.length ? alertsSorted.map(a => `
    <details class="alert ${a.severity}">
      <summary>
        <span class="chev">▸</span>
        <span class="a-cat">${esc(a.category)}</span>
        <span class="a-meta">${a.current_count} this week · avg ${a.average_count}</span>
        <span class="a-ratio ${a.severity}">${a.spike_ratio}×</span>
      </summary>
      <div class="a-body">
        ${(a.articles && a.articles.length) ? a.articles.map(articleRow).join('') : '<p class="muted">No articles available for this spike.</p>'}
      </div>
    </details>`).join('') : '<p class="muted">No category spikes detected in the last 7 days.</p>';

  // Actual positive / negative posts (content, author, link) — the voices driving sentiment.
  const socAuthorOf = (p: any) => { const a = p.social_meta?.author; if (a) return a; const m = (p.title || '').match(/@([\w.\-]+)/); return m ? m[1] : ''; };
  const socBodyOf = (p: any) => { const b = stripSocialMarkdown(p.summary || '').trim(); return b || stripSocialMarkdown((p.title || '').replace(/^Post by @[\w.\-]+\s*/i, '')).trim() || '(no text)'; };
  const socPostRow = (p: any) => {
    const h = socAuthorOf(p);
    const date = p.publication_date ? esc(p.publication_date.slice(0, 10)) : '';
    const rel = p.relevance != null ? `<span class="src">rel ${p.relevance.toFixed(2)}</span>` : '';
    return `<div class="spost" data-text="${esc((socBodyOf(p) + ' ' + h).toLowerCase())}">
      <div class="spost-head"><span class="chip ${sentClass(p.sentiment)}">${esc(p.platform || 'social')}</span>
        <a href="${esc(p.uri)}" target="_blank" rel="noopener noreferrer" class="spost-h">${h ? '@' + esc(h) : 'view'}</a>
        ${date ? `<span class="date">${date}</span>` : ''}${rel}</div>
      <div class="spost-body">${esc(socBodyOf(p))}</div></div>`;
  };
  const byRel = (a: any, b: any) => (b.relevance ?? 0) - (a.relevance ?? 0);
  const socTopPos = socTop.filter(p => p.sentiment && sentClass(p.sentiment) === 'pos').sort(byRel).slice(0, 15);
  const socTopNeg = socTop.filter(p => p.sentiment && sentClass(p.sentiment) === 'neg').sort(byRel).slice(0, 15);
  const socPosHtml = socTopPos.length ? socTopPos.map(socPostRow).join('') : '<p class="muted">No positive posts in range.</p>';
  const socNegHtml = socTopNeg.length ? socTopNeg.map(socPostRow).join('') : '<p class="muted">No negative posts in range.</p>';

  const socSentTot = socPos + socNeu + socNeg || 1;
  const socSentBar = (socPos + socNeu + socNeg)
    ? `<div class="bar-row"><span class="bar-label">Sentiment split</span>
        <span class="sbar">
          <span class="pos" style="width:${(socPos / socSentTot * 100).toFixed(1)}%" title="Positive ${socPos}"></span>
          <span class="neu" style="width:${(socNeu / socSentTot * 100).toFixed(1)}%" title="Neutral ${socNeu}"></span>
          <span class="neg" style="width:${(socNeg / socSentTot * 100).toFixed(1)}%" title="Negative ${socNeg}"></span>
        </span><span class="bar-val">${socPos}+ ${socNeu}· ${socNeg}−</span></div>`
    : '<p class="muted">No scored posts.</p>';

  const socPerceptionHtml = socPerception.length
    ? socPerception.map(pv => {
        const net = pv.net ?? 0;
        const sc = pv.pos + pv.neu + pv.neg;
        const posPct = sc ? (pv.pos / sc) * 50 : 0;   // half-track = 100%
        const negPct = sc ? (pv.neg / sc) * 50 : 0;
        const counts = `${pv.pos}+ ${pv.neu}· ${pv.neg}−`;
        return `<div class="bar-row${pv.low ? ' low-n' : ''}" title="${counts}${pv.low ? ' — low sample' : ''}">
          <span class="bar-label">${esc(pv.pl)}${pv.low ? ' <span class="lown-tag">low sample</span>' : ''}</span>
          <span class="dbar"><span class="n" style="width:${negPct.toFixed(1)}%"></span><span class="p" style="width:${posPct.toFixed(1)}%"></span><span class="c"></span></span>
          <span class="bar-val">${pv.net == null ? 'n/a' : (net > 0 ? '+' : '') + net} · ${counts}</span></div>`;
      }).join('')
    : '<p class="muted">No on-brand social posts.</p>';

  const authorRow = (x: { a: string; pos: number; neu: number; neg: number; total: number; net: number }, kind: 'fan' | 'crit') => {
    const tot = x.total || 1;
    return `<div class="art"><span class="art-title">@${esc(x.a)}</span>
      <span class="art-meta">
        <span class="sbar" style="flex:0 0 70px">
          <span class="pos" style="width:${(x.pos / tot * 100).toFixed(0)}%"></span>
          <span class="neu" style="width:${(x.neu / tot * 100).toFixed(0)}%"></span>
          <span class="neg" style="width:${(x.neg / tot * 100).toFixed(0)}%"></span>
        </span>
        <span class="chip ${kind === 'fan' ? 'pos' : 'neg'}">${x.net > 0 ? '+' : ''}${x.net}</span>
        <span class="src">${x.total}</span></span></div>`;
  };
  const socFansHtml = socFans.length ? socFans.map(x => authorRow(x, 'fan')).join('') : '<p class="muted">No net-positive third-party authors.</p>';
  const socCriticsHtml = socCritics.length ? socCritics.map(x => authorRow(x, 'crit')).join('') : '<p class="muted">No net-negative authors.</p>';

  const narrativeHtml = d.narrative?.narrative ? mdToHtml(d.narrative.narrative) : '<p class="muted">No insights generated yet for this period.</p>';

  return `<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Brand Watcher — ${esc(brandName)}</title>
<style>
:root{--accent:#D6409F;--accent-tint:rgba(214,64,159,.12);--live:#16a34a;--amber:#E8A838;--neg:#dc2626;
--bg:#ECEDF3;--card:#fff;--border:#e0e1e9;--text:#1a1a2e;--text2:#3d3a4a;--muted:#65636d;--r:12px;}
*{box-sizing:border-box}
body{margin:0;font-family:Inter,-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:var(--bg);color:var(--text);font-size:14px;line-height:1.55}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
.topnav{position:sticky;top:0;z-index:10;background:rgba(255,255,255,.92);backdrop-filter:blur(8px);border-bottom:1px solid var(--border);padding:10px 20px;display:flex;align-items:center;gap:14px;flex-wrap:wrap}
.topnav .brand{font-weight:700;font-size:15px}.topnav .brand b{color:var(--accent)}
.topnav .meta{color:var(--muted);font-size:12px}
.nav{display:flex;gap:4px;margin-left:auto;flex-wrap:wrap}
.nav a{padding:5px 11px;border-radius:999px;font-size:12.5px;color:var(--text2);font-weight:500}
.nav a:hover,.nav a.active{background:var(--accent-tint);color:var(--accent);text-decoration:none}
.search{margin-left:8px;padding:5px 10px;border:1px solid var(--border);border-radius:999px;font-size:12.5px;width:170px;background:#fff}
main{max-width:1040px;margin:0 auto;padding:22px 20px 60px}
h1{font-size:22px;margin:6px 0 2px}.lead{color:var(--muted);margin:0 0 18px}
section{margin:26px 0;scroll-margin-top:64px}
section>h2{font-size:13px;text-transform:uppercase;letter-spacing:.06em;color:var(--accent);margin:0 0 12px;font-weight:700}
.card{background:var(--card);border:1px solid var(--border);border-radius:var(--r);padding:16px 18px;margin-bottom:14px}
.card h3{font-size:13.5px;margin:0 0 12px;color:var(--text)}
.two-col{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.two-col .card{margin-bottom:0}
.low-n{opacity:.5}
.lown-tag{font-size:9.5px;color:var(--muted);background:#f1f1f5;padding:0 5px;border-radius:999px;font-style:italic}
.dbar{flex:1;height:14px;background:#eef0f5;border-radius:999px;overflow:hidden;position:relative}
.dbar .n{position:absolute;right:50%;top:0;bottom:0;background:var(--neg)}
.dbar .p{position:absolute;left:50%;top:0;bottom:0;background:var(--live)}
.dbar .c{position:absolute;left:50%;top:0;bottom:0;width:1px;background:#d5d7e0}
.spost{border-bottom:1px solid #f0f0f4;padding:8px 0}.spost:last-child{border-bottom:none}
.spost-head{display:flex;align-items:center;gap:7px;margin-bottom:3px}
.spost-h{font-size:12px;font-weight:600}
.spost-body{font-size:12.5px;color:var(--text2);white-space:pre-wrap;word-break:break-word}
.stat-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
.stat{background:var(--card);border:1px solid var(--border);border-radius:var(--r);padding:14px 16px}
.stat .eyebrow{font-size:10.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);font-weight:600}
.stat .val{font-size:26px;font-weight:700;margin-top:4px;line-height:1.1}
.stat .sub{font-size:11.5px;color:var(--muted);margin-top:2px}
.val.pos{color:var(--live)}.val.neg{color:var(--neg)}
.bar-row{display:flex;align-items:center;gap:10px;padding:3px 0}
.bar-label{font-size:12.5px;color:var(--text2);width:200px;flex-shrink:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;display:flex;align-items:center;gap:6px}
.bar-track{flex:1;height:14px;background:#eef0f5;border-radius:999px;overflow:hidden}
.bar-fill{display:block;height:100%;background:var(--accent);border-radius:999px}
.bar-val{font-size:11.5px;color:var(--muted);width:96px;text-align:right;flex-shrink:0;font-variant-numeric:tabular-nums}
.sbar{flex:1;height:14px;border-radius:999px;overflow:hidden;display:flex;background:#eef0f5}
.sbar .pos{background:var(--live)}.sbar .neu{background:#94a3b8}.sbar .neg{background:var(--neg)}
.dot{width:9px;height:9px;border-radius:999px;display:inline-block;flex-shrink:0}
details.alert{border:1px solid var(--border);border-radius:10px;margin-bottom:8px;overflow:hidden;background:#fff}
details.alert.high{border-color:#f3c0c0}details.alert.medium{border-color:#f4d9bd}
details.alert>summary{list-style:none;cursor:pointer;display:flex;align-items:center;gap:10px;padding:9px 12px}
details.alert>summary::-webkit-details-marker{display:none}
details.alert .chev{color:var(--muted);transition:transform .15s}details.alert[open] .chev{transform:rotate(90deg)}
.a-cat{flex:1;font-weight:600;font-size:13px}.a-meta{font-size:11.5px;color:var(--muted);font-variant-numeric:tabular-nums}
.a-ratio{font-weight:700;font-size:12px;padding:1px 7px;border-radius:6px;background:#fdeaea;color:var(--neg)}
.a-ratio.medium{background:#fbeedd;color:#b45309}
.a-body{padding:4px 12px 10px 34px;border-top:1px solid #f0f0f4}
.art{display:flex;align-items:center;gap:8px;padding:5px 0;border-bottom:1px solid #f4f4f7;font-size:12.5px}
.art:last-child{border-bottom:none}
.art-title{flex:1;color:var(--text)}.art-title:hover{color:var(--accent)}
.art-meta{display:flex;align-items:center;gap:7px;flex-shrink:0}
.chip{font-size:10.5px;padding:1px 7px;border-radius:999px}
.chip.pos{background:#e7f6ec;color:#15803d}.chip.neg{background:#fdeaea;color:#b91c1c}.chip.neu{background:#eef0f5;color:#475569}
.src,.date{font-size:11px;color:var(--muted)}
.prose h2{font-size:16px;margin:18px 0 6px}.prose h3{font-size:14px;margin:16px 0 6px;color:var(--accent)}
.prose h4{font-size:13px;margin:12px 0 4px}.prose p{margin:6px 0;color:var(--text2)}
.prose ul{margin:6px 0;padding-left:20px}.prose li{margin:3px 0;color:var(--text2)}
.muted{color:var(--muted);font-size:12.5px;font-style:italic}
footer{margin-top:40px;padding-top:16px;border-top:1px solid var(--border);color:var(--muted);font-size:11.5px;text-align:center}
.hidden{display:none!important}
@media(max-width:760px){.stat-grid{grid-template-columns:1fr 1fr}.two-col{grid-template-columns:1fr}.bar-label{width:120px}.nav{width:100%;order:3}.search{margin-left:0}}
@media print{.topnav{position:static}.nav,.search,.print-btn{display:none}details.alert{break-inside:avoid}}
</style></head>
<body>
<header class="topnav">
  <span class="brand">Brand Watcher · <b>${esc(brandName)}</b></span>
  <span class="meta">${esc(period)} · generated ${gen}</span>
  <nav class="nav">
    <a href="#overview" class="active">Overview</a>
    <a href="#analysis">Analysis</a>
    <a href="#insights">Insights</a>
    <a href="#social">Social</a>
  </nav>
  <input class="search" id="q" type="search" placeholder="Search articles…" />
</header>
<main>
  <h1>${esc(brandName)} — Brand Intelligence Report</h1>
  <p class="lead">${esc(period)} · ${totalArticles.toLocaleString()} on-brand articles analyzed</p>

  <section id="overview">
    <h2>Overview</h2>
    <div class="stat-grid">
      ${statCard('On-brand articles', totalArticles.toLocaleString(), period)}
      ${statCard('Categories tracked', String(catSorted.filter(c => c.article_count > 0).length))}
      ${statCard('Top category', topCat, catSorted[0] ? `${catSorted[0].article_count} articles` : '')}
      ${statCard('Active spike alerts', String(d.alerts.length), highAlerts ? `${highAlerts} high-severity` : 'none high')}
    </div>
    <div class="card"><h3>Category distribution</h3>${catBars || '<p class="muted">No categories.</p>'}</div>
  </section>

  <section id="analysis">
    <h2>Analysis</h2>
    <div class="card"><h3>Category spike alerts — click to see the articles driving each spike</h3>${alertsHtml}</div>
    <div class="card"><h3>Sentiment by category</h3>${sentBars}</div>
    <div class="card"><h3>Share of voice</h3>${sovBars}</div>
  </section>

  <section id="insights">
    <h2>Insights</h2>
    <div class="card prose">${narrativeHtml}</div>
  </section>

  <section id="social">
    <h2>Social Pulse${d.brand ? ` — ${esc(brandName)}` : ''}</h2>
    <div class="stat-grid">
      ${statCard('On-brand posts', String(socTop.length), 'relevance ≥ 0.4')}
      ${(() => { const cls = socNet == null ? '' : socNet > 0 ? 'pos' : socNet < 0 ? 'neg' : ''; const v = socNet == null ? '—' : `${socNet > 0 ? '+' : ''}${socNet}`; return `<div class="stat"><div class="eyebrow">Net sentiment</div><div class="val ${cls}">${v}</div><div class="sub">% pos − % neg</div></div>`; })()}
      ${statCard('Fans / Critics', `${socFans.length} / ${socCritics.length}`, 'net-positive / -negative authors')}
      ${statCard('Networks', String(socPerception.length), socPerception.length ? socPerception.map(p => p.pl).join(' · ') : '')}
    </div>
    <div class="card"><h3>Sentiment</h3>${socSentBar}</div>
    <div class="card"><h3>Perception by network — net sentiment <span class="muted">(% positive − % negative of scored posts; neutrals count in the base)</span></h3>${socPerceptionHtml}</div>
    <div class="two-col">
      <div class="card"><h3>😊 Top fans <span class="muted">(own accounts excluded)</span></h3>${socFansHtml}</div>
      <div class="card"><h3>😠 Top critics</h3>${socCriticsHtml}</div>
    </div>
    <div class="two-col">
      <div class="card"><h3>👍 Positive posts</h3>${socPosHtml}</div>
      <div class="card"><h3>👎 Negative posts</h3>${socNegHtml}</div>
    </div>
  </section>

  <footer>Generated ${gen} · Powered by AunooAI · Interactive report — click spikes to expand, use search to filter</footer>
</main>
<script>
(function(){
  // section scroll-spy
  var links=[].slice.call(document.querySelectorAll('.nav a'));
  var secs=links.map(function(a){return document.querySelector(a.getAttribute('href'));});
  function spy(){var y=window.scrollY+80,i=secs.length-1;for(var k=0;k<secs.length;k++){if(secs[k]&&secs[k].offsetTop<=y)i=k;}
    links.forEach(function(l,j){l.classList.toggle('active',j===i);});}
  window.addEventListener('scroll',spy,{passive:true});spy();
  // search filter over article/post rows
  var q=document.getElementById('q');
  q.addEventListener('input',function(){var t=q.value.trim().toLowerCase();
    document.querySelectorAll('.art').forEach(function(el){
      var hit=!t||(el.dataset.text||'').indexOf(t)!==-1;el.classList.toggle('hidden',!hit);});
    // auto-open alerts that contain matches, collapse others, when searching
    if(t){document.querySelectorAll('details.alert').forEach(function(d){
      var any=[].slice.call(d.querySelectorAll('.art')).some(function(a){return !a.classList.contains('hidden');});
      d.open=any;});}
  });
})();
</script>
</body></html>`;
}

export function downloadBrandWatcherReport(d: BrandReportData): void {
  const html = buildBrandWatcherReportHtml(d);
  const blob = new Blob([html], { type: 'text/html;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  const slug = (d.brand?.display_name || 'all').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
  a.download = `brand-report-${slug}-${d.generatedAt.slice(0, 10)}.html`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
