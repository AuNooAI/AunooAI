/**
 * Incident report exports — Markdown, text-based PDF, and a self-contained
 * interactive HTML document (house style, matches brandReportHtml.ts).
 *
 * Everything is generated client-side from the data the incident panel
 * already holds: the incident detail (evidence + timeline + Five Signals
 * summaries) and the latest enrichment state (agent brief + stats). The one
 * network call is an optional translation pass — non-English evidence is sent
 * to the backend for an AI English translation embedded under the original.
 *
 * The evidence locker stores raw captures (append-only, some with literal
 * "\n" sequences and lost-emoji U+FFFD runs from upstream ingestion), so all
 * text is cleaned at render time and titles are derived from evidence meta
 * (author/platform) rather than raw post text.
 */
import { jsPDF } from 'jspdf';
import type { BWIncidentDetail, BWIncidentEvent } from './brandWatcherApi';
import { incidentReportSummary, translateForReport } from './brandWatcherApi';

export interface IncidentReportData {
  incident: BWIncidentDetail & { description?: string | null; owner?: string | null };
  enrichment?: {
    run?: { id: number; status: string; brief?: string | null; stats?: any;
            finished_at?: string | null; started_by?: string | null } | null;
    candidates?: any[];
    /** Decided candidates (attached/dismissed) with who/when — disposition audit. */
    history?: { candidate_type: string; source_ref?: string | null; title?: string | null;
                reason?: string | null; state: string; decided_by?: string | null;
                decided_at?: string | null }[];
    counts?: Record<string, number>;
  } | null;
}

/** id → AI English translation, keyed by String(evidence.id). */
type TranslationMap = Record<string, { language: string; text: string }>;

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
const hhmm = (iso?: string | null) => (iso || '').slice(11, 16);
const hostOf = (url?: string | null) => {
  try { return url ? new URL(url).hostname.replace(/^www\./, '') : ''; } catch { return ''; }
};
const slug = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 50);

/** Undo ingestion artifacts: literal "\n" sequences, U+FFFD runs where astral
 * emoji were lost upstream, and whitespace noise. Applied to ALL report text. */
function cleanText(s: any): string {
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

// ─── Language detection (report-side heuristic; the model double-checks) ────

// Cyrillic, Armenian, Hebrew, Arabic, Syriac/Thaana, Devanagari→Sinhala,
// Thai/Lao, Hangul jamo, CJK, kana, Hangul syllables
const NON_LATIN_RE = /[Ѐ-ӿ԰-֏֐-׿؀-ۿ܀-޿ऀ-෿฀-໿ᄀ-ᇿ一-鿿぀-ヿ가-힯]/g;

function needsTranslation(s: string): boolean {
  const t = cleanText(s);
  const nonLatin = (t.match(NON_LATIN_RE) || []).length;
  if (nonLatin < 15) return false;
  const latin = (t.match(/[A-Za-z]/g) || []).length;
  return nonLatin / (nonLatin + latin) > 0.3;
}

// ─── Display titles (never raw post text) ───────────────────────────────────

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

/** Client-facing label for any evidence/candidate row. Prefers meta author +
 * platform; falls back to the source URL's shape; only uses (cleaned,
 * truncated) text when nothing better exists. */
function displayTitle(title?: string | null, sourceRef?: string | null, meta?: any): string {
  const t = cleanText(title || '');
  const briefMatch = /^Agent incident brief(?:\s*\(run #(\d+)\))?/i.exec(t);
  if (briefMatch) return 'AI monitoring brief';
  const author = meta?.author || meta?.social_meta?.author;
  const platformKey = String(meta?.platform || meta?.social_meta?.platform || '').toLowerCase();
  const urlInfo = authorFromUrl(sourceRef);
  const platform = PLATFORM_LABEL[platformKey] || urlInfo.platform || '';
  const handle = author || urlInfo.handle;
  if (handle) return `Post by @${handle}${platform ? ` on ${platform}` : ''}`;
  const fromPostBy = /^Post by (@[^\s]+)/.exec(t);
  if (fromPostBy) return `Post by ${fromPostBy[1]}${platform ? ` on ${platform}` : ''}`;
  if (platform && t) return `${platform} post: “${truncate(t, 70)}”`;
  if (platform) return `${platform} post`;
  return truncate(t || String(sourceRef || '(untitled)'), 90);
}

/** "18 likes · 4 reposts · 3 comments" from evidence meta, or ''. */
function engagementLine(meta?: any): string {
  const e = meta?.social_meta || meta?.engagement || {};
  const parts: string[] = [];
  if (e.likes != null) parts.push(`${e.likes} like${e.likes === 1 ? '' : 's'}`);
  if (e.reposts != null) parts.push(`${e.reposts} repost${e.reposts === 1 ? '' : 's'}`);
  if (e.comments != null) parts.push(`${e.comments} comment${e.comments === 1 ? '' : 's'}`);
  return parts.join(' · ');
}

const postedDate = (meta?: any): string => day(meta?.publication_date || null);

// ─── Linkify (after HTML-escaping) ───────────────────────────────────────────

/** Turn URLs inside already-escaped text into anchors. Display-truncated URLs
 * (ending in … or ..) stay plain text — a faked link would 404. */
function linkifyEscaped(escaped: string): string {
  return escaped.replace(/\b(https?:\/\/|www\.)[^\s<>"']+/g, (m) => {
    if (/\.{2,}$|…$/.test(m)) return m; // display-truncated URL — a faked link would 404
    const trimmed = m.replace(/[).,;:!?]+$/, '');
    const trail = m.slice(trimmed.length);
    const href = trimmed.startsWith('http') ? trimmed : `https://${trimmed}`;
    return `<a href="${href}" target="_blank" rel="noopener">${trimmed}</a>${trail}`;
  });
}

const bodyHtml = (raw: string, limit = 2000) =>
  linkifyEscaped(esc(truncateBlock(cleanText(raw), limit)));

function truncateBlock(s: string, n: number): string {
  return s.length <= n ? s : s.slice(0, n) + ' …';
}

// ─── Timeline (merged story + case activity, humanized) ─────────────────────

interface TimelineRow { at: string; actor: string; what: string; whatHtml?: string; isSource?: boolean }

const ACTOR_LABEL: Record<string, string> = {
  'agent:auto:create': 'agent (auto)', 'agent:user': 'agent',
  'agent:triage': 'agent (triage)', 'agent:monitor': 'agent (monitor)',
};
const actorLabel = (a?: string | null) => ACTOR_LABEL[a || ''] || a || 'system';

function humanizeEvent(ev: BWIncidentEvent, titleLookup: (raw: string) => string): string {
  const note = cleanText(ev.note || '');
  switch (ev.kind) {
    case 'created':
      return `Incident opened${ev.new_value ? ` at severity ${ev.new_value}` : ''}`;
    case 'status_change':
      return `Status changed: ${ev.old_value || '?'} → ${ev.new_value || '?'}${note ? ` — ${truncate(note, 140)}` : ''}`;
    case 'severity_change':
      return `Severity changed: ${ev.old_value || '?'} → ${ev.new_value || '?'}${note ? ` — ${truncate(note, 140)}` : ''}`;
    case 'owner_change':
      return `Owner changed: ${ev.old_value || '—'} → ${ev.new_value || '—'}`;
    case 'evidence_added':
      return `Evidence attached: ${titleLookup(note)}`;
    case 'agent_brief':
      return 'AI monitoring brief updated (full text in the Brief section)';
    case 'enrichment': {
      const m = /^run #(\d+):\s*(.*)$/s.exec(note);
      return m ? `Agent research sweep: ${truncate(m[2], 220)}` : `Agent research sweep: ${truncate(note, 220)}`;
    }
    case 'agent_suggestion':
      return `Agent suggestion: ${truncate(note, 220)}`;
    case 'note': {
      // The attach action logs "attached from agent run #N: <raw title>" — the
      // matching evidence_added row already names the item, so keep provenance only.
      const m = /^attached from agent run #(\d+)/.exec(note);
      if (m) return `Attached an agent-found item (from research sweep #${m[1]})`;
      return truncate(note, 300) || 'Note added';
    }
    default:
      return truncate(note, 220) || ev.kind;
  }
}

/** Chronological rows: original source publication dates first-class, so the
 * report reads as a story (what was posted when), then case activity. */
function buildTimelineRows(d: IncidentReportData): TimelineRow[] {
  const rows: TimelineRow[] = [];
  // evidence_added notes carry the stored (raw) title — map raw → display title
  const titleLookup = (raw: string): string => {
    const key = cleanText(raw).slice(0, 60);
    const hit = key ? (d.incident.evidence || []).find(ev =>
      cleanText(ev.title || '').slice(0, 60) === key) : undefined;
    return hit ? displayTitle(hit.title, hit.source_ref, (hit as any).meta)
               : displayTitle(raw, null, null);
  };
  for (const ev of d.incident.evidence || []) {
    const meta = (ev as any).meta;
    const pub = meta?.publication_date;
    if (!pub) continue;
    const title = displayTitle(ev.title, ev.source_ref, meta);
    const link = ev.source_ref && String(ev.source_ref).startsWith('http')
      ? `<a href="${esc(ev.source_ref)}" target="_blank" rel="noopener">${esc(title)}</a>` : esc(title);
    rows.push({
      at: String(pub), actor: 'source', isSource: true,
      what: `Published: ${title}`, whatHtml: `Published: ${link}`,
    });
  }
  for (const ev of d.incident.timeline || []) {
    if (!ev.at) continue;
    rows.push({ at: ev.at, actor: actorLabel(ev.actor), what: humanizeEvent(ev, titleLookup) });
  }
  rows.sort((a, b) => a.at.localeCompare(b.at));
  return rows;
}

const dayHeading = (iso: string) => {
  try {
    return new Date(iso.slice(0, 10) + 'T00:00:00Z').toLocaleDateString('en-GB', {
      weekday: 'long', day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC',
    });
  } catch { return iso.slice(0, 10); }
};

// ─── Translations ────────────────────────────────────────────────────────────

/** Key facts computed from the evidence itself — the non-AI half of the
 * Situation section. */
function situationFacts(d: IncidentReportData): string[] {
  const items = (d.incident.evidence || []).filter(ev =>
    ev.evidence_type === 'article' || ev.evidence_type === 'social_post');
  const dates = items.map(ev => postedDate((ev as any).meta)).filter(Boolean).sort();
  const facts: string[] = [];
  if (dates.length) {
    facts.push(dates[0] === dates[dates.length - 1]
      ? `Source material from ${dates[0]}`
      : `Source material spans ${dates[0]} → ${dates[dates.length - 1]}`);
  }
  const platCounts: Record<string, number> = {};
  let engagement = 0;
  for (const ev of items) {
    const meta = (ev as any).meta || {};
    const key = String(meta.platform || meta.social_meta?.platform || '').toLowerCase();
    const plat = PLATFORM_LABEL[key] || (ev.evidence_type === 'article' && !key ? 'News' : '');
    if (plat) platCounts[plat] = (platCounts[plat] || 0) + 1;
    const sm = meta.social_meta || meta.engagement || {};
    engagement += (Number(sm.likes) || 0) + (Number(sm.reposts) || 0) + (Number(sm.comments) || 0);
  }
  const plats = Object.entries(platCounts).map(([n, c]) => `${c} on ${n}`).join(', ');
  if (items.length) facts.push(`${items.length} attached item${items.length === 1 ? '' : 's'}${plats ? ` (${plats})` : ''}`);
  if (engagement) facts.push(`${engagement} total engagement observed`);
  const verdicts = (d.incident.evidence || [])
    .map(ev => (ev as any).signals_summary)
    .filter(s => s?.status === 'completed' && s.verdict);
  if (verdicts.length) facts.push(`credibility screening: ${verdicts.map((s: any) => s.verdict).join(', ')}`);
  return facts;
}

async function fetchSituationSummary(d: IncidentReportData): Promise<string> {
  try {
    return await incidentReportSummary(d.incident.id);
  } catch (e) {
    console.error('report summary failed — exporting without it', e);
    return '';
  }
}

async function fetchTranslations(d: IncidentReportData): Promise<TranslationMap> {
  const items = (d.incident.evidence || [])
    .filter(ev => ev.content && needsTranslation(String(ev.content)))
    .slice(0, 10)
    .map(ev => ({ id: String(ev.id), text: cleanText(String(ev.content)).slice(0, 1500) }));
  if (!items.length) return {};
  try {
    return await translateForReport(items);
  } catch (e) {
    console.error('report translation failed — exporting without translations', e);
    return {};
  }
}

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

export function buildIncidentReportMarkdown(d: IncidentReportData, trans: TranslationMap = {}, situation = ''): string {
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

  const facts = situationFacts(d);
  if (inc.description || situation || facts.length) {
    md += `## Situation\n\n`;
    if (inc.description) md += `${cleanText(inc.description)}\n\n`;
    if (situation) md += `${situation}\n\n*AI-generated situation summary — verify before external use.*\n\n`;
    if (facts.length) md += facts.map(f => `- ${f}`).join('\n') + '\n\n';
  }

  const screened = screenedEvidence(d);
  if (screened.length) {
    md += `## Five Signals screening\n\n`;
    md += `Attached articles screened via the Aunoo validation platform (claim validation + social propagation):\n\n`;
    for (const ev of screened) {
      const s = (ev as any).signals_summary;
      md += `### ${displayTitle(ev.title, ev.source_ref, (ev as any).meta)}\n\n`;
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
    md += `## AI monitoring brief\n\n`;
    md += `*Written by the enrichment agent${run.finished_at ? ` on ${minute(run.finished_at)}` : ''}. `;
    md += `AI-generated from the attached material — verify before acting.*\n\n`;
    md += `${run.brief}\n\n`;
  }

  md += `## Evidence (${(inc.evidence || []).length})\n\n`;
  md += `The evidence locker is append-only and hash-chained; each entry's sha256 is listed for audit.\n\n`;
  (inc.evidence || []).forEach((ev, i) => {
    const meta = (ev as any).meta;
    md += `### ${i + 1}. ${displayTitle(ev.title, ev.source_ref, meta)}\n\n`;
    if (ev.source_ref && String(ev.source_ref).startsWith('http')) md += `<${ev.source_ref}>\n\n`;
    const facts: string[] = [];
    if (postedDate(meta)) facts.push(`Posted ${postedDate(meta)}`);
    const eng = engagementLine(meta);
    if (eng) facts.push(eng);
    if (meta?.sentiment) facts.push(`sentiment: ${meta.sentiment}`);
    facts.push(`captured ${minute(ev.captured_at)} by ${ev.captured_by || 'unknown'}`);
    md += `*${facts.join(' · ')}*\n\n`;
    if (ev.content) md += `${truncateBlock(cleanText(String(ev.content)), 1500)}\n\n`;
    const tr = trans[String(ev.id)];
    if (tr) md += `> **English translation (from ${tr.language}, AI-generated):** ${tr.text}\n\n`;
    md += `\`sha256 ${ev.content_sha256}\` · \`chain ${ev.chain_sha256}\`\n\n`;
  });

  const rows = buildTimelineRows(d);
  if (rows.length) {
    md += `## Timeline\n\n`;
    md += `Source publication dates and case activity, oldest first.\n\n`;
    let lastDay = '';
    for (const r of rows) {
      if (day(r.at) !== lastDay) { lastDay = day(r.at); md += `\n**${dayHeading(r.at)}**\n\n`; }
      md += `- ${hhmm(r.at) || '—'} · *${r.actor}* — ${r.what}\n`;
    }
    md += `\n`;
  }

  const pending = d.enrichment?.candidates || [];
  if (pending.length) {
    md += `## Enrichment candidates awaiting review (${pending.length})\n\n`;
    for (const c of pending) {
      md += `- [${c.candidate_type.replace('_', ' ')}] ${displayTitle(c.title, c.source_ref, null)}`
          + (c.reason ? ` — ${c.reason}` : '') + `\n`;
    }
    md += `\n`;
  }

  const history = d.enrichment?.history || [];
  if (history.length) {
    md += `## Candidate disposition history (${history.length})\n\n`;
    md += `Every agent-proposed item an analyst has ruled on. Dismissed items are never re-proposed.\n\n`;
    md += `| Decision | Type | Item | Found because | Decided by | When |\n|---|---|---|---|---|---|\n`;
    for (const h of history) {
      const item = displayTitle(h.title, h.source_ref, null).replace(/\|/g, '\\|');
      md += `| ${h.state} | ${h.candidate_type.replace('_', ' ')} | ${item} | `
          + `${(h.reason || '').replace(/\|/g, '\\|')} | ${h.decided_by || ''} | ${minute(h.decided_at)} |\n`;
    }
    md += `\n`;
  }

  md += `---\n\n*Generated by Aunoo AI Brand Watcher. Parts of this report (AI monitoring brief, `
      + `Five Signals verdicts, translations) are AI-generated and should be verified before external use.*\n`;
  return md;
}

// ─── Interactive HTML (house style) ──────────────────────────────────────────

/** Minimal markdown → HTML for the agent brief (headings, bold, bullets),
 * with URLs linkified. */
function briefHtml(md: string): string {
  const lines = md.split('\n');
  let out = '', inList = false;
  for (const raw of lines) {
    const line = raw.trimEnd();
    const fmt = (s: string) => linkifyEscaped(esc(s)).replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>');
    if (/^\s*[-*]\s+/.test(line)) {
      if (!inList) { out += '<ul>'; inList = true; }
      out += `<li>${fmt(line.replace(/^\s*[-*]\s+/, ''))}</li>`;
      continue;
    }
    if (inList) { out += '</ul>'; inList = false; }
    if (/^###\s+/.test(line)) out += `<h4>${fmt(line.replace(/^###\s+/, ''))}</h4>`;
    else if (/^##\s+/.test(line)) out += `<h3>${fmt(line.replace(/^##\s+/, ''))}</h3>`;
    else if (/^#\s+/.test(line)) out += `<h3>${fmt(line.replace(/^#\s+/, ''))}</h3>`;
    else if (line) out += `<p>${fmt(line)}</p>`;
  }
  if (inList) out += '</ul>';
  return out;
}

const BAND_COLOR: Record<string, string> = {
  good: '#16a34a', warn: '#E8A838', bad: '#dc2626', nodata: '#9ca3af',
};

export function buildIncidentReportHtml(d: IncidentReportData, trans: TranslationMap = {}, situation = ''): string {
  const inc = d.incident;
  const run = d.enrichment?.run;
  const gen = new Date().toISOString().slice(0, 16).replace('T', ' ') + ' UTC';
  const sevColor = inc.severity === 'critical' || inc.severity === 'high' ? 'var(--neg)'
    : inc.severity === 'medium' ? 'var(--amber)' : 'var(--live)';

  const statCard = (label: string, val: string, sub = '') =>
    `<div class="stat"><div class="eyebrow">${esc(label)}</div><div class="val">${esc(val)}</div>${sub ? `<div class="sub">${esc(sub)}</div>` : ''}</div>`;

  const titleLink = (ev: { title?: string | null; source_ref?: string | null }, meta: any) => {
    const t = displayTitle(ev.title, ev.source_ref, meta);
    return ev.source_ref && String(ev.source_ref).startsWith('http')
      ? `<a href="${esc(ev.source_ref)}" target="_blank" rel="noopener">${esc(t)}</a>`
      : esc(t);
  };

  const facts = situationFacts(d);
  const situationHtml = (inc.description || situation || facts.length) ? `<section id="situation"><h2>Situation</h2>
    <div class="card">
      ${inc.description ? `<p style="margin:0 0 8px;color:var(--text2)">${linkifyEscaped(esc(cleanText(inc.description)))}</p>` : ''}
      ${situation ? `<p style="margin:0;color:var(--text2)">${linkifyEscaped(esc(situation))}</p>
      <p class="muted" style="margin:6px 0 0">AI-generated situation summary — verify before external use.</p>` : ''}
      ${facts.length ? `<p class="muted" style="margin:${situation || inc.description ? '10px' : '0'} 0 0;font-style:normal">${facts.map(esc).join(' · ')}</p>` : ''}
    </div></section>` : '';

  const screened = screenedEvidence(d);
  const signalsHtml = screened.length ? `<section id="signals"><h2>Five Signals screening</h2>
    ${screened.map(ev => {
      const s = (ev as any).signals_summary;
      const meta = (ev as any).meta;
      return `<div class="card">
        <h3>${titleLink(ev, meta)}
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

  const briefSection = run?.brief ? `<section id="brief"><h2>AI monitoring brief</h2>
    <div class="card prose">${briefHtml(run.brief)}
      <p class="muted" style="margin-top:10px">Written by the enrichment agent${run.finished_at ? ` on ${esc(minute(run.finished_at))}` : ''} — AI-generated from the attached material; verify before acting.</p>
    </div></section>` : '';

  const evidenceHtml = `<section id="evidence"><h2>Evidence (${(inc.evidence || []).length})</h2>
    <p class="muted" style="margin:0 0 10px">Append-only, hash-chained locker — entries can never be edited or removed. sha256 digests below allow independent verification.</p>
    ${(inc.evidence || []).map((ev, i) => {
      const s = (ev as any).signals_summary;
      const meta = (ev as any).meta;
      const chips = s?.status === 'completed'
        ? `<span class="sigchips">${(s.signals || []).map((sig: any) =>
            `<span class="sigchip" style="background:${BAND_COLOR[sig.band || 'nodata']}" title="${esc(SIG_TITLES[sig.key] || sig.key)}: ${sig.score != null ? sig.score + '/100' : 'no data'}">${SIG_SHORT[sig.key] || '?'}</span>`).join('')}</span>`
        : '';
      const typeLabel = (meta?.platform || meta?.social_meta?.platform)
        ? 'social post' : ev.evidence_type.replace('_', ' ');
      const facts: string[] = [];
      if (postedDate(meta)) facts.push(`posted ${postedDate(meta)}`);
      const eng = engagementLine(meta);
      if (eng) facts.push(eng);
      const sentChip = meta?.sentiment
        ? `<span class="chip ${String(meta.sentiment).toLowerCase() === 'negative' ? 'neg' : String(meta.sentiment).toLowerCase() === 'positive' ? 'pos' : 'neu'}">${esc(String(meta.sentiment).toLowerCase())}</span>` : '';
      const tr = trans[String(ev.id)];
      return `<details class="alert evi" ${i < 3 ? 'open' : ''}>
        <summary><span class="chev">▸</span>
          <span class="chip neu">${esc(typeLabel)}</span>
          <span class="a-cat">${titleLink(ev, meta)} <span class="muted" style="font-weight:400">${esc(hostOf(ev.source_ref))}</span></span>
          ${sentChip}
          ${chips}
          <span class="a-meta">${esc(postedDate(meta) ? `posted ${postedDate(meta)}` : minute(ev.captured_at))}</span></summary>
        <div class="a-body">
          ${facts.length ? `<p class="muted" style="margin:6px 0 4px">${esc(facts.join(' · '))}</p>` : ''}
          ${ev.content ? (ev.evidence_type === 'note'
            ? `<div class="prose">${briefHtml(truncateBlock(cleanText(String(ev.content)), 4000))}</div>`
            : `<p style="white-space:pre-wrap">${bodyHtml(String(ev.content))}</p>`) : ''}
          ${tr ? `<div class="trans"><b>English translation (from ${esc(tr.language)}, AI-generated):</b><br>${esc(tr.text)}</div>` : ''}
          <p class="muted">captured ${esc(minute(ev.captured_at))} by ${esc(ev.captured_by || 'unknown')} · sha256 <code>${esc(ev.content_sha256)}</code> · chain <code>${esc(ev.chain_sha256)}</code></p>
        </div></details>`;
    }).join('')}
  </section>`;

  const rows = buildTimelineRows(d);
  let lastDay = '';
  const timelineHtml = rows.length ? `<section id="timeline"><h2>Timeline</h2>
    <p class="muted" style="margin:0 0 10px">Source publication dates and case activity, oldest first. Rows marked <span class="chip med">source</span> are when the underlying posts/articles appeared; the rest is case handling.</p>
    <div class="card">
    ${rows.map(r => {
      const head = day(r.at) !== lastDay ? `<div class="tl-day">${esc(dayHeading(r.at))}</div>` : '';
      lastDay = day(r.at);
      return `${head}<div class="tl-row${r.isSource ? ' tl-src' : ''}"><span class="tl-when">${esc(hhmm(r.at) || '—')}</span>
        <span class="tl-actor">${r.isSource ? '<span class="chip med">source</span>' : esc(r.actor)}</span>
        <span class="tl-what">${r.whatHtml || esc(r.what)}</span></div>`;
    }).join('')}
  </div></section>` : '';

  const pending = d.enrichment?.candidates || [];
  const pendingHtml = pending.length ? `<section id="candidates"><h2>Enrichment candidates awaiting review (${pending.length})</h2>
    <div class="card">${pending.map(c => `<div class="tl-row">
      <span class="chip neu">${esc(c.candidate_type.replace('_', ' '))}</span>
      <span class="tl-what">${c.source_ref && String(c.source_ref).startsWith('http') ? `<a href="${esc(c.source_ref)}" target="_blank" rel="noopener">${esc(displayTitle(c.title, c.source_ref, null))}</a>` : esc(displayTitle(c.title, c.source_ref, null))}
        ${c.reason ? `<span class="muted"> — ${esc(c.reason)}</span>` : ''}</span></div>`).join('')}
      <p class="muted" style="margin-top:8px">Found by the enrichment agent; not part of the evidence locker until an analyst attaches them.</p>
    </div></section>` : '';

  const history = d.enrichment?.history || [];
  const historyHtml = history.length ? `<section id="dispositions"><h2>Candidate disposition history (${history.length})</h2>
    <div class="card">${history.map(h => `<div class="tl-row">
      <span class="chip ${h.state === 'attached' ? 'pos' : 'neu'}">${esc(h.state)}</span>
      <span class="chip neu">${esc(h.candidate_type.replace('_', ' '))}</span>
      <span class="tl-what">${h.source_ref && String(h.source_ref).startsWith('http') ? `<a href="${esc(h.source_ref)}" target="_blank" rel="noopener">${esc(displayTitle(h.title, h.source_ref, null))}</a>` : esc(displayTitle(h.title, h.source_ref, null))}
        ${h.reason ? `<span class="muted"> — found: ${esc(h.reason)}</span>` : ''}</span>
      <span class="tl-actor">${esc(h.decided_by || '')}</span>
      <span class="tl-when">${esc(minute(h.decided_at))}</span></div>`).join('')}
      <p class="muted" style="margin-top:8px">Every agent-proposed item an analyst has ruled on. Dismissed items are never re-proposed.</p>
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
.trans{margin:8px 0;padding:8px 10px;border-left:3px solid var(--accent);background:var(--accent-tint);border-radius:0 8px 8px 0;font-size:12.5px}
.sigchips{display:inline-flex;gap:1px;border-radius:999px;overflow:hidden}
.sigchip{color:#fff;font-size:9px;font-weight:700;padding:1px 5px}
.tl-day{font-size:11.5px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:var(--accent);padding:10px 0 4px;border-bottom:1px solid #f4f4f7}
.tl-row{display:flex;gap:10px;padding:5px 0;border-bottom:1px solid #f4f4f7;font-size:12.5px;align-items:baseline}
.tl-row:last-child{border-bottom:none}
.tl-row.tl-src{background:#fdf7fb}
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
    ${situationHtml ? '<a href="#situation">Situation</a>' : ''}
    ${screened.length ? '<a href="#signals">Signals</a>' : ''}
    ${run?.brief ? '<a href="#brief">Brief</a>' : ''}
    <a href="#evidence">Evidence</a>
    ${rows.length ? '<a href="#timeline">Timeline</a>' : ''}
    ${history.length ? '<a href="#dispositions">Dispositions</a>' : ''}
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
  </section>

  ${situationHtml}
  ${signalsHtml}
  ${briefSection}
  ${evidenceHtml}
  ${timelineHtml}
  ${pendingHtml}
  ${historyHtml}

  <footer>Generated by Aunoo AI Brand Watcher · ${gen}<br>
  Parts of this report (AI monitoring brief, Five Signals verdicts, translations) are AI-generated and should be verified before external use.</footer>
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

export function buildIncidentReportPdf(d: IncidentReportData, trans: TranslationMap = {}, situation = ''): void {
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

  const facts = situationFacts(d);
  if (inc.description || situation || facts.length) {
    addText('Situation', 13, true, [214, 64, 159]);
    if (inc.description) addText(cleanText(inc.description), 10.5);
    if (situation) {
      addText(situation, 10.5);
      addText('AI-generated situation summary — verify before external use.', 8.5, false, [130, 130, 130]);
    }
    if (facts.length) addText(facts.join(' · '), 9, false, [100, 100, 100]);
    y += 3;
  }

  const screened = screenedEvidence(d);
  if (screened.length) {
    checkPageBreak(20);
    addText('Five Signals screening', 13, true, [214, 64, 159]);
    for (const ev of screened) {
      const s = (ev as any).signals_summary;
      checkPageBreak(30);
      addText(displayTitle(ev.title, ev.source_ref, (ev as any).meta), 11, true);
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
    addText('AI monitoring brief', 13, true, [214, 64, 159]);
    addText(`AI-generated${run.finished_at ? ` ${minute(run.finished_at)}` : ''} — verify before acting.`, 8.5, false, [130, 130, 130]);
    // Strip markdown headers/bold for the PDF's plain text
    const plain = run.brief.replace(/^#{1,4}\s+/gm, '').replace(/\*\*/g, '');
    addText(plain, 10);
    y += 3;
  }

  checkPageBreak(20);
  addText(`Evidence (${(inc.evidence || []).length}) — append-only, hash-chained`, 13, true, [214, 64, 159]);
  (inc.evidence || []).forEach((ev, i) => {
    const meta = (ev as any).meta;
    checkPageBreak(24);
    addText(`${i + 1}. ${displayTitle(ev.title, ev.source_ref, meta)}`, 10.5, true);
    if (ev.source_ref && String(ev.source_ref).startsWith('http')) addText(ev.source_ref, 8, false, [100, 100, 180]);
    const facts: string[] = [];
    if (postedDate(meta)) facts.push(`Posted ${postedDate(meta)}`);
    const eng = engagementLine(meta);
    if (eng) facts.push(eng);
    facts.push(`captured ${minute(ev.captured_at)} by ${ev.captured_by || 'unknown'}`);
    addText(facts.join(' · '), 8.5, false, [130, 130, 130]);
    if (ev.content) addText(truncateBlock(cleanText(String(ev.content)), 600), 9, false, [60, 60, 60]);
    const tr = trans[String(ev.id)];
    if (tr) addText(`English translation (from ${tr.language}, AI-generated): ${tr.text}`, 9, false, [120, 60, 120]);
    addText(`sha256 ${ev.content_sha256} · chain ${ev.chain_sha256}`, 7, false, [150, 150, 150]);
    y += 2;
  });

  const rows = buildTimelineRows(d);
  if (rows.length) {
    checkPageBreak(20);
    addText('Timeline', 13, true, [214, 64, 159]);
    addText('Source publication dates and case activity, oldest first.', 8.5, false, [130, 130, 130]);
    let lastDay = '';
    for (const r of rows) {
      if (day(r.at) !== lastDay) {
        lastDay = day(r.at);
        checkPageBreak(10);
        addText(dayHeading(r.at), 10, true, [80, 80, 80]);
      }
      addText(`${hhmm(r.at) || '—'}  ${r.actor} — ${r.what}`, 9, false, [70, 70, 70]);
    }
  }

  const history = d.enrichment?.history || [];
  if (history.length) {
    checkPageBreak(20);
    addText(`Candidate disposition history (${history.length})`, 13, true, [214, 64, 159]);
    addText('Every agent-proposed item an analyst has ruled on. Dismissed items are never re-proposed.', 8.5, false, [130, 130, 130]);
    for (const h of history) {
      const decision = h.state === 'attached' ? [22, 130, 60] : [120, 120, 120];
      addText(`${h.state.toUpperCase()}  [${h.candidate_type.replace('_', ' ')}] ${displayTitle(h.title, h.source_ref, null)}`, 9.5, true, decision);
      addText(`  ${h.reason ? `found: ${h.reason} · ` : ''}decided by ${h.decided_by || 'unknown'} at ${minute(h.decided_at)}`, 8.5, false, [110, 110, 110]);
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

export async function downloadIncidentReport(d: IncidentReportData, format: 'md' | 'html' | 'pdf'): Promise<void> {
  const [trans, situation] = await Promise.all([fetchTranslations(d), fetchSituationSummary(d)]);
  const base = `incident-${d.incident.id}-${slug(d.incident.title)}-${new Date().toISOString().slice(0, 10)}`;
  if (format === 'md') download(buildIncidentReportMarkdown(d, trans, situation), `${base}.md`, 'text/markdown');
  else if (format === 'html') download(buildIncidentReportHtml(d, trans, situation), `${base}.html`, 'text/html');
  else buildIncidentReportPdf(d, trans, situation);
}
