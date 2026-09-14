/**
 * Self-contained VOICES report for Brand Watcher: who is talking about one
 * brand and what each audience says. One downloadable .html, inline CSS, no
 * dependencies, same house style as the social report. Written to be handed
 * to the brand's own team, so it carries the digest's context line and the
 * "what these posts ask for" list, and every quote is copied from a post.
 */
import type { BWVoicesResponse, BWVoiceRole, BWVoicesDigest, BWVoicePost } from './brandWatcherApi';

export interface VoicesReportData {
  voices: BWVoicesResponse;
  /** The audiences shown side by side, in order. */
  compared: string[];
  /** Digest per compared role, where one was produced. */
  digests: Record<string, BWVoicesDigest | null | undefined>;
  daysBack: number;
  generatedAt: string; // ISO, caller stamps it
}

function esc(s: unknown): string {
  return String(s ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

const PLAT_COLORS: Record<string, string> = { twitter: '#1d9bf0', bluesky: '#0085ff', reddit: '#ff4500', instagram: '#e1306c', tiktok: '#111', glassdoor: '#0caa41', social: '#6b7280' };
const PLAT_LABELS: Record<string, string> = { twitter: 'X', bluesky: 'Bluesky', reddit: 'Reddit', instagram: 'Instagram', tiktok: 'TikTok', glassdoor: 'Glassdoor', social: 'Other' };

function netChip(net: number | null): string {
  if (net === null) return '<span class="chip">n/a</span>';
  const cls = net >= 20 ? 'pos' : net <= -20 ? 'neg' : '';
  return `<span class="chip ${cls}">${net > 0 ? '+' : ''}${net}</span>`;
}

function splitBar(r: BWVoiceRole): string {
  const tot = r.n || 1;
  return `<span class="sbar" title="${r.positive}+ ${r.neutral}· ${r.negative}−">
    <span class="pos" style="width:${(r.positive / tot * 100).toFixed(0)}%"></span>
    <span class="neu" style="width:${(r.neutral / tot * 100).toFixed(0)}%"></span>
    <span class="neg" style="width:${(r.negative / tot * 100).toFixed(0)}%"></span>
  </span>`;
}

function sourceNote(p: BWVoicePost): string {
  if (p.author_role_source === 'account_profile') {
    const extra = p.account_market_role ? ` (${p.account_market_role.replace(/_/g, ' ')}${p.account_org ? `, ${p.account_org}` : ''})` : '';
    const diff = p.post_role && p.post_role !== p.author_role ? `; this post alone read as ${p.post_role}` : '';
    return `Role from the account profile${esc(extra)}${esc(diff)}`;
  }
  if (p.author_role_source === 'account_posts') {
    const diff = p.post_role && p.post_role !== p.author_role ? `; this post alone read as ${p.post_role}` : '';
    return `Role from this account's other posts${esc(diff)}`;
  }
  return p.author_role_reason ? `Why this role: ${esc(p.author_role_reason)}` : '';
}

function postCard(p: BWVoicePost): string {
  const plat = p.platform || 'social';
  const s = p.sentiment === 'positive' ? 'pos' : p.sentiment === 'negative' ? 'neg' : 'neu';
  const note = sourceNote(p);
  return `<div class="post ${s}" data-text="${esc((p.text || '').toLowerCase())}">
    <div class="post-head">
      <span class="plat" style="background:${PLAT_COLORS[plat] || PLAT_COLORS.social};color:#fff">${esc(PLAT_LABELS[plat] || plat)}</span>
      ${p.author ? `<span class="post-h">@${esc(p.author)}</span>` : ''}
      ${p.publication_date ? `<span class="date">${esc(p.publication_date.slice(0, 10))}</span>` : ''}
      <span class="date">${esc(p.sentiment || 'unrated')}</span>
      <span class="spacer"></span>
      <a href="${esc(p.uri)}" target="_blank" rel="noopener">view</a>
    </div>
    <div class="post-body">${esc(p.text)}</div>
    ${note ? `<div class="why">${note}</div>` : ''}
  </div>`;
}

function digestHtml(d: BWVoicesDigest | null | undefined, r: BWVoiceRole): string {
  if (!d) return `<p class="muted">No digest was produced for this audience.</p>`;
  if (!d.summary && !d.themes?.length) return `<p class="muted">${esc(d.note || 'Nothing to summarise yet.')}</p>`;
  const themes = (d.themes || []).map(t => `
    <div class="theme">
      <div class="theme-h"><span>${esc(t.theme)}</span>
        <span class="chip ${t.sentiment === 'positive' ? 'pos' : t.sentiment === 'negative' ? 'neg' : ''}">${esc(t.sentiment)}</span>
        ${t.post_count ? `<span class="cnt-l">${t.post_count} post${t.post_count === 1 ? '' : 's'}</span>` : ''}</div>
      ${t.quotes?.length ? `<ul class="quotes">${t.quotes.map(q => `<li>“${esc(q)}”</li>`).join('')}</ul>` : ''}
    </div>`).join('');
  const asks = d.asks?.length ? `<h4>What these posts ask for</h4><ul class="asks">${d.asks.map(a => `<li>${esc(a)}</li>`).join('')}</ul>` : '';
  return `
    ${d.context ? `<p class="ctx">${esc(d.context)}</p>` : ''}
    ${d.summary ? `<p class="summary">${esc(d.summary)}</p>` : ''}
    ${d.tone_warning ? `<p class="warn">${esc(d.tone_warning)}</p>` : ''}
    ${themes}
    ${asks}
    <p class="muted">Digest by ${esc(d.model || 'the site model')} over ${r.n} post${r.n === 1 ? '' : 's'}. Quotes are copied from the posts; open the post before citing one.</p>`;
}

export function buildVoicesReportHtml(d: VoicesReportData): string {
  const v = d.voices;
  const brandName = v.brand;
  const period = d.daysBack === 0 ? 'All time' : `Last ${d.daysBack} days`;
  const gen = esc(d.generatedAt.replace('T', ' ').slice(0, 16));
  const roles = v.roles || [];
  const compared = d.compared.map(r => roles.find(x => x.role === r)).filter((x): x is BWVoiceRole => !!x);
  const external = roles.filter(r => r.role !== 'brand');
  const externalN = external.reduce((s, r) => s + r.n, 0);

  const tableRows = roles.map(r => `
    <tr>
      <td><b>${esc(r.label)}</b><div class="hint">${esc(r.hint)}</div></td>
      <td class="num">${r.n}</td>
      <td class="num pos-t">${r.positive}</td><td class="num">${r.neutral}</td><td class="num neg-t">${r.negative}</td>
      <td>${splitBar(r)}</td>
      <td>${netChip(r.net)}</td>
      <td class="plats">${Object.entries(r.by_platform).sort((a, b) => b[1] - a[1]).map(([pl, n]) => `<span class="plat" style="background:${PLAT_COLORS[pl] || PLAT_COLORS.social};color:#fff">${esc(PLAT_LABELS[pl] || pl)} ${n}</span>`).join(' ')}</td>
    </tr>`).join('');

  const columns = compared.map(r => `
    <div class="card col">
      <h3>${esc(r.label)} <span class="h-sub">${r.n} post${r.n === 1 ? '' : 's'} · ${r.positive} positive · ${r.neutral} neutral · ${r.negative} negative · net ${r.net === null ? 'n/a' : (r.net > 0 ? '+' : '') + r.net}</span></h3>
      <div class="hint">${esc(r.hint)}</div>
      <div class="digest">${digestHtml(d.digests[r.role], r)}</div>
      <h4>Posts <span class="h-sub">${r.posts.length < r.n ? `the ${r.posts.length} most recent of ${r.n}` : `all ${r.n}`}</span></h4>
      <div class="posts">${r.posts.length ? r.posts.map(postCard).join('') : '<p class="muted">No posts.</p>'}</div>
    </div>`).join('');

  const notes = (v.coverage_notes || []).map(n => `<li>${esc(n)}</li>`).join('');

  return `<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Voices — ${esc(brandName)}</title>
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
main{max-width:1100px;margin:0 auto;padding:22px 20px 60px}
h1{font-size:22px;margin:6px 0 2px}.lead{color:var(--muted);margin:0 0 18px}
section{margin:26px 0;scroll-margin-top:64px}
section>h2{font-size:13px;text-transform:uppercase;letter-spacing:.06em;color:var(--accent);margin:0 0 12px;font-weight:700}
.card{background:var(--card);border:1px solid var(--border);border-radius:var(--r);padding:16px 18px;margin-bottom:14px}
.card h3{font-size:15px;margin:0 0 4px;color:var(--text)}
.card h4{font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);margin:16px 0 6px}
.two-col{display:grid;grid-template-columns:1fr 1fr;gap:14px;align-items:start}.two-col .card{margin-bottom:0}
.stat-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:14px}
.stat{background:var(--card);border:1px solid var(--border);border-radius:var(--r);padding:14px 16px}
.stat .eyebrow{font-size:10.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);font-weight:600}
.stat .val{font-size:26px;font-weight:700;margin-top:4px;line-height:1.1}.stat .sub{font-size:11.5px;color:var(--muted);margin-top:2px}
table{width:100%;border-collapse:collapse;font-size:13px}
th{font-size:10.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);text-align:left;padding:6px 8px;border-bottom:1px solid var(--border)}
td{padding:8px;border-bottom:1px solid #f0f0f4;vertical-align:middle}
td.num{text-align:right;font-variant-numeric:tabular-nums;width:48px}
td.pos-t{color:var(--live)}td.neg-t{color:var(--neg)}
td.plats{white-space:nowrap}
.hint{font-size:11.5px;color:var(--muted)}
.sbar{height:12px;border-radius:999px;overflow:hidden;display:flex;background:#eef0f5;width:110px}
.sbar .pos{background:var(--live)}.sbar .neu{background:#94a3b8}.sbar .neg{background:var(--neg)}
.chip{font-size:10.5px;padding:1px 7px;border-radius:999px;font-weight:600;background:#fdf3d0;color:#92400e}
.chip.pos{background:#e7f6ec;color:#15803d}.chip.neg{background:#fdeaea;color:#b91c1c}
.plat{font-size:10px;text-transform:uppercase;letter-spacing:.04em;padding:1px 7px;border-radius:999px;font-weight:600}
.ctx{font-size:12.5px;color:var(--muted);margin:8px 0 4px}
.summary{font-size:14px;color:var(--text);margin:4px 0 12px}
.warn{font-size:12px;color:#92400e;background:#fdf3d0;padding:6px 10px;border-radius:8px}
.theme{border:1px solid #f0f0f4;border-radius:8px;padding:8px 10px;margin-bottom:8px}
.theme-h{display:flex;align-items:center;gap:8px;font-weight:600;font-size:13px}
.cnt-l{font-size:11px;color:var(--muted);font-weight:500}
.quotes{margin:6px 0 0;padding-left:0;list-style:none}
.quotes li{font-size:12.5px;color:var(--text2);border-left:2px solid #e5e7eb;padding-left:8px;margin:4px 0;font-style:italic}
.asks{margin:4px 0 0;padding-left:18px}.asks li{font-size:13px;color:var(--text2);margin:3px 0}
.post{border-bottom:1px solid #f0f0f4;padding:9px 0 9px 10px;border-left:3px solid transparent;margin-bottom:2px}
.post:last-child{border-bottom:none}
.post.pos{border-left-color:var(--live)}.post.neg{border-left-color:var(--neg)}
.post-head{display:flex;align-items:center;gap:8px;margin-bottom:3px;flex-wrap:wrap}
.post-h{font-size:12px;font-weight:600}.date{font-size:11px;color:var(--muted)}
.spacer{flex:1}
.post-body{font-size:13px;color:var(--text2);white-space:pre-wrap;word-break:break-word}
.why{font-size:11px;color:var(--muted);font-style:italic;margin-top:3px}
.h-sub{font-size:11px;color:var(--muted);text-transform:none;letter-spacing:0;font-weight:500;margin-left:8px}
.muted{color:var(--muted);font-size:12.5px;font-style:italic}
.method{font-size:12.5px;color:var(--text2)}
footer{margin-top:40px;padding-top:16px;border-top:1px solid var(--border);color:var(--muted);font-size:11.5px;text-align:center}
@media(max-width:760px){.stat-grid{grid-template-columns:1fr 1fr}.two-col{grid-template-columns:1fr}}
@media print{.topnav{position:static}.nav,.search{display:none}.two-col{grid-template-columns:1fr}}
</style></head>
<body>
<header class="topnav">
  <span class="brand">Voices · <b>${esc(brandName)}</b></span>
  <span class="meta">${esc(period)} · generated ${gen}</span>
  <nav class="nav">
    <a href="#overview">Overview</a>
    <a href="#audiences">Audiences</a>
    <a href="#compare">Side by side</a>
    <a href="#method">Method</a>
  </nav>
  <input class="search" id="q" type="search" placeholder="Search posts…" />
</header>
<main>
  <h1>${esc(brandName)} — who is talking, and what each audience says</h1>
  <p class="lead">${esc(period)} · on-brand social and community posts (relevance ≥ ${v.min_relevance}) · the brand's own accounts are listed as brand voice and never counted in an audience's sentiment.</p>

  <section id="overview">
    <h2>Overview</h2>
    <div class="stat-grid">
      <div class="stat"><div class="eyebrow">Posts about the brand</div><div class="val">${v.total}</div><div class="sub">${externalN} from outside voices</div></div>
      <div class="stat"><div class="eyebrow">Audiences heard</div><div class="val">${external.length}</div><div class="sub">${external.map(r => r.label).slice(0, 4).join(', ')}${external.length > 4 ? '…' : ''}</div></div>
      ${compared.map(r => `<div class="stat"><div class="eyebrow">${esc(r.label)}</div><div class="val ${r.net !== null && r.net >= 20 ? 'pos' : r.net !== null && r.net <= -20 ? 'neg' : ''}">${r.net === null ? 'n/a' : (r.net > 0 ? '+' : '') + r.net}</div><div class="sub">net sentiment over ${r.n} post${r.n === 1 ? '' : 's'}</div></div>`).join('')}
    </div>
    ${notes ? `<div class="card"><ul class="asks">${notes}</ul></div>` : ''}
  </section>

  <section id="audiences">
    <h2>Audiences</h2>
    <div class="card">
      <table>
        <thead><tr><th>Audience</th><th>Posts</th><th>+</th><th>·</th><th>−</th><th>Split</th><th>Net</th><th>Where</th></tr></thead>
        <tbody>${tableRows}</tbody>
      </table>
      <p class="hint" style="margin-top:8px">Net sentiment = (positive − negative) ÷ posts × 100. Small counts move it a long way; read the number with the count beside it.</p>
    </div>
  </section>

  <section id="compare">
    <h2>Side by side</h2>
    ${compared.length ? `<div class="two-col">${columns}</div>` : '<p class="muted">No audiences were compared.</p>'}
  </section>

  <section id="method">
    <h2>Method</h2>
    <div class="card method">
      <p>Each post is read once by the site's social evaluation model, which scores relevance to the brand, sentiment toward it, and who is speaking: patient, caregiver, clinician, customer, academic, professional, employee, journalist, investor, brand, or unknown when the text gives no clue. Glassdoor reviews count as employees without a model reading.</p>
      <p>The account outranks the single post. Where the author's account has been profiled, its profile role is used for every one of its posts; otherwise, where the account's other classified posts keep reading the same way, that reading is used. Each post below says which applied.</p>
      <p>The digest is written for the brand's own team: it attributes everything to the posts and counts it, gives the context needed to weigh it, quotes the posts verbatim, and lists what the posts ask for. It passes no verdict on the brand or on the audience.</p>
    </div>
  </section>

  <footer>Generated ${gen} · Powered by AunooAI · Voices report</footer>
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
})();
</script>
</body></html>`;
}

export function downloadVoicesReport(d: VoicesReportData): void {
  const html = buildVoicesReportHtml(d);
  const blob = new Blob([html], { type: 'text/html' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  const slug = (d.voices.brand || 'brand').toLowerCase().replace(/\s+/g, '-');
  a.download = `voices-${slug}-${d.generatedAt.slice(0, 10)}.html`;
  document.body.appendChild(a); a.click(); document.body.removeChild(a); URL.revokeObjectURL(url);
}
