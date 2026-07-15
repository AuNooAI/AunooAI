/**
 * Incident report exports — Markdown, text-based PDF, and a self-contained
 * interactive HTML document (house style, matches brandReportHtml.ts).
 *
 * Everything is generated client-side from the data the incident panel
 * already holds: the incident detail (evidence + timeline + Five Signals
 * summaries) and the latest enrichment state (agent brief + stats).
 */
import { jsPDF } from 'jspdf';
import type { BWIncidentDetail } from './brandWatcherApi';

export interface IncidentReportData {
  incident: BWIncidentDetail & { description?: string | null; owner?: string | null };
  enrichment?: {
    run?: { id: number; status: string; brief?: string | null; stats?: any;
            finished_at?: string | null; started_by?: string | null } | null;
    candidates?: any[];
    counts?: Record<string, number>;
  } | null;
}

const SIG_TITLES: Record<string, string> = {
  veracity: 'Claim veracity', source_credibility: 'Source credibility',
  corroboration: 'Corroboration', propagation: 'Propagation & reach',
  amplification_integrity: 'Amplification integrity',
};
const SIG_SHORT: Record<string, string> = {
  veracity: 'V', source_credibility: 'S', corroboration: 'C',
  propagation: 'P', amplification_integrity: 'A',
};

const esc = (s: any): string => String(s ?? '')
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

const day = (iso?: string | null) => (iso || '').slice(0, 10);
const minute = (iso?: string | null) => (iso || '').slice(0, 16).replace('T', ' ');
const hostOf = (url?: string | null) => {
  try { return url ? new URL(url).hostname.replace(/^www\./, '') : ''; } catch { return ''; }
};
const slug = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 50);

function download(content: string, filename: string, mime: string): void {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

const screenedEvidence = (d: IncidentReportData) =>
  (d.incident.evidence || []).filter(e =>
    e.evidence_type === 'article' && (e as any).signals_summary?.status === 'completed');

// ─── Markdown ────────────────────────────────────────────────────────────────

export function buildIncidentReportMarkdown(d: IncidentReportData): string {
  const inc = d.incident;
  const run = d.enrichment?.run;
  let md = `# Incident #${inc.id}: ${inc.title}\n\n`;
  md += `| | |\n|---|---|\n`;
  md += `| Brand | ${inc.brand_name || ''} |\n`;
  md += `| Severity | ${inc.severity} |\n`;
  md += `| Status | ${inc.status} |\n`;
  if (inc.owner) md += `| Owner | ${inc.owner} |\n`;
  md += `| Opened | ${day(inc.created_at)} by ${inc.created_by || 'unknown'} |\n`;
  if (inc.resolved_at) md += `| Resolved | ${day(inc.resolved_at)} |\n`;
  md += `| Report generated | ${new Date().toISOString().slice(0, 16).replace('T', ' ')} UTC |\n\n`;
  if (inc.description) md += `${inc.description}\n\n`;

  const screened = screenedEvidence(d);
  if (screened.length) {
    md += `## Five Signals screening\n\n`;
    md += `Attached articles screened via the Aunoo validation platform (claim validation + social propagation):\n\n`;
    for (const ev of screened) {
      const s = (ev as any).signals_summary;
      md += `### ${ev.title || ev.source_ref}\n\n`;
      if (ev.source_ref) md += `<${ev.source_ref}>\n\n`;
      md += `**Verdict:** ${s.verdict || 'n/a'} · **Composite score:** ${s.composite ?? 'n/a'}/100\n\n`;
      md += `| Signal | Band | Score |\n|---|---|---|\n`;
      for (const sig of s.signals || []) {
        md += `| ${SIG_TITLES[sig.key] || sig.key} | ${sig.band || 'no data'} | ${sig.score ?? '—'} |\n`;
      }
      md += `\n`;
    }
  }

  if (run?.brief) {
    md += `## Agent brief\n\n`;
    md += `*Written by the enrichment agent${run.finished_at ? ` on ${minute(run.finished_at)}` : ''}. `;
    md += `AI-generated from the attached material — verify before acting.*\n\n`;
    md += `${run.brief}\n\n`;
  }

  md += `## Evidence (${(inc.evidence || []).length})\n\n`;
  md += `The evidence locker is append-only and hash-chained; each entry's sha256 is listed for audit.\n\n`;
  (inc.evidence || []).forEach((ev, i) => {
    md += `### ${i + 1}. [${ev.evidence_type.replace('_', ' ')}] ${ev.title || ev.source_ref || '(untitled)'}\n\n`;
    if (ev.source_ref && String(ev.source_ref).startsWith('http')) md += `<${ev.source_ref}>\n\n`;
    md += `*Captured ${minute(ev.captured_at)} by ${ev.captured_by || 'unknown'}*\n\n`;
    if (ev.content) md += `${String(ev.content).slice(0, 1500)}\n\n`;
    md += `\`sha256 ${ev.content_sha256}\` · \`chain ${ev.chain_sha256}\`\n\n`;
  });

  const timeline = inc.timeline || [];
  if (timeline.length) {
    md += `## Timeline\n\n`;
    // stored newest-first; a report reads oldest-first
    for (const ev of [...timeline].reverse()) {
      const what = ev.kind === 'status_change'
        ? `status ${ev.old_value || '?'} → ${ev.new_value || '?'}`
        : ev.note || ev.kind;
      md += `- **${minute(ev.at)}** (${ev.actor || 'system'}) — ${what}\n`;
    }
    md += `\n`;
  }

  const pending = d.enrichment?.candidates || [];
  if (pending.length) {
    md += `## Enrichment candidates awaiting review (${pending.length})\n\n`;
    for (const c of pending) {
      md += `- [${c.candidate_type.replace('_', ' ')}] ${c.title || c.source_ref}`
          + (c.reason ? ` — ${c.reason}` : '') + `\n`;
    }
    md += `\n`;
  }

  md += `---\n\n*Generated by Aunoo AI Brand Watcher. Parts of this report (agent brief, `
      + `Five Signals verdicts) are AI-generated and should be verified before external use.*\n`;
  return md;
}

// ─── Interactive HTML (house style) ──────────────────────────────────────────

/** Minimal markdown → HTML for the agent brief (headings, bold, bullets). */
function briefHtml(md: string): string {
  const lines = md.split('\n');
  let out = '', inList = false;
  for (const raw of lines) {
    const line = raw.trimEnd();
    const bold = (s: string) => esc(s).replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>');
    if (/^\s*[-*]\s+/.test(line)) {
      if (!inList) { out += '<ul>'; inList = true; }
      out += `<li>${bold(line.replace(/^\s*[-*]\s+/, ''))}</li>`;
      continue;
    }
    if (inList) { out += '</ul>'; inList = false; }
    if (/^###\s+/.test(line)) out += `<h4>${bold(line.replace(/^###\s+/, ''))}</h4>`;
    else if (/^##\s+/.test(line)) out += `<h3>${bold(line.replace(/^##\s+/, ''))}</h3>`;
    else if (/^#\s+/.test(line)) out += `<h3>${bold(line.replace(/^#\s+/, ''))}</h3>`;
    else if (line) out += `<p>${bold(line)}</p>`;
  }
  if (inList) out += '</ul>';
  return out;
}

const BAND_COLOR: Record<string, string> = {
  good: '#16a34a', warn: '#E8A838', bad: '#dc2626', nodata: '#9ca3af',
};

export function buildIncidentReportHtml(d: IncidentReportData): string {
  const inc = d.incident;
  const run = d.enrichment?.run;
  const gen = new Date().toISOString().slice(0, 16).replace('T', ' ') + ' UTC';
  const sevColor = inc.severity === 'critical' || inc.severity === 'high' ? 'var(--neg)'
    : inc.severity === 'medium' ? 'var(--amber)' : 'var(--live)';

  const statCard = (label: string, val: string, sub = '') =>
    `<div class="stat"><div class="eyebrow">${esc(label)}</div><div class="val">${esc(val)}</div>${sub ? `<div class="sub">${esc(sub)}</div>` : ''}</div>`;

  const screened = screenedEvidence(d);
  const signalsHtml = screened.length ? `<section id="signals"><h2>Five Signals screening</h2>
    ${screened.map(ev => {
      const s = (ev as any).signals_summary;
      return `<div class="card">
        <h3>${ev.source_ref ? `<a href="${esc(ev.source_ref)}" target="_blank" rel="noopener">${esc(ev.title || ev.source_ref)}</a>` : esc(ev.title || '')}
          <span class="muted" style="font-weight:400">${esc(hostOf(ev.source_ref))}</span></h3>
        <p style="margin:4px 0 10px"><span class="chip ${s.verdict === 'corroborated' ? 'pos' : s.verdict ? 'med' : 'neu'}">verdict: ${esc(s.verdict || 'n/a')}</span>
          <span class="chip neu">composite ${s.composite ?? '—'}/100</span></p>
        ${(s.signals || []).map((sig: any) => `<div class="bar-row">
          <span class="bar-label" title="${esc(SIG_TITLES[sig.key] || sig.key)}">${esc(SIG_TITLES[sig.key] || sig.key)}</span>
          <span class="bar-track">${sig.score != null ? `<span class="bar-fill" style="width:${Math.max(2, Math.min(100, sig.score))}%;background:${BAND_COLOR[sig.band || 'nodata']}"></span>` : ''}</span>
          <span class="bar-val">${sig.score != null ? `${sig.score}/100 (${sig.band})` : 'no data'}</span>
        </div>`).join('')}
      </div>`;
    }).join('')}
    <p class="muted">Screens run two engines on the Aunoo platform — claim validation and social story-reach — composed into five 0–100 signals. Propagation measures spread magnitude (wide spread of an adverse story is the risky case).</p>
  </section>` : '';

  const briefSection = run?.brief ? `<section id="brief"><h2>Agent brief</h2>
    <div class="card prose">${briefHtml(run.brief)}
      <p class="muted" style="margin-top:10px">Written by the enrichment agent${run.finished_at ? ` on ${esc(minute(run.finished_at))}` : ''} — AI-generated from the attached material; verify before acting.</p>
    </div></section>` : '';

  const evidenceHtml = `<section id="evidence"><h2>Evidence (${(inc.evidence || []).length})</h2>
    <p class="muted" style="margin:0 0 10px">Append-only, hash-chained locker — entries can never be edited or removed. sha256 digests below allow independent verification.</p>
    ${(inc.evidence || []).map((ev, i) => {
      const s = (ev as any).signals_summary;
      const chips = s?.status === 'completed'
        ? `<span class="sigchips">${(s.signals || []).map((sig: any) =>
            `<span class="sigchip" style="background:${BAND_COLOR[sig.band || 'nodata']}" title="${esc(SIG_TITLES[sig.key] || sig.key)}: ${sig.score != null ? sig.score + '/100' : 'no data'}">${SIG_SHORT[sig.key] || '?'}</span>`).join('')}</span>`
        : '';
      return `<details class="alert evi" ${i < 3 ? 'open' : ''}>
        <summary><span class="chev">▸</span>
          <span class="chip neu">${esc(ev.evidence_type.replace('_', ' '))}</span>
          <span class="a-cat">${ev.source_ref && String(ev.source_ref).startsWith('http')
            ? `<a href="${esc(ev.source_ref)}" target="_blank" rel="noopener">${esc(ev.title || ev.source_ref)}</a> <span class="muted" style="font-weight:400">${esc(hostOf(ev.source_ref))}</span>`
            : esc(ev.title || ev.source_ref || '(untitled)')}</span>
          ${chips}
          <span class="a-meta">${esc(minute(ev.captured_at))}</span></summary>
        <div class="a-body">
          ${ev.content ? `<p style="white-space:pre-wrap">${esc(String(ev.content).slice(0, 2000))}</p>` : ''}
          <p class="muted">captured by ${esc(ev.captured_by || 'unknown')} · sha256 <code>${esc(ev.content_sha256)}</code> · chain <code>${esc(ev.chain_sha256)}</code></p>
        </div></details>`;
    }).join('')}
  </section>`;

  const timeline = [...(inc.timeline || [])].reverse();
  const timelineHtml = timeline.length ? `<section id="timeline"><h2>Timeline</h2><div class="card">
    ${timeline.map(ev => {
      const what = ev.kind === 'status_change'
        ? `status <b>${esc(ev.old_value || '?')}</b> → <b>${esc(ev.new_value || '?')}</b>`
        : esc(ev.note || ev.kind);
      return `<div class="tl-row"><span class="tl-when">${esc(minute(ev.at))}</span>
        <span class="tl-actor">${esc(ev.actor || 'system')}</span>
        <span class="tl-what">${what}</span></div>`;
    }).join('')}
  </div></section>` : '';

  const pending = d.enrichment?.candidates || [];
  const pendingHtml = pending.length ? `<section id="candidates"><h2>Enrichment candidates awaiting review (${pending.length})</h2>
    <div class="card">${pending.map(c => `<div class="tl-row">
      <span class="chip neu">${esc(c.candidate_type.replace('_', ' '))}</span>
      <span class="tl-what">${c.source_ref && String(c.source_ref).startsWith('http') ? `<a href="${esc(c.source_ref)}" target="_blank" rel="noopener">${esc(c.title || c.source_ref)}</a>` : esc(c.title || c.source_ref)}
        ${c.reason ? `<span class="muted"> — ${esc(c.reason)}</span>` : ''}</span></div>`).join('')}
      <p class="muted" style="margin-top:8px">Found by the enrichment agent; not part of the evidence locker until an analyst attaches them.</p>
    </div></section>` : '';

  return `<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Incident #${inc.id} — ${esc(inc.title)}</title>
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
.nav a:hover{background:var(--accent-tint);color:var(--accent);text-decoration:none}
.search{margin-left:8px;padding:5px 10px;border:1px solid var(--border);border-radius:999px;font-size:12.5px;width:170px;background:#fff}
main{max-width:900px;margin:0 auto;padding:22px 20px 60px}
h1{font-size:22px;margin:6px 0 2px}.lead{color:var(--muted);margin:0 0 18px}
section{margin:26px 0;scroll-margin-top:64px}
section>h2{font-size:13px;text-transform:uppercase;letter-spacing:.06em;color:var(--accent);margin:0 0 12px;font-weight:700}
.card{background:var(--card);border:1px solid var(--border);border-radius:var(--r);padding:16px 18px;margin-bottom:14px}
.card h3{font-size:13.5px;margin:0 0 8px;color:var(--text)}
.stat-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:14px}
.stat{background:var(--card);border:1px solid var(--border);border-radius:var(--r);padding:14px 16px}
.stat .eyebrow{font-size:10.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);font-weight:600}
.stat .val{font-size:22px;font-weight:700;margin-top:4px;line-height:1.1}
.stat .sub{font-size:11.5px;color:var(--muted);margin-top:2px}
.chip{font-size:10.5px;padding:1px 7px;border-radius:999px}
.chip.pos{background:#e7f6ec;color:#15803d}.chip.neg{background:#fdeaea;color:#b91c1c}.chip.neu{background:#eef0f5;color:#475569}.chip.med{background:#fbeedd;color:#b45309}
.bar-row{display:flex;align-items:center;gap:10px;padding:3px 0}
.bar-label{font-size:12.5px;color:var(--text2);width:190px;flex-shrink:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.bar-track{flex:1;height:14px;background:#eef0f5;border-radius:999px;overflow:hidden}
.bar-fill{display:block;height:100%;border-radius:999px}
.bar-val{font-size:11.5px;color:var(--muted);width:110px;text-align:right;flex-shrink:0;font-variant-numeric:tabular-nums}
details.alert{border:1px solid var(--border);border-radius:10px;margin-bottom:8px;overflow:hidden;background:#fff}
details.alert>summary{list-style:none;cursor:pointer;display:flex;align-items:center;gap:10px;padding:9px 12px;flex-wrap:wrap}
details.alert>summary::-webkit-details-marker{display:none}
details.alert .chev{color:var(--muted);transition:transform .15s}details.alert[open] .chev{transform:rotate(90deg)}
.a-cat{flex:1;font-weight:600;font-size:13px;min-width:200px}.a-meta{font-size:11.5px;color:var(--muted);font-variant-numeric:tabular-nums}
.a-body{padding:4px 12px 10px 34px;border-top:1px solid #f0f0f4;font-size:12.5px;color:var(--text2)}
.a-body code{font-size:10px;word-break:break-all}
.sigchips{display:inline-flex;gap:1px;border-radius:999px;overflow:hidden}
.sigchip{color:#fff;font-size:9px;font-weight:700;padding:1px 5px}
.tl-row{display:flex;gap:10px;padding:5px 0;border-bottom:1px solid #f4f4f7;font-size:12.5px;align-items:baseline}
.tl-row:last-child{border-bottom:none}
.tl-when{color:var(--muted);font-variant-numeric:tabular-nums;flex-shrink:0;width:120px}
.tl-actor{color:var(--accent);flex-shrink:0;width:110px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.tl-what{flex:1;color:var(--text2)}
.prose h3{font-size:14px;margin:14px 0 6px;color:var(--accent)}.prose h4{font-size:13px;margin:10px 0 4px}
.prose p{margin:6px 0;color:var(--text2)}.prose ul{margin:6px 0;padding-left:20px}.prose li{margin:3px 0;color:var(--text2)}
.muted{color:var(--muted);font-size:12px;font-style:italic}
.sev{font-weight:700;text-transform:uppercase;font-size:11px}
footer{margin-top:40px;padding-top:16px;border-top:1px solid var(--border);color:var(--muted);font-size:11.5px;text-align:center}
.hidden{display:none!important}
@media(max-width:700px){.stat-grid{grid-template-columns:1fr 1fr}.bar-label{width:120px}.nav{width:100%;order:3}}
@media print{.topnav{position:static}.nav,.search{display:none}details.alert{break-inside:avoid}details.alert>summary{pointer-events:none}}
</style></head>
<body>
<header class="topnav">
  <span class="brand">Incident report · <b>#${inc.id}</b></span>
  <span class="meta">${esc(inc.brand_name || '')} · generated ${gen}</span>
  <nav class="nav">
    <a href="#overview">Overview</a>
    ${screened.length ? '<a href="#signals">Signals</a>' : ''}
    ${run?.brief ? '<a href="#brief">Brief</a>' : ''}
    <a href="#evidence">Evidence</a>
    ${timeline.length ? '<a href="#timeline">Timeline</a>' : ''}
  </nav>
  <input class="search" id="q" type="search" placeholder="Filter evidence…" />
</header>
<main>
  <h1>#${inc.id} ${esc(inc.title)}</h1>
  <p class="lead">${esc(inc.brand_name || '')} · opened ${esc(day(inc.created_at))} by ${esc(inc.created_by || 'unknown')}${inc.resolved_at ? ` · resolved ${esc(day(inc.resolved_at))}` : ''}</p>

  <section id="overview">
    <h2>Overview</h2>
    <div class="stat-grid">
      ${statCard('Severity', inc.severity.toUpperCase()).replace('class="val"', `class="val" style="color:${sevColor}"`)}
      ${statCard('Status', inc.status)}
      ${statCard('Evidence items', String((inc.evidence || []).length), 'hash-chained')}
      ${statCard('Owner', inc.owner || '—')}
    </div>
    ${inc.description ? `<div class="card"><p style="margin:0;color:var(--text2)">${esc(inc.description)}</p></div>` : ''}
  </section>

  ${signalsHtml}
  ${briefSection}
  ${evidenceHtml}
  ${timelineHtml}
  ${pendingHtml}

  <footer>Generated by Aunoo AI Brand Watcher · ${gen}<br>
  Parts of this report (agent brief, Five Signals verdicts) are AI-generated and should be verified before external use.</footer>
</main>
<script>
(function(){
  var q=document.getElementById('q');
  if(!q)return;
  q.addEventListener('input',function(){
    var t=q.value.trim().toLowerCase();
    document.querySelectorAll('details.evi, .tl-row').forEach(function(el){
      el.classList.toggle('hidden', !!t && el.textContent.toLowerCase().indexOf(t)<0);
    });
  });
})();
</script>
</body></html>`;
}

// ─── PDF (text-based, jsPDF) ─────────────────────────────────────────────────

export function buildIncidentReportPdf(d: IncidentReportData): void {
  const inc = d.incident;
  const run = d.enrichment?.run;
  const pdf = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4' });
  const pageWidth = 210, pageHeight = 297, margin = 15;
  const contentWidth = pageWidth - margin * 2;
  let y = margin;

  const checkPageBreak = (needed: number) => {
    if (y + needed > pageHeight - margin) { pdf.addPage(); y = margin; }
  };
  const addText = (text: string, fontSize: number, isBold = false, color: number[] = [0, 0, 0]) => {
    pdf.setFontSize(fontSize);
    pdf.setFont('helvetica', isBold ? 'bold' : 'normal');
    pdf.setTextColor(color[0], color[1], color[2]);
    const lines = pdf.splitTextToSize(text, contentWidth);
    const lineHeight = fontSize * 0.4;
    checkPageBreak(lines.length * lineHeight + 2);
    pdf.text(lines, margin, y);
    y += lines.length * lineHeight + 2;
  };

  const sevColor = inc.severity === 'critical' || inc.severity === 'high'
    ? [220, 38, 38] : inc.severity === 'medium' ? [180, 120, 0] : [22, 130, 60];

  addText(`Incident #${inc.id}: ${inc.title}`, 17, true, [214, 64, 159]);
  addText(`${inc.brand_name || ''} · Severity: ${inc.severity.toUpperCase()} · Status: ${inc.status}${inc.owner ? ` · Owner: ${inc.owner}` : ''}`, 11, true, sevColor);
  addText(`Opened ${day(inc.created_at)} by ${inc.created_by || 'unknown'}${inc.resolved_at ? ` · Resolved ${day(inc.resolved_at)}` : ''} · Report generated ${new Date().toLocaleString()}`, 9, false, [120, 120, 120]);
  y += 3;
  if (inc.description) { addText(inc.description, 10.5); y += 3; }

  const screened = screenedEvidence(d);
  if (screened.length) {
    checkPageBreak(20);
    addText('Five Signals screening', 13, true, [214, 64, 159]);
    for (const ev of screened) {
      const s = (ev as any).signals_summary;
      checkPageBreak(30);
      addText(ev.title || ev.source_ref || '', 11, true);
      if (ev.source_ref) addText(ev.source_ref, 8, false, [100, 100, 180]);
      addText(`Verdict: ${s.verdict || 'n/a'} · Composite: ${s.composite ?? 'n/a'}/100`, 10, true);
      for (const sig of s.signals || []) {
        addText(`  ${SIG_TITLES[sig.key] || sig.key}: ${sig.score != null ? `${sig.score}/100 (${sig.band})` : 'no data'}`, 9.5, false, [80, 80, 80]);
      }
      y += 3;
    }
  }

  if (run?.brief) {
    checkPageBreak(25);
    addText('Agent brief', 13, true, [214, 64, 159]);
    addText(`AI-generated${run.finished_at ? ` ${minute(run.finished_at)}` : ''} — verify before acting.`, 8.5, false, [130, 130, 130]);
    // Strip markdown headers/bold for the PDF's plain text
    const plain = run.brief.replace(/^#{1,4}\s+/gm, '').replace(/\*\*/g, '');
    addText(plain, 10);
    y += 3;
  }

  checkPageBreak(20);
  addText(`Evidence (${(inc.evidence || []).length}) — append-only, hash-chained`, 13, true, [214, 64, 159]);
  (inc.evidence || []).forEach((ev, i) => {
    checkPageBreak(24);
    addText(`${i + 1}. [${ev.evidence_type.replace('_', ' ')}] ${ev.title || ev.source_ref || '(untitled)'}`, 10.5, true);
    if (ev.source_ref && String(ev.source_ref).startsWith('http')) addText(ev.source_ref, 8, false, [100, 100, 180]);
    addText(`Captured ${minute(ev.captured_at)} by ${ev.captured_by || 'unknown'}`, 8.5, false, [130, 130, 130]);
    if (ev.content) addText(String(ev.content).slice(0, 600), 9, false, [60, 60, 60]);
    addText(`sha256 ${ev.content_sha256} · chain ${ev.chain_sha256}`, 7, false, [150, 150, 150]);
    y += 2;
  });

  const timeline = [...(inc.timeline || [])].reverse();
  if (timeline.length) {
    checkPageBreak(20);
    addText('Timeline', 13, true, [214, 64, 159]);
    for (const ev of timeline) {
      const what = ev.kind === 'status_change'
        ? `status ${ev.old_value || '?'} -> ${ev.new_value || '?'}`
        : ev.note || ev.kind;
      addText(`${minute(ev.at)}  ${ev.actor || 'system'} — ${what}`, 9, false, [70, 70, 70]);
    }
  }

  const totalPages = pdf.getNumberOfPages();
  for (let i = 1; i <= totalPages; i++) {
    pdf.setPage(i);
    pdf.setFontSize(8);
    pdf.setTextColor(150, 150, 150);
    pdf.text(`Page ${i} of ${totalPages}`, pageWidth / 2, pageHeight - 10, { align: 'center' });
    pdf.text('Generated by Aunoo AI Brand Watcher — AI-generated content, verify before external use', pageWidth / 2, pageHeight - 5, { align: 'center' });
  }
  pdf.save(`incident-${inc.id}-${slug(inc.title)}-${new Date().toISOString().slice(0, 10)}.pdf`);
}

// ─── Entry point ─────────────────────────────────────────────────────────────

export function downloadIncidentReport(d: IncidentReportData, format: 'md' | 'html' | 'pdf'): void {
  const base = `incident-${d.incident.id}-${slug(d.incident.title)}-${new Date().toISOString().slice(0, 10)}`;
  if (format === 'md') download(buildIncidentReportMarkdown(d), `${base}.md`, 'text/markdown');
  else if (format === 'html') download(buildIncidentReportHtml(d), `${base}.html`, 'text/html');
  else buildIncidentReportPdf(d);
}
