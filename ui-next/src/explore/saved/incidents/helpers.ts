import type { SavedIncident } from '../../feed/api';
import { extractSignalTags } from '../../agents/signalBadge';
import { incidentDates } from '../../feed/visuals';

type Tone = 'success' | 'warning' | 'error' | 'info' | 'muted' | 'neutral';
export const SIG_TONE: Record<string, Tone> = { high: 'error', medium: 'warning', low: 'muted' };
export const PLAUS_TONE: Record<string, Tone> = { likely: 'success', questionable: 'warning', implausible: 'error' };
export const QUALITY_TONE: Record<string, Tone> = { high: 'success', mixed: 'warning', low: 'error' };
export const TYPE_LABEL: Record<string, string> = {
  incident: 'Incident', entity: 'Entity', expertise: 'Expertise', informed_insider: 'Informed insider', trend_signal: 'Trend signal',
  strategic_shift: 'Strategic shift', event: 'Event',
};

export const nameOf = (i: SavedIncident) => i.name || i.title || 'Unnamed incident';
export const keyOf = (i: SavedIncident) => String(i._saved_id ?? `${nameOf(i)}|${i.topic ?? ''}`);

/** Article links: the uri list, falling back to the metadata's own uris (promoted incidents carry only metadata) */
export function articlesOf(i: SavedIncident) {
  const meta = i.article_metadata ?? [];
  const uris = i.article_uris?.length ? i.article_uris : meta.map((m) => m.uri).filter((u): u is string => !!u);
  return uris.map((uri, k) => {
    const m = meta.find((x) => x.uri === uri) ?? meta[k];
    const a = i.articles?.[k];
    return { uri, title: m?.title || a?.title || uri, source: m?.news_source || m?.source || a?.source || '', factual: m?.factual_reporting || a?.factual_reporting };
  });
}

/** Observer agent names from the articles' tags */
export function signalTagsOf(i: SavedIncident) {
  return extractSignalTags((i.article_metadata ?? []).flatMap((m) => m.tags ?? []));
}

/** Low plausibility, low source quality or a low-credibility misinformation flag */
export function isLowQuality(i: SavedIncident) {
  return i.plausibility === 'implausible' || i.source_quality === 'low'
    || (i.misinfo_flags ?? []).some((f) => ['low_factuality_source', 'low_credibility_source', 'fringe_bias'].includes(f));
}

/** Dates the incident's timeline names, oldest first */
/** Every date the incident names, oldest first, one per day (timeline entries can be text such as "2026-10-01: first report") */
export function timelineDates(i: SavedIncident) {
  return [...new Set(incidentDates(i as Parameters<typeof incidentDates>[0]))].sort((a, b) => a - b);
}

/** Latest YYYY-MM-DD the incident names (its timeline can hold text such as "reported 2026-10-12") */
export function lastDate(i: SavedIncident) {
  const text = [...(Array.isArray(i.timeline) ? i.timeline : [i.timeline ?? '']), i.last_seen ?? '', i.first_seen ?? ''].join(' ');
  return (text.match(/\d{4}-\d{2}-\d{2}/g) ?? []).sort().pop() ?? '';
}

export const prettyFlag = (f: string) => f.replace(/_/g, ' ');

export function investigatePrompt(i: SavedIncident) {
  const arts = articlesOf(i);
  const entities = i.entities?.slice(0, 10).join(', ') || 'None identified';
  const quality = [i.plausibility && `Plausibility: ${i.plausibility}`, i.source_quality && `Source quality: ${i.source_quality}`].filter(Boolean).join(', ');
  return `Investigate this incident: "${nameOf(i)}"

INCIDENT CONTEXT:
Type: ${i.type || 'event'}
Significance: ${i.significance || 'medium'}
${i.topic ? `Topic: ${i.topic}` : ''}
${quality ? `Quality indicators: ${quality}` : ''}
${i.description || i.summary ? `Description: ${i.description || i.summary}` : ''}
${i.organizational_relevance ? `Why this matters: ${i.organizational_relevance}` : ''}

Key entities: ${entities}

Source articles (${arts.length} total):
${arts.slice(0, 10).map((a) => `- ${a.uri}`).join('\n')}
${arts.length > 10 ? `... and ${arts.length - 10} more articles` : ''}

Please analyse:
1. What is known about this incident from the source articles
2. Key entities and organisations involved
3. Timeline of events if available
4. Potential implications and significance
5. Related incidents or patterns

Provide a full analysis with citations to the source articles.`;
}

export function leadPrompt(i: SavedIncident, lead: string) {
  const entities = i.entities?.slice(0, 10).join(', ');
  return `Research this investigation lead: "${lead}"

PARENT INCIDENT: "${nameOf(i)}"
${i.description || i.summary ? `Context: ${i.description || i.summary}` : ''}
${i.organizational_relevance ? `Why this matters: ${i.organizational_relevance}` : ''}
${entities ? `Related entities: ${entities}` : ''}

Please investigate this specific angle and provide findings with citations.`;
}

export function consensusPrompt(i: SavedIncident) {
  const arts = articlesOf(i);
  return `Perform a consensus analysis on: "${nameOf(i)}"

${i.description || i.summary ? `CONTEXT: ${i.description || i.summary}` : ''}

SOURCE ARTICLES (${arts.length} total):
${arts.slice(0, 20).map((a) => `- ${a.source || 'Unknown'}: ${a.uri}`).join('\n')}${arts.length > 20 ? `\n... and ${arts.length - 20} more sources` : ''}

Please analyse:
1. What different sources are reporting about this incident
2. Points of agreement across sources
3. Points of disagreement or contradiction
4. Overall consensus assessment (strong/moderate/weak/disputed)
5. Key facts: well established vs. still uncertain

Provide a balanced analysis of how this story is being covered across sources, citing specific articles.`;
}

export function toMarkdown(list: SavedIncident[], topic?: string) {
  const out = [`# Saved incidents${topic ? `: ${topic}` : ''}`, '', `Exported ${new Date().toISOString().slice(0, 10)}. Incident summaries are written by AI and may contain errors.`, ''];
  for (const i of list) {
    out.push(`## ${nameOf(i)}`, '', `${TYPE_LABEL[i.type] ?? i.type} · significance ${i.significance}${i.topic ? ` · ${i.topic}` : ''}${lastDate(i) ? ` · ${lastDate(i)}` : ''}`, '');
    if (i.description || i.summary) out.push(i.description || i.summary || '', '');
    if (i.organizational_relevance) out.push(`**Why it matters to us:** ${i.organizational_relevance}`, '');
    if (i.plausibility || i.source_quality) out.push(`Plausibility: ${i.plausibility ?? 'not assessed'} · source quality: ${i.source_quality ?? 'not assessed'}`, '');
    if (i.entities?.length) out.push(`**Entities:** ${i.entities.join(', ')}`, '');
    for (const a of articlesOf(i)) out.push(`- ${a.title}${a.source ? ` (${a.source})` : ''} ${a.uri}`);
    if (i.analyst_notes?.length) {
      out.push('', '**Analyst notes**', '');
      for (const n of i.analyst_notes) out.push(`- ${n.timestamp.slice(0, 16).replace('T', ' ')} ${n.analyst}: ${n.comment}`);
    }
    out.push('');
  }
  return out.join('\n');
}

const csvCell = (v: unknown) => {
  const s = v === null || v === undefined ? '' : String(v);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
};

export function toCsv(list: SavedIncident[]) {
  const head = ['name', 'type', 'significance', 'topic', 'latest date', 'description', 'why it matters', 'plausibility', 'source quality', 'entities', 'articles', 'notes'];
  const rows = list.map((i) => [
    nameOf(i), i.type, i.significance, i.topic, lastDate(i), i.description || i.summary, i.organizational_relevance, i.plausibility, i.source_quality,
    (i.entities ?? []).join('; '), articlesOf(i).map((a) => a.uri).join(' '), i.analyst_notes?.length ?? 0,
  ]);
  return [head, ...rows].map((r) => r.map(csvCell).join(',')).join('\n');
}

/**
 * The old "styled" Markdown report (ExportService.exportIncidentsStyledMarkdown): one section per
 * incident with its badges, dates, description, relevance, credibility, entities, leads, the first
 * five sources as links and the analyst notes. The old one claimed every report "has been reviewed
 * for accuracy"; this one says the summaries are AI-written. It also feeds the PDF.
 */
export function toStyledMarkdown(list: SavedIncident[], topic?: string) {
  const out = ['# Incident report', ''];
  if (topic) out.push(`**Topic:** ${topic}`, '');
  out.push(`**Generated:** ${new Date().toLocaleString('en-GB')}  `, `**Incidents:** ${list.length}`, '', '---', '');
  out.push('## AI technology disclosure', '', '> The incident summaries were written by AI from collected articles and may contain errors. Check the sources before acting on them.', '', '---', '');
  list.forEach((i, n) => {
    out.push(`## ${n + 1}. ${nameOf(i)}`, '');
    const badges = [TYPE_LABEL[i.type] ?? i.type, i.significance && `significance ${i.significance}`, i.plausibility && `plausibility ${i.plausibility}`, i.source_quality && `sources ${i.source_quality}`]
      .filter(Boolean).map((b) => `\`${b}\``);
    if (badges.length) out.push(badges.join(' '), '');
    const seen = [i.first_seen && `First seen: ${i.first_seen}`, i.last_seen && `Last seen: ${i.last_seen}`].filter(Boolean);
    if (seen.length) out.push(`*${seen.join(' | ')}*`, '');
    if (i.description || i.summary) out.push('### Description', '', i.description || i.summary || '', '');
    if (i.organizational_relevance) out.push('### Strategic relevance', '', i.organizational_relevance, '');
    if (i.credibility_summary) out.push('### Credibility', '', i.credibility_summary, '');
    if (i.entities?.length) out.push('### Key entities', '', ...i.entities.map((e) => `- ${e}`), '');
    const leads = Array.isArray(i.investigation_leads) ? i.investigation_leads : [];
    if (leads.length) out.push('### Investigation leads', '', ...leads.map((l) => `- ${l}`), '');
    const arts = articlesOf(i);
    if (arts.length) {
      out.push(`### Source articles (${arts.length})`, '');
      arts.slice(0, 5).forEach((a, j) => out.push(`${j + 1}. ${a.uri ? `[${a.title}](${a.uri})` : a.title}${a.source ? ` · *${a.source}*` : ''}`));
      if (arts.length > 5) out.push('', `*and ${arts.length - 5} more sources*`);
      out.push('');
    }
    if (i.analyst_notes?.length) {
      out.push(`### Analyst notes (${i.analyst_notes.length})`, '');
      for (const note of i.analyst_notes) {
        const d = new Date(note.timestamp);
        const when = Number.isNaN(d.getTime()) ? note.timestamp : d.toLocaleString('en-GB', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
        out.push(`> **${note.analyst}** · ${when}`, '>', `> ${note.comment.replace(/\n/g, '\n> ')}`, '');
      }
    }
    out.push('---', '');
  });
  return out.join('\n');
}

/** The body of /api/share/incident for one saved incident (the old ShareModal's fields) */
export function sharePayload(i: SavedIncident): Record<string, unknown> {
  return {
    incident_name: nameOf(i), incident_type: i.type, significance: i.significance, description: i.description || i.summary, topic: i.topic,
    entities: i.entities, strategic_relevance: i.organizational_relevance, plausibility: i.plausibility, source_quality: i.source_quality,
    credibility_summary: i.credibility_summary, timeline: i.timeline, investigation_leads: Array.isArray(i.investigation_leads) ? i.investigation_leads : undefined,
    first_seen: i.first_seen, last_seen: i.last_seen,
    articles: articlesOf(i).map((a) => ({ title: a.title, source: a.source, url: a.uri })),
    analyst_notes: i.analyst_notes,
  };
}
