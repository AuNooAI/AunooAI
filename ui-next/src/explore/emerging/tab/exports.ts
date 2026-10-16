import { download } from '../../feed/api';
import { downloadPdf } from '../../shared/exports';
import { asStrings, parseTimelineItem, type EmergingTopic } from './types';

/*
 * Markdown and CSV exports of the trending themes, after the old ExportService. Changes: timeline
 * entries that are objects print as "date: event" instead of "[object Object]"; a score of zero is
 * written as 0 in the CSV instead of a blank; and the AI note no longer claims a review that never
 * happened. The PDF is the same Markdown, laid out by shared/exports.ts.
 */

const stamp = () => new Date().toISOString().slice(0, 10);
const timelineText = (t: EmergingTopic) => (t.events?.timeline ?? []).map((i) => {
  const p = parseTimelineItem(i);
  return p.date ? `${p.date}: ${p.event}` : p.event;
});

export function themesMarkdown(topics: EmergingTopic[], scope?: string): string {
  const r = Math.round;
  let md = `# Emerging themes${scope ? `: ${scope}` : ''}\n\n*Generated ${new Date().toLocaleString('en-GB')}*\n\n`;
  md += '## AI technology disclosure\n\nThe themes, their analysis and their scores were produced by AI from collected articles and may contain errors. Check the source articles before acting on them.\n\n---\n\n';
  const avg = topics.length ? r(topics.reduce((s, t) => s + (t.trend_score?.composite ?? (t.confidence_score || 0) * 100), 0) / topics.length) : 0;
  md += `## Summary\n\n- **Themes detected:** ${topics.length}\n- **Accelerating:** ${topics.filter((t) => t.velocity === 'accelerating').length}\n`;
  md += `- **Articles behind them:** ${topics.reduce((s, t) => s + (t.article_count || 0), 0)}\n- **Average score:** ${avg}\n\n---\n\n## Themes (${topics.length})\n\n`;
  topics.forEach((t, i) => {
    md += `### ${i + 1}. ${t.topic_label}\n\n`;
    const meta = [
      t.detection_type && `Type: ${t.detection_type}`, t.velocity && `Velocity: ${t.velocity}`, t.article_count && `${t.article_count} articles`,
      t.source_count && `${t.source_count} sources`, t.synthesis?.urgency && `Urgency: ${t.synthesis.urgency}`,
    ].filter(Boolean);
    if (meta.length) md += `*${meta.join(' | ')}*\n\n`;
    if (t.topic_description) md += `${t.topic_description}\n\n`;
    if (t.first_detection_date) {
      md += `**Detection history:**\n- First seen: ${t.first_detection_date}\n`;
      if (t.last_detection_date && t.last_detection_date !== t.first_detection_date) md += `- Last seen: ${t.last_detection_date}\n`;
      if ((t.detection_count ?? 1) > 1) md += `- Times detected: ${t.detection_count}\n`;
      if (t.trajectory) md += `- Trajectory: ${t.trajectory}\n`;
      md += '\n';
    }
    if (t.why_emerging) md += `**Why emerging:** ${t.why_emerging}\n\n`;
    if (t.synthesis?.key_takeaway) md += `**Key takeaway:** ${t.synthesis.key_takeaway}\n\n`;
    if (t.trend_score) {
      const s = t.trend_score;
      md += `#### Trend score\n\n| Volume | Velocity | Diversity | Novelty | Overall |\n|---|---|---|---|---|\n| ${r(s.volume)} | ${r(s.velocity)} | ${r(s.diversity)} | ${r(s.novelty)} | **${r(s.composite)}** |\n\n`;
    }
    if (t.key_entities?.length) md += `**Key entities:** ${t.key_entities.join(', ')}\n\n`;
    const a = t.actors;
    if (a?.companies?.length || a?.people?.length || a?.organizations?.length) {
      md += '#### Key actors\n\n';
      if (a.companies?.length) md += `- **Companies:** ${a.companies.join(', ')}\n`;
      if (a.people?.length) md += `- **People:** ${a.people.join(', ')}\n`;
      if (a.organizations?.length) md += `- **Organisations:** ${a.organizations.join(', ')}\n`;
      md += '\n';
    }
    const tl = timelineText(t);
    if (t.events?.trigger_event || tl.length) {
      md += '#### Events\n\n';
      if (t.events?.trigger_event) md += `**Trigger:** ${t.events.trigger_event}\n\n`;
      if (tl.length) md += `**Timeline:**\n${tl.map((x) => `- ${x}`).join('\n')}\n\n`;
      if (t.events?.current_status) md += `**Current status:** ${t.events.current_status}\n\n`;
    }
    const g = asStrings(t.signals?.growth_indicators), rk = asStrings(t.signals?.risk_factors), w = asStrings(t.signals?.watch_for);
    if (g.length || rk.length || w.length) {
      md += '#### Signals\n\n';
      if (g.length) md += `**Growth indicators:**\n${g.map((x) => `- ${x}`).join('\n')}\n\n`;
      if (rk.length) md += `**Risk factors:**\n${rk.map((x) => `- ${x}`).join('\n')}\n\n`;
      if (w.length) md += `**Watch for:**\n${w.map((x) => `- ${x}`).join('\n')}\n\n`;
    }
    const im = t.implications;
    if (im?.industry_impact || im?.regulatory || im?.market) {
      md += '#### Implications\n\n';
      if (im.industry_impact) md += `- **Industry:** ${im.industry_impact}\n`;
      if (im.regulatory) md += `- **Regulatory:** ${im.regulatory}\n`;
      if (im.market) md += `- **Market:** ${im.market}\n`;
      md += '\n';
    }
    if (t.synthesis?.stakeholders_affected?.length) md += `**Stakeholders affected:** ${t.synthesis.stakeholders_affected.join(', ')}\n\n`;
    if (t.representative_keywords?.length) md += `**Keywords:** ${t.representative_keywords.join(', ')}\n\n`;
    md += '---\n\n';
  });
  return md;
}

const fileBase = (scope?: string) => `emerging-topics${scope ? `-${scope.toLowerCase().replace(/\s+/g, '-')}` : ''}-${stamp()}`;

export function exportMarkdown(topics: EmergingTopic[], scope?: string) {
  download(`${fileBase(scope)}.md`, themesMarkdown(topics, scope));
}

export function exportPdf(topics: EmergingTopic[], scope?: string) {
  return downloadPdf({
    filename: `${fileBase(scope)}.pdf`,
    title: `Emerging themes${scope ? `: ${scope}` : ''}`,
    subtitle: `${topics.length} theme${topics.length === 1 ? '' : 's'} · generated ${new Date().toLocaleString('en-GB')}`,
    markdown: themesMarkdown(topics, scope),
  });
}

const HEADERS = [
  'Theme', 'Description', 'Detection type', 'Velocity', 'Urgency', 'Articles', 'Sources', 'Volume score', 'Velocity score', 'Diversity score',
  'Novelty score', 'Overall score', 'Confidence', 'First detected', 'Last detected', 'Times detected', 'Trajectory', 'Why emerging', 'Key takeaway',
  'Key entities', 'Companies', 'People', 'Organisations', 'Trigger event', 'Current status', 'Growth indicators', 'Risk factors', 'Watch for',
  'Industry impact', 'Regulatory impact', 'Market impact', 'Stakeholders affected', 'Keywords',
];

export function exportCsv(topics: EmergingTopic[]) {
  const c = (v: unknown) => (v === undefined || v === null || v === '' ? '' : `"${String(v).replace(/"/g, '""')}"`);
  const j = (v: unknown) => asStrings(v).join('; ');
  const rows = topics.map((t) => [
    t.topic_label, t.topic_description, t.detection_type, t.velocity, t.synthesis?.urgency, t.article_count ?? 0, t.source_count,
    t.trend_score?.volume, t.trend_score?.velocity, t.trend_score?.diversity, t.trend_score?.novelty, t.trend_score?.composite,
    t.confidence_score != null ? `${Math.round(t.confidence_score * 100)}%` : '', t.first_detection_date, t.last_detection_date, t.detection_count ?? 1,
    t.trajectory, t.why_emerging, t.synthesis?.key_takeaway, j(t.key_entities), j(t.actors?.companies), j(t.actors?.people), j(t.actors?.organizations),
    t.events?.trigger_event, t.events?.current_status, j(t.signals?.growth_indicators), j(t.signals?.risk_factors), j(t.signals?.watch_for),
    t.implications?.industry_impact, t.implications?.regulatory, t.implications?.market, j(t.synthesis?.stakeholders_affected), j(t.representative_keywords),
  ].map(c).join(','));
  download(`emerging-topics-${stamp()}.csv`, [HEADERS.join(','), ...rows].join('\n'), 'text/csv');
}
