/**
 * Adapters mapping the monolith's stored trend-convergence payloads onto the
 * response shapes the shared-dashboard Consensus / Horizons views render.
 *
 * The views (ConsensusView.tsx / HorizonsView.tsx) are ported from the saas
 * app, whose services flattened this monolith's prompt output. The prompt
 * here still emits the numbered-key category schema (`1_consensus_type`,
 * `9_timeframe_analysis`, …) and timeframe strings ("2025-2032") instead of
 * timeline_start/timeline_end, so the flattening lives client-side.
 */

import type { ConsensusResponse, ConsensusCategory, ReferencedArticle } from './ConsensusView';
import type { HorizonsResponse, Scenario, ExecutiveSummary } from './HorizonsView';
import type { TopicExecutiveSummary } from '../../types/horizonsExecutiveSummary';

// ─── Consensus ───────────────────────────────────────────────────────────────

/** Numbered-key category (current prompt schema) → flat view shape. */
function flattenCategory(cat: any): ConsensusCategory | null {
  if (!cat) return null;
  // Already-flat payloads (future prompt revisions) pass through untouched.
  if (cat.sentiment_distribution || cat.majority_agreement != null) return cat;

  const consensusType = cat['1_consensus_type'] || {};
  const timelineConsensus = cat['2_timeline_consensus'] || {};
  const confidence = cat['3_confidence_level'] || {};

  return {
    category_name: cat.category_name || 'Untitled theme',
    category_description: cat.category_description,
    sentiment_distribution: consensusType.distribution,
    consensus_strength: confidence.consensus_strength,
    evidence_quality: confidence.evidence_quality,
    majority_agreement: confidence.majority_agreement,
    articles_analyzed: cat.articles_analyzed,
    timeline_window: timelineConsensus.consensus_window,
    strategic_implications: cat['7_strategic_implications'],
    key_articles: cat['6_key_articles'],
    optimistic_outlier: (cat['4_optimistic_outliers'] || [])[0] || null,
    pessimistic_outlier: (cat['5_pessimistic_outliers'] || [])[0] || null,
    timeframe_analysis: cat['9_timeframe_analysis'],
  };
}

/** article_list entries carry the citation index as `id` ([N] markers). */
function mapConsensusArticle(a: any): ReferencedArticle {
  return {
    id: a.id,
    citation_number: a.id,
    title: a.title,
    url: a.url || (typeof a.uri === 'string' && a.uri.startsWith('http') ? a.uri : undefined),
    source: a.source,
    published_at: a.publication_date || a.published_at || null,
  };
}

export function toConsensusResponse(data: any, topicLabel: string): ConsensusResponse {
  const categories = ((data?.categories || []) as any[])
    .map(flattenCategory)
    .filter((c): c is ConsensusCategory => c != null);
  const articles = ((data?.article_list || []) as any[]).map(mapConsensusArticle);
  return {
    categories,
    key_insights: data?.key_insights || [],
    article_count: data?.articles_analyzed || data?.total_articles_found || articles.length,
    articles,
    topic: topicLabel,
  };
}

// ─── Horizons ────────────────────────────────────────────────────────────────

/** Parse "2025-2032" / "2025–2032" / "2026" timeframe strings into years. */
function parseTimeframe(tf: unknown): { start: number | null; end: number | null } {
  if (typeof tf !== 'string') return { start: null, end: null };
  const range = tf.match(/(\d{4})\s*[-–—]\s*(\d{4})/);
  if (range) return { start: Number(range[1]), end: Number(range[2]) };
  const single = tf.match(/(\d{4})/);
  if (single) return { start: Number(single[1]), end: Number(single[1]) + 1 };
  return { start: null, end: null };
}

function mapScenario(s: any): Scenario {
  const { start, end } = parseTimeframe(s?.timeframe);
  return {
    type: s?.type,
    title: s?.title || '',
    description: s?.description || '',
    timeframe: s?.timeframe,
    timeline_start: s?.timeline_start ?? start ?? undefined,
    timeline_end: s?.timeline_end ?? end ?? undefined,
    sentiment: s?.sentiment,
  };
}

/** Monolith TopicExecutiveSummary → the view's Strategic Consensus card shape. */
function mapExecSummary(e: TopicExecutiveSummary): ExecutiveSummary {
  const forks: ExecutiveSummary['decision_fork'] = [];
  const fork = e.decision_fork || ({} as TopicExecutiveSummary['decision_fork']);
  if (fork?.condition_a?.condition || fork?.condition_a?.outcome) {
    forks.push({ branch: 'positive', if_clause: fork.condition_a.condition || '', then_clause: fork.condition_a.outcome || '' });
  }
  if (fork?.condition_b?.condition || fork?.condition_b?.outcome) {
    forks.push({ branch: 'warning', if_clause: fork.condition_b.condition || '', then_clause: fork.condition_b.outcome || '' });
  }
  const minority = e.minority_view?.statement
    ? e.minority_view.percentage_range
      ? `${e.minority_view.statement} (${e.minority_view.percentage_range})`
      : e.minority_view.statement
    : '';
  return {
    title: e.topic_title || '',
    summary: e.opening_statement || '',
    consensus_pct: e.consensus_percentage,
    minority_view: minority,
    primary_signal: e.primary_signal || '',
    decision_fork: forks,
    underlying_scenarios: (e.source_scenarios || [])
      .map((s) => (typeof s === 'string' ? s : s?.title || ''))
      .filter(Boolean),
  };
}

/** Horizons reference articles arrive with a sequential `id` = citation number. */
function mapHorizonArticle(a: any, idx: number): ReferencedArticle {
  return {
    id: a.id ?? idx + 1,
    citation_number: a.id ?? idx + 1,
    title: a.title,
    url: a.url || (typeof a.uri === 'string' && a.uri.startsWith('http') ? a.uri : undefined),
    source: a.source || a.source_name,
    published_at: a.published_at || a.publication_date || null,
  };
}

export function toHorizonsResponse(opts: {
  scenarios: any[];
  articleList: any[];
  execSummaries: TopicExecutiveSummary[] | null;
  topic: string;
  articleCount?: number;
}): HorizonsResponse {
  const scenarios = (opts.scenarios || []).filter(Boolean).map(mapScenario);
  const articles = (opts.articleList || []).map(mapHorizonArticle);
  return {
    scenarios,
    executive_summaries: (opts.execSummaries || []).map(mapExecSummary),
    article_count: opts.articleCount ?? articles.length,
    articles,
    topic: opts.topic,
  };
}
