import type {
  Brand, BWAlert, BWArticle, BWCategory, BWComparison, BWIncident, BWRiskAssessment, BWSavedNarrative, BWSentimentTrend,
  BWShareOfVoice, BWStats,
} from '@monolith/brandWatcherApi';

/*
 * The brand report as Markdown, for the Markdown download, the PDF and the print view. Same
 * sections as the old ExportService.exportBrandWatcherMarkdown (ui/src/services/exportService.ts),
 * built from the data the HTML report fetches, so all four exports describe the same period.
 */

export interface ReportData {
  brand?: Brand | null;
  daysBack: number;
  stats: BWStats | null;
  categories: BWCategory[];
  sentimentTrends: BWSentimentTrend[];
  alerts: BWAlert[];
  comparison: BWComparison[];
  shareOfVoice: BWShareOfVoice[];
  narrative: BWSavedNarrative | null;
  riskAssessment: BWRiskAssessment | null;
  incidents: BWIncident[];
  articles: BWArticle[];
}

const cell = (v: unknown) => String(v ?? '').replace(/\|/g, '\\|').replace(/\s+/g, ' ').trim();
const pct = (n: number, d: number) => (d > 0 ? `${((n / d) * 100).toFixed(1)}%` : '—');

/** Sentiment labels vary by source ("Positive", "positive", "Very negative"); fold them into three */
function sentimentBuckets(s: Record<string, number>) {
  const out = { positive: 0, neutral: 0, negative: 0 };
  for (const [k, v] of Object.entries(s || {})) {
    const key = k.toLowerCase();
    if (key.includes('pos')) out.positive += v;
    else if (key.includes('neg') || key.includes('crit')) out.negative += v;
    else out.neutral += v;
  }
  return out;
}

export const reportTitle = (d: ReportData) => `Brand report: ${d.brand?.display_name ?? 'all brands'}`;
export const reportPeriod = (d: ReportData) => (d.daysBack === 0 ? 'All time' : `Last ${d.daysBack} days`);

export function buildReportMarkdown(d: ReportData): string {
  const lines: string[] = [];
  const push = (...l: string[]) => lines.push(...l);
  push(`# ${reportTitle(d)}`, '', `${reportPeriod(d)} · generated ${new Date().toLocaleString('en-GB')}`, '');

  // Overview
  if (d.stats) {
    push('## Key figures', '', '| Figure | Value |', '|---|---|');
    push(`| Articles about the brand (earned coverage) | ${d.stats.total_articles} |`);
    if (d.stats.owned_articles) push(`| The brand's own posts and press, not counted above | ${d.stats.owned_articles} |`);
    push(`| Brands tracked | ${d.stats.total_brands} |`);
    push(`| Most active category | ${cell(d.stats.most_active_category ?? '—')} |`);
    push(`| Articles in more than one category | ${d.stats.multi_category_count} |`);
    if (d.stats.date_range_start) push(`| Date range | ${d.stats.date_range_start} to ${d.stats.date_range_end} |`);
    push('');
  }

  // Sentiment, summed over the weekly trend
  const agg = { positive: 0, neutral: 0, negative: 0 };
  for (const t of d.sentimentTrends) {
    const s = sentimentBuckets(t.sentiments);
    agg.positive += s.positive; agg.neutral += s.neutral; agg.negative += s.negative;
  }
  const sentTotal = agg.positive + agg.neutral + agg.negative;
  if (sentTotal > 0) {
    push('## Sentiment', '', '| Sentiment | Articles | Share |', '|---|---|---|');
    push(`| Positive | ${agg.positive} | ${pct(agg.positive, sentTotal)} |`, `| Neutral | ${agg.neutral} | ${pct(agg.neutral, sentTotal)} |`, `| Negative | ${agg.negative} | ${pct(agg.negative, sentTotal)} |`, '');
    push('An article in several categories is counted once per category here, so the totals can exceed the article count above.', '');
  }

  // Risk
  const ra = d.riskAssessment;
  if (ra) {
    push('## Risk', '');
    if (ra.active_issues?.length) {
      push('| Severity | Type | Issue | Coverage | Momentum |', '|---|---|---|---|---|');
      for (const i of ra.active_issues) {
        push(`| ${i.severity} | ${cell(i.primary_type.replace(/_/g, ' '))} | ${cell(i.title)} | ${i.articles} articles, ${i.sources} sources, first seen ${i.first_seen} | ${i.momentum} |`);
      }
      push('');
    } else {
      push('No active issues: no adverse events are open for this brand.', '');
    }
    if (ra.attention?.available && ra.attention.category_spikes?.length) {
      push(`Attention (coverage volume, not risk): ${ra.attention.category_spikes.map((s) => `${s.category} at ${s.multiple}× its usual level (${s.recent} against ${s.weekly_avg} a week)`).join('; ')}.`, '');
    }
  }

  if (d.alerts.length) {
    push('## Coverage spikes', '', '| Severity | Category | This period | Usual | Spike |', '|---|---|---|---|---|');
    for (const a of [...d.alerts].sort((x, y) => y.spike_ratio - x.spike_ratio)) {
      push(`| ${a.severity} | ${cell(a.category)} | ${a.current_count} | ${a.average_count?.toFixed(1)} | ${a.spike_ratio?.toFixed(1)}× |`);
    }
    push('');
  }

  const openIncidents = d.incidents.filter((i) => i.status !== 'resolved' && i.status !== 'closed');
  if (openIncidents.length) {
    push('## Open incidents', '', '| # | Title | Severity | Status | Evidence |', '|---|---|---|---|---|');
    for (const i of openIncidents) push(`| ${i.id} | ${cell(i.title)} | ${i.severity} | ${i.status} | ${i.evidence_count ?? 0} |`);
    push('');
  }

  if (d.categories.length) {
    push('## Categories', '', '| Category | Articles | Share |', '|---|---|---|');
    for (const c of d.categories) push(`| ${cell(c.category)} | ${c.article_count} | ${c.percentage.toFixed(1)}% |`);
    push('');
  }

  // Competitors
  const sovTotal = d.shareOfVoice.reduce((n, s) => n + s.mention_count, 0);
  if (d.shareOfVoice.length && sovTotal > 0) {
    push('## Share of voice', '', 'Earned coverage only; each brand\'s own posts are listed beside it, not counted.', '', '| Brand | Articles | Share | Own posts |', '|---|---|---|---|');
    for (const s of [...d.shareOfVoice].sort((a, b) => b.mention_count - a.mention_count)) {
      push(`| ${cell(s.brand_name)} | ${s.mention_count} | ${s.percentage.toFixed(1)}% | ${s.owned_count ?? '—'} |`);
    }
    push('');
  }
  if (d.comparison.length) {
    push('## Sentiment by brand', '', '| Brand | Articles | Positive | Neutral | Negative |', '|---|---|---|---|---|');
    for (const c of [...d.comparison].sort((a, b) => b.total_articles - a.total_articles)) {
      const s = sentimentBuckets(c.sentiment_breakdown);
      const t = s.positive + s.neutral + s.negative;
      push(`| ${cell(c.brand_name)} | ${c.total_articles} | ${pct(s.positive, t)} | ${pct(s.neutral, t)} | ${pct(s.negative, t)} |`);
    }
    push('');
  }

  if (d.narrative?.narrative) {
    push('## AI-written summary', '');
    if (d.narrative.generated_at) push(`Written ${new Date(d.narrative.generated_at).toLocaleDateString('en-GB')}${d.narrative.days_back ? ` over the last ${d.narrative.days_back} days` : ''}.`, '');
    push(d.narrative.narrative.trim(), '');
  }

  if (d.articles.length) {
    const shown = d.articles.slice(0, 50);
    push(`## Articles (${shown.length} of ${d.articles.length} on the current page)`, '');
    shown.forEach((a, i) => {
      push(`${i + 1}. [${(a.title || a.uri).replace(/[[\]]/g, '')}](${a.uri})${a.news_source ? `, ${a.news_source}` : ''}${a.publication_date ? `, ${String(a.publication_date).slice(0, 10)}` : ''}${a.sentiment ? ` · ${a.sentiment}` : ''}`);
    });
    push('');
  }

  push('---', '', 'AI disclosure: article classification, sentiment, risk screening and the summary are produced by AI from collected sources and may contain errors. Check the linked source before acting on it.');
  return lines.join('\n');
}
