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
  BWRiskSummary, BWIncident, BWEmployeeRisk,
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
  riskSummary?: BWRiskSummary | null;      // adverse-risk rollup (taxonomy counts + top findings)
  incidents?: BWIncident[] | null;         // open incidents
  // Five Signals screens: articles carrying a completed signals_summary
  // (title/uri + verdict + composite + five per-signal bands).
  screened?: {
    title: string; uri: string; verdict: string | null; composite: number | null;
    signals: { key: string; band: string | null; score: number | null }[];
  }[] | null;
  employee?: BWEmployeeRisk | null;        // Glassdoor aggregates + reviews + workforce risks
  perception?: { brands: import('./brandWatcherApi').BWPerceptionBrand[] } | null; // five-dimension perception scores
  allBrandPosts?: any[] | null;            // all-brands social snapshot for the swimlane
  laneBrands?: string[] | null;            // lane order (brand display names)
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
  const socByAuthor: Record<string, { a: string; pos: number; neg: number; neu: number; total: number; nets: Set<string> }> = {};
  for (const p of socTop) {
    if (!p.sentiment) continue;
    const h = authorOfP(p); if (!h || h === 'unknown' || h.includes(':')) continue;
    const x = (socByAuthor[h.toLowerCase()] ||= { a: h, pos: 0, neg: 0, neu: 0, total: 0, nets: new Set<string>() });
    const c = sentClass(p.sentiment);
    if (c === 'pos') x.pos++; else if (c === 'neg') x.neg++; else x.neu++;
    x.total++;
    if ((p as any).platform) x.nets.add((p as any).platform);
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

  const authorRow = (x: { a: string; pos: number; neu: number; neg: number; total: number; net: number; nets?: Set<string> }, kind: 'fan' | 'crit') => {
    const tot = x.total || 1;
    const netTag = x.nets && x.nets.size
      ? ` <span class="muted" style="font-size:10px">${esc(Array.from(x.nets).join(' · '))}</span>` : '';
    return `<div class="art"><span class="art-title">@${esc(x.a)}${netTag}</span>
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

  // ---- Risk & compliance ----
  const rs = d.riskSummary || null;
  const riskTypes = rs ? Object.entries(rs.by_type).sort((a, b) => b[1].total - a[1].total) : [];
  const maxRiskCount = Math.max(1, ...riskTypes.map(([, c]) => c.total));
  const riskBars = riskTypes.length ? riskTypes.map(([rt, c]) => `
    <div class="bar-row">
      <span class="bar-label">${esc(rt.replace(/_/g, ' / '))}</span>
      <span class="bar-track"><span class="bar-fill" style="width:${((c.total / maxRiskCount) * 100).toFixed(1)}%;background:${c.high ? 'var(--neg)' : c.medium ? 'var(--amber)' : 'var(--accent)'}"></span></span>
      <span class="bar-val">${c.total}${c.high ? ` · ${c.high} high` : ''}</span>
    </div>`).join('') : '<p class="muted">No adverse risk findings in the window. 🎉</p>';
  const sevChip = (sev: string) => `<span class="chip ${sev === 'high' || sev === 'critical' ? 'neg' : sev === 'medium' ? 'med' : 'neu'}">${esc(sev)}</span>`;
  const findingsHtml = rs && rs.top_findings.length ? rs.top_findings.map(f => `
    <div class="art" data-text="${esc((f.title || '').toLowerCase())}">
      ${sevChip(f.severity)}
      <a href="${esc(f.uri)}" target="_blank" rel="noopener noreferrer" class="art-title">${esc(f.title)}</a>
      <span class="art-meta"><span class="src">${esc(f.risk_type.replace(/_/g, '/'))}</span>
        ${f.case_status !== 'new' ? `<span class="chip neu">${esc(f.case_status)}</span>` : ''}
        <span class="date">${esc((f.publication_date || '').slice(0, 10))}</span></span>
    </div>`).join('') : '<p class="muted">No findings.</p>';
  const openIncidents = (d.incidents || []).filter(i => !['resolved', 'closed'].includes(i.status));
  const incidentsHtml = openIncidents.length ? openIncidents.map(i => `
    <div class="art" data-text="${esc((i.title || '').toLowerCase())}">
      ${sevChip(i.severity)}
      <span class="art-title">${esc(i.title)}</span>
      <span class="art-meta"><span class="chip neu">${esc(i.status)}</span>${i.owner ? `<span class="src">${esc(i.owner)}</span>` : ''}<span class="date">${esc((i.created_at || '').slice(0, 10))}</span></span>
    </div>`).join('') : '<p class="muted">No open incidents. 🎉</p>';
  const officialHtml = rs && Object.keys(rs.official_sources).length
    ? Object.entries(rs.official_sources).sort((a, b) => b[1] - a[1]).map(([ns, n]) => `<span class="chip neu">${esc(ns)}: ${n}</span>`).join(' ')
    : '';

  // Five Signals screening intentionally NOT in the report — screening exists
  // to escalate incidents, not for report consumption (removed 2026-07-06).

  // ---- Workforce (Glassdoor) ----
  const emp = d.employee || null;
  const eo = emp?.overview || null;
  const empPct = (v?: number | null) => (v == null ? null : Math.round(v * 100));
  const empSubs: Array<[string, number | null | undefined]> = eo ? [
    ['Work-life balance', eo.work_life_balance_rating],
    ['Culture & values', eo.culture_and_values_rating],
    ['Compensation & benefits', eo.compensation_and_benefits_rating],
    ['Senior management', eo.senior_management_rating],
    ['Career opportunities', eo.career_opportunities_rating],
    ['Diversity & inclusion', eo.diversity_and_inclusion_rating],
  ] : [];
  const empSubBars = empSubs.filter(([, v]) => typeof v === 'number').map(([label, v]) => `
    <div class="bar-row">
      <span class="bar-label">${esc(label)}</span>
      <span class="bar-track"><span class="bar-fill" style="width:${(((v as number) / 5) * 100).toFixed(1)}%;background:${(v as number) >= 3.5 ? 'var(--live)' : (v as number) < 3 ? 'var(--neg)' : 'var(--amber)'}"></span></span>
      <span class="bar-val">${(v as number).toFixed(1)}/5</span>
    </div>`).join('');
  const empCompRows = emp && (emp.competitors.length || eo) ? [
    ...(eo ? [{ brand_name: brandName, overview: eo, self: true }] : []),
    ...emp.competitors.map(c => ({ brand_name: c.brand_name, overview: c.overview, self: false })),
  ].map(c => `
    <div class="bar-row">
      <span class="bar-label"${c.self ? ' style="font-weight:700"' : ''}>${esc(c.brand_name)}</span>
      <span class="bar-track"><span class="bar-fill" style="width:${(((c.overview.rating || 0) / 5) * 100).toFixed(1)}%"></span></span>
      <span class="bar-val">${c.overview.rating != null ? `${c.overview.rating}/5` : '—'}${empPct(c.overview.business_outlook_rating) != null ? ` · outlook ${empPct(c.overview.business_outlook_rating)}%` : ''}</span>
    </div>`).join('') : '';
  const empReviewRows = (emp?.reviews || []).slice(0, 8).map(r => {
    const m = (r.title || '').match(/^Glassdoor review(?: \((\d)\/5\))?: (.*)$/);
    const rating = m?.[1] || null;
    const headline = m?.[2] || r.title;
    const seg = (name: string) => { const mm = (r.summary || '').match(new RegExp(`${name}: ([^|]*)(\\||$)`)); return mm ? mm[1].trim() : null; };
    const pros = seg('Pros'), cons = seg('Cons');
    return `<div class="spost" data-text="${esc(`${headline} ${pros || ''} ${cons || ''}`.toLowerCase())}">
      <div class="spost-head">${rating ? `<span class="chip ${Number(rating) >= 4 ? 'pos' : Number(rating) <= 2 ? 'neg' : 'neu'}">${rating}★</span>` : ''}
        <a href="${esc(r.uri)}" target="_blank" rel="noopener noreferrer" class="spost-h">${esc(headline)}</a>
        <span class="date">${esc((r.publication_date || '').slice(0, 10))}</span></div>
      ${pros ? `<div class="spost-body"><strong style="color:var(--live)">Pros:</strong> ${esc(pros.slice(0, 200))}</div>` : ''}
      ${cons ? `<div class="spost-body"><strong style="color:var(--neg)">Cons:</strong> ${esc(cons.slice(0, 200))}</div>` : ''}
    </div>`;
  }).join('') || '<p class="muted">No reviews landed yet.</p>';
  const wfRiskRows = (emp?.workforce_risks || []).slice(0, 8).map(w => `
    <div class="art" data-text="${esc((w.title || '').toLowerCase())}">
      ${sevChip(w.severity)}
      <a href="${esc(w.uri)}" target="_blank" rel="noopener noreferrer" class="art-title">${esc(w.title)}</a>
      <span class="art-meta">${w.case_status !== 'new' ? `<span class="chip neu">${esc(w.case_status)}</span>` : ''}<span class="date">${esc((w.publication_date || '').slice(0, 10))}</span></span>
    </div>`).join('') || '<p class="muted">No workforce risk findings. 🎉</p>';
  const empRs = emp?.review_sentiment;

  // ---- Social competitor swimlanes (static cells) ----
  let lanesHtml = '';
  if (d.allBrandPosts && d.allBrandPosts.length && (d.laneBrands || []).length > 1) {
    const windowDays = d.daysBack && d.daysBack > 0 ? Math.min(d.daysBack, 365) : 90;
    const weekly = windowDays > 60;
    const genDate = new Date(d.generatedAt.slice(0, 10) + 'T00:00:00Z');
    const bucketOf = (ds: string) => {
      const day = (ds || '').slice(0, 10);
      if (!day) return null;
      if (!weekly) return day;
      const dt = new Date(`${day}T00:00:00Z`);
      if (isNaN(+dt)) return null;
      dt.setUTCDate(dt.getUTCDate() - ((dt.getUTCDay() + 6) % 7));
      return dt.toISOString().slice(0, 10);
    };
    const buckets: string[] = [];
    const start = new Date(genDate); start.setUTCDate(start.getUTCDate() - windowDays);
    if (weekly) start.setUTCDate(start.getUTCDate() - ((start.getUTCDay() + 6) % 7));
    const cur = new Date(start);
    const endDay = genDate.toISOString().slice(0, 10);
    while (cur.toISOString().slice(0, 10) <= endDay) {
      buckets.push(cur.toISOString().slice(0, 10));
      cur.setUTCDate(cur.getUTCDate() + (weekly ? 7 : 1));
    }
    const brandOf = (p: any) => ((p.topic || '').replace(/^Brand Monitoring\s+/i, '').trim() || 'Other');
    type LCell = { pos: number; neu: number; neg: number; total: number };
    const lanes: Record<string, { cells: Record<string, LCell>; pos: number; neg: number; scored: number; total: number }> = {};
    for (const p of d.allBrandPosts) {
      const b = brandOf(p);
      const bk = bucketOf(p.publication_date);
      if (!bk) continue;
      const lane = lanes[b] || (lanes[b] = { cells: {}, pos: 0, neg: 0, scored: 0, total: 0 });
      const cell = lane.cells[bk] || (lane.cells[bk] = { pos: 0, neu: 0, neg: 0, total: 0 });
      const c = sentClass(p.sentiment);
      cell.total++; lane.total++;
      if (c === 'pos') { cell.pos++; lane.pos++; lane.scored++; }
      else if (c === 'neg') { cell.neg++; lane.neg++; lane.scored++; }
      else if (p.sentiment) { cell.neu++; lane.scored++; }
    }
    const laneOrder = (d.laneBrands || []).filter(n => lanes[n]);
    if (laneOrder.length > 1) {
      const cellColor = (c: LCell) => {
        const sc = c.pos + c.neu + c.neg;
        if (!sc) return '#9ca3af';
        const net = (c.pos - c.neg) / sc;
        return net > 0.2 ? 'var(--live)' : net < -0.2 ? 'var(--neg)' : 'var(--amber)';
      };
      lanesHtml = `<div class="card"><h3>Brand swimlanes <span class="muted">(${weekly ? 'weekly' : 'daily'} post volume, colored by net sentiment)</span></h3>
        ${laneOrder.map(name => {
          const lane = lanes[name];
          const maxVol = Math.max(1, ...buckets.map(bk => lane.cells[bk]?.total || 0));
          const net = lane.scored ? Math.round(((lane.pos - lane.neg) / lane.scored) * 100) : null;
          return `<div class="lane"><span class="lane-name">${esc(name)}</span>
            <span class="lane-net ${net == null ? '' : net > 0 ? 'pos-t' : net < 0 ? 'neg-t' : ''}">${net == null ? '—' : `${net > 0 ? '+' : ''}${net}`}</span>
            <span class="lane-cells">${buckets.map(bk => {
              const c = lane.cells[bk];
              if (!c) return '<span class="lcell empty"></span>';
              const h = Math.max(4, Math.round((c.total / maxVol) * 26));
              return `<span class="lcell" style="height:${h}px;background:${cellColor(c)}" title="${esc(bk)}${weekly ? ' (week)' : ''}: ${c.total} · ${c.pos}+ ${c.neu}· ${c.neg}−"></span>`;
            }).join('')}</span>
            <span class="lane-total">${lane.total}</span></div>`;
        }).join('')}
        <p class="muted" style="margin-top:6px">${esc(buckets[0] || '')} → ${esc(endDay)} · green net-positive, amber mixed, red net-negative</p>
      </div>`;
    }
  }

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
.chip.pos{background:#e7f6ec;color:#15803d}.chip.neg{background:#fdeaea;color:#b91c1c}.chip.neu{background:#eef0f5;color:#475569}.chip.med{background:#fbeedd;color:#b45309}
.lane{display:flex;align-items:center;gap:8px;padding:4px 0}
.lane-name{width:130px;font-size:12.5px;color:var(--text2);flex-shrink:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.lane-net{width:38px;font-size:11px;font-weight:700;flex-shrink:0}.pos-t{color:var(--live)}.neg-t{color:var(--neg)}
.lane-cells{flex:1;display:flex;align-items:flex-end;gap:1px;height:28px}
.lcell{flex:1;border-radius:2px;min-width:2px}.lcell.empty{height:3px;background:#e8e9f0}
.lane-total{width:40px;font-size:11px;color:var(--muted);text-align:right;flex-shrink:0;font-variant-numeric:tabular-nums}
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
    <a href="#perception">Perception</a>
    <a href="#risk">Risk</a>
    <a href="#workforce">Workforce</a>
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

  ${(() => {
    const pb = d.perception?.brands || [];
    if (!pb.length) return '';
    const DIMS: { k: 'media' | 'social' | 'community' | 'employee' | 'investor'; l: string }[] = [
      { k: 'media', l: 'Media' }, { k: 'social', l: 'Social' }, { k: 'community', l: 'Community' },
      { k: 'employee', l: 'Employee' }, { k: 'investor', l: 'Investor' }];
    const chip = (s: number | null | undefined) => {
      if (s === null || s === undefined) return '<span class="chip">no data</span>';
      const cls = s >= 20 ? 'pos' : s <= -20 ? 'neg' : '';
      return `<span class="chip ${cls}">${s > 0 ? '+' : ''}${s}</span>`;
    };
    const rows = pb.map(b => `<tr>
      <td style="white-space:nowrap">${esc(b.display_name)}${b.is_primary ? ' <span class="muted" style="font-size:10px">primary</span>' : ''}</td>
      ${DIMS.map(dim => {
        const v = b.dimensions[dim.k];
        const n = dim.k === 'employee'
          ? (v?.rating != null ? `${v.rating}/5` : '')
          : (v?.n ? String(v.n) : '');
        return `<td>${chip(v?.score)}${n ? ` <span class="muted" style="font-size:10px">${esc(n)}</span>` : ''}</td>`;
      }).join('')}
    </tr>`).join('');
    return `<section id="perception">
    <h2>Perception Dimensions</h2>
    <div class="card">
      <table style="width:100%;border-collapse:collapse;font-size:13px">
        <thead><tr style="text-align:left;color:#888;font-size:11px">
          <th style="padding:4px 8px 8px 0">Brand</th>${DIMS.map(x => `<th style="padding:4px 8px 8px 0">${x.l}</th>`).join('')}
        </tr></thead>
        <tbody>${rows}</tbody>
      </table>
      <p class="muted" style="margin-top:10px;font-size:11px">Net sentiment −100…+100 over relevance ≥ 0.4 items (media = news, social = Bluesky/X/Instagram/TikTok, community = Reddit, investor = Financial Performance-classified articles). Employee scales the Glassdoor rating (3.0 = neutral); grey numbers are item volumes — low-sample scores are volatile.</p>
    </div>
  </section>` ;
  })()}

  <section id="risk">
    <h2>Risk &amp; Compliance</h2>
    <div class="stat-grid">
      ${statCard('Risk findings', String(riskTypes.reduce((a, [, c]) => a + c.total, 0)), rs ? `last ${rs.days_back} days` : '')}
      ${statCard('High severity', String(riskTypes.reduce((a, [, c]) => a + c.high, 0)))}
      ${statCard('Open incidents', String(openIncidents.length))}
      ${statCard('Alert events', String(rs?.alert_events ?? 0), 'server-side rules fired')}
    </div>
    <div class="card"><h3>Findings by risk type</h3>${riskBars}</div>
    <div class="two-col">
      <div class="card"><h3>Top findings</h3>${findingsHtml}</div>
      <div class="card"><h3>Open incidents</h3>${incidentsHtml}</div>
    </div>
    ${officialHtml ? `<div class="card"><h3>Official &amp; scholarly records</h3>${officialHtml}</div>` : ''}
  </section>

  <section id="workforce">
    <h2>Workforce Signal</h2>
    ${eo ? `<div class="stat-grid">
      ${statCard('Glassdoor rating', eo.rating != null ? `${eo.rating}/5` : '—', eo.review_count ? `${eo.review_count.toLocaleString()} reviews` : '')}
      ${statCard('CEO approval', empPct(eo.ceo_rating) != null ? `${empPct(eo.ceo_rating)}%` : '—', eo.ceo || '')}
      ${(() => { const v = empPct(eo.business_outlook_rating); const cls = v == null ? '' : v >= 60 ? 'pos' : v < 45 ? 'neg' : ''; return `<div class="stat"><div class="eyebrow">Business outlook</div><div class="val ${cls}">${v != null ? `${v}%` : '—'}</div><div class="sub">positive outlook</div></div>`; })()}
      ${statCard('Recommend to friend', empPct(eo.recommend_to_friend_rating) != null ? `${empPct(eo.recommend_to_friend_rating)}%` : '—')}
    </div>
    <div class="two-col">
      <div class="card"><h3>Sub-ratings</h3>${empSubBars || '<p class="muted">No sub-ratings.</p>'}</div>
      <div class="card"><h3>Employer ratings vs competitors</h3>${empCompRows || '<p class="muted">No competitor data.</p>'}</div>
    </div>
    <div class="two-col">
      <div class="card"><h3>Recent employee reviews${empRs && empRs.scored ? ` <span class="muted">(${empRs.pos}+ ${empRs.neu}· ${empRs.neg}−)</span>` : ''}</h3>${empReviewRows}</div>
      <div class="card"><h3>Workforce risk findings</h3>${wfRiskRows}</div>
    </div>` : '<div class="card"><p class="muted">No Glassdoor data for this brand — enable the Glassdoor source to populate this section.</p></div>'}
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
    ${lanesHtml}
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
